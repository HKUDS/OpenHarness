"""Goal verifier: a lightweight model judges continue/done after each turn."""

from __future__ import annotations

import json
import logging

from openharness.api.client import (
    ApiMessageRequest,
    ApiTextDeltaEvent,
    SupportsStreamingMessages,
)
from openharness.engine.messages import (
    ConversationMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from openharness.goal.prompts import (
    MAX_BLOCK_CHARS,
    MAX_TRANSCRIPT_MESSAGES,
    VERIFIER_SYSTEM_PROMPT,
    build_verifier_prompt,
)
from openharness.goal.types import GoalDefinition, VerifierVerdict

log = logging.getLogger(__name__)


def build_transcript(messages: list[ConversationMessage]) -> str:
    """Render a compact text transcript from recent conversation messages.

    Tool calls and their results are included so the verifier sees the actual
    evidence (command output, file contents) rather than only the agent's prose
    claims.  Otherwise a tool-heavy agent loop looks "unverified" to the judge
    and keeps being told to continue, spinning forever.
    """
    lines: list[str] = []
    for message in messages[-MAX_TRANSCRIPT_MESSAGES:]:
        parts: list[str] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                params = json.dumps(block.input, ensure_ascii=False)
                if len(params) > 200:
                    params = params[:200] + "..."
                parts.append(f"[tool_use] {block.name}({params})")
            elif isinstance(block, ToolResultBlock):
                prefix = "[tool_result_error] " if block.is_error else "[tool_result] "
                result_text = block.content
                if len(result_text) > MAX_BLOCK_CHARS:
                    result_text = result_text[: MAX_BLOCK_CHARS - 3] + "..."
                parts.append(prefix + result_text)
        text = "\n".join(part.strip() for part in parts if part and part.strip())
        if not text:
            continue
        text = text.replace("\r\n", "\n")
        if len(text) > MAX_BLOCK_CHARS:
            text = text[: MAX_BLOCK_CHARS - 3] + "..."
        lines.append(f"{message.role}: {text}")
    return "\n".join(lines)


def render_verdict(text: str) -> VerifierVerdict:
    """Parse the verifier's JSON output into a structured verdict.

    Falls back to a continue verdict (via exception) when the output is not
    parseable so that a garbled verifier reply never falsely declares the
    goal complete.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        fence = "```"
        stripped = stripped[len(fence):].strip()
        if stripped.endswith(fence):
            stripped = stripped[:-len(fence)].strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # Tolerate a leading prose prefix by extracting the first JSON object.
        brace_open = stripped.find("{")
        if brace_open >= 0:
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(stripped[brace_open:])
            except json.JSONDecodeError:
                data = None
        else:
            data = None
    if not isinstance(data, dict):
        log.warning("Goal verifier returned unparseable output (first 200 chars): %r", stripped[:200])
        raise ValueError("verifier output is not a JSON object")
    try:
        return VerifierVerdict(
            done=bool(data.get("done", False)),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            rationale=str(data.get("rationale", "") or ""),
            next_step_hint=str(data.get("next_step_hint", "") or ""),
            progress_summary=str(data.get("progress_summary", "") or ""),
        )
    except (TypeError, ValueError) as exc:
        log.warning("Goal verifier verdict fields invalid: %s", exc)
        raise ValueError("verifier output fields invalid") from exc


async def run_goal_verifier(
    api_client: SupportsStreamingMessages,
    goal: GoalDefinition,
    messages: list[ConversationMessage],
    *,
    fallback_model: str = "",
) -> VerifierVerdict:
    """Ask the verifier model to judge whether the goal is achieved.

    ``goal.verifier_model`` wins when set; otherwise the caller-supplied
    ``fallback_model`` (typically the main engine model) is used.
    """
    model = goal.verifier_model.strip() or fallback_model
    prompt = build_verifier_prompt(goal.condition, build_transcript(messages))
    request = ApiMessageRequest(
        model=model,
        messages=[ConversationMessage.from_user_text(prompt)],
        system_prompt=VERIFIER_SYSTEM_PROMPT,
        max_tokens=1024,
    )
    text_parts: list[str] = []
    async for event in api_client.stream_message(request):
        if isinstance(event, ApiTextDeltaEvent):
            text_parts.append(event.text)
    text = "".join(text_parts)
    log.debug("Goal verifier raw output: %r", text[:500])
    verdict = render_verdict(text)
    # A verdict with every field empty carries no signal (e.g. the model
    # echoed `{}` back).  Treat it as a failure so the runner counts it and
    # stops after repeated attempts instead of looping on a prompt the model
    # never answers in the expected JSON shape.
    if (
        not verdict.done
        and not verdict.rationale.strip()
        and not verdict.next_step_hint.strip()
        and not verdict.progress_summary.strip()
    ):
        log.warning("Goal verifier returned an empty verdict: %r", text[:200])
        raise ValueError("verifier returned an empty (no-signal) verdict")
    return verdict