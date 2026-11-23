"""Superfast Decision Gate -- a System One front-door classifier (shadow mode).

Ported to Python from the reference implementation by Andrea Bruno, released
under Creative Commons Attribution 4.0 (CC BY 4.0). See the harness-superfast
white paper for the full design. The decision models themselves (Von, OpenJev,
Laya) are third-party open models; only this integration architecture and the
routing method are ours.

A small, non-autoregressive "System One" decision model (Von, or any
Jev-compatible server) evaluates the pending user turn in a single forward pass
and returns typed, calibrated answers (choice / noul) without generating text.
The Decision Gate turns those answers into a routing recommendation so the
harness can, in a later validated step, skip expensive System Two work when the
decision is obvious.

Design contract:
  - Off by default. Nothing here runs unless ``SUPERFAST_ENABLED`` is truthy.
  - Fail open. Any error, timeout, non-2xx response, unreachable backend, or
    malformed body returns ``None`` ("no opinion"). Callers treat ``None`` as
    "the Gate is off" and continue exactly as they would without it. The Gate can
    only ever make the harness faster, never change its behaviour when unsure.
  - No new dependencies. The Gate talks to a local HTTP endpoint with the
    project's existing ``httpx`` client, so the decision model is installed
    out-of-band and never bundled.
  - Shadow mode. This first increment only classifies and logs; it never changes
    routing, never skips the model call, and never alters user-visible behavior.
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

#: Default Jev-compatible decision endpoint (a local System One server).
DEFAULT_ENDPOINT = "http://localhost:8000/v1/systemone"
#: Default decision model id sent in the request body.
DEFAULT_MODEL = "von-1.2.0"
#: Hard timeout for a single decision call, in milliseconds.
DEFAULT_TIMEOUT_MS = 150
#: Minimum calibrated intent confidence required for the plain_chat fast route.
PLAIN_CHAT_CONFIDENCE_FLOOR = 0.5

_TRUTHY = {"1", "true", "yes", "on"}


def gate_enabled() -> bool:
    """Return True only when the Gate is explicitly turned on via env var.

    Off by default: an unset or falsy ``SUPERFAST_ENABLED`` means the Gate never
    runs and the harness behaves exactly as if it were absent.
    """
    return os.environ.get("SUPERFAST_ENABLED", "").strip().lower() in _TRUTHY


def _endpoint() -> str:
    return os.environ.get("SUPERFAST_ENDPOINT", "").strip() or DEFAULT_ENDPOINT


def _model() -> str:
    return os.environ.get("SUPERFAST_MODEL", "").strip() or DEFAULT_MODEL


def _timeout_ms() -> int:
    raw = os.environ.get("SUPERFAST_TIMEOUT_MS", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_MS
    return value if 0 < value <= 2_147_483_647 else DEFAULT_TIMEOUT_MS


#: Standard question set for classifying an incoming user turn. Kept small so the
#: single forward pass stays well under the timeout budget.
TURN_QUESTIONS: dict[str, dict[str, Any]] = {
    "needs_tool": {
        "type": "noul",
        "instructions": (
            "Does answering this request require taking an action with a tool "
            "(reading, writing, running, searching), rather than replying from "
            "what is already known?"
        ),
    },
    "answerable_from_context": {
        "type": "noul",
        "instructions": (
            "Can this request be answered from information already present in "
            "the conversation, without any new investigation?"
        ),
    },
    "intent": {
        "type": "choice",
        "instructions": "Classify the primary intent of the user request.",
        "criteria": {
            "code_change": "Create, edit, or delete code or files.",
            "code_question": "Explain or reason about code without changing it.",
            "command": "Run a command or operation.",
            "chat": "Casual conversation or a question needing no tools.",
            "other": "None of the above.",
        },
    },
}


def _read_noul(answer: Any) -> float | None:
    """Read a noul probability, returning it only when it is a real, finite value
    in the closed [0, 1] interval. Anything else (absent, NaN, Infinity, out of
    range, wrong type, or a bool) is treated as "no evidence" (None), so a
    mis-scaled or missing answer can never produce a decisive fast route.
    """
    if not isinstance(answer, dict):
        return None
    value = answer.get("noul")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


def _confident(answer: Any, floor: float) -> bool:
    """Return True only for a real, finite confidence in [0, 1] at or above the
    floor. Anything else is treated as no evidence.
    """
    if not isinstance(answer, dict):
        return False
    value = answer.get("confidence")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and 0.0 <= number <= 1.0 and number >= floor


def derive_route(answers: dict[str, Any]) -> str:
    """Derive a conservative route from the answers.

    The Gate only recommends a fast route when the relevant probabilities are
    decisive; otherwise it says ``unknown`` so the caller falls back to the
    normal path.
    """
    needs_tool = _read_noul(answers.get("needs_tool"))
    from_context = _read_noul(answers.get("answerable_from_context"))

    # Decisive "needs a tool" wins first -- the harness must not skip work.
    if needs_tool is not None and needs_tool >= 0.85:
        return "needs_tool"

    # Strongly answerable from context, with a present and low tool-need signal.
    if (
        from_context is not None
        and from_context >= 0.85
        and needs_tool is not None
        and needs_tool <= 0.3
    ):
        return "answer_from_context"

    # Clearly chat, with a calibrated intent and a present, low tool-need signal.
    intent = answers.get("intent")
    if (
        isinstance(intent, dict)
        and intent.get("choice") == "chat"
        and _confident(intent, PLAIN_CHAT_CONFIDENCE_FLOOR)
        and needs_tool is not None
        and needs_tool <= 0.2
    ):
        return "plain_chat"

    return "unknown"


async def query_system_one(
    state: str,
    questions: dict[str, dict[str, Any]],
    *,
    endpoint: str,
    model: str,
    timeout_ms: int,
) -> dict[str, Any] | None:
    """Issue one System One request.

    Returns the parsed ``answers`` mapping on success, or ``None`` on any failure
    (fail-open). Never raises.
    """
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000.0) as client:
            response = await client.post(
                endpoint,
                json={"model": model, "state": state, "questions": questions},
                headers={"Content-Type": "application/json"},
            )
        if not 200 <= response.status_code < 300:
            log.debug(
                "superfast gate non-2xx status=%s latency_ms=%d",
                response.status_code,
                int((time.perf_counter() - started) * 1000),
            )
            return None
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 -- fail open on any transport/parse error
        log.debug(
            "superfast gate unavailable (fail-open) latency_ms=%d cause=%s",
            int((time.perf_counter() - started) * 1000),
            type(exc).__name__,
        )
        return None

    if not isinstance(payload, dict):
        log.debug("superfast gate malformed response (not an object)")
        return None
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        log.debug("superfast gate malformed response (missing answers)")
        return None
    return answers


async def classify_turn(user_text: str) -> dict[str, Any] | None:
    """Classify a user turn through the Gate.

    Returns ``None`` when the Gate is disabled or unavailable (fail-open).
    Otherwise returns a dict with a conservative ``route``, the raw ``answers``,
    and the measured ``latency_ms``.
    """
    if not gate_enabled():
        return None

    started = time.perf_counter()
    answers = await query_system_one(
        user_text,
        TURN_QUESTIONS,
        endpoint=_endpoint(),
        model=_model(),
        timeout_ms=_timeout_ms(),
    )
    if answers is None:
        return None

    return {
        "route": derive_route(answers),
        "answers": answers,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


async def shadow_log_turn(user_text: str) -> None:
    """Shadow-mode entry point: classify the turn and log the recommendation.

    This never raises and never changes routing. It is meant to be fired as a
    background task so it adds no latency to the real model turn.
    """
    try:
        decision = await classify_turn(user_text)
    except Exception:  # noqa: BLE001 -- shadow mode must never surface an error
        log.debug("superfast shadow classification raised (ignored)", exc_info=True)
        return
    if decision is None:
        return
    log.info(
        "superfast shadow: route=%s latency_ms=%d",
        decision["route"],
        decision["latency_ms"],
    )
