"""Superfast Decision Gate package.

An optional, off-by-default System One front-door classifier for the agent loop.
Concept and reference implementation by Andrea Bruno, CC BY 4.0
(https://github.com/Andrea-Bruno/harness-superfast). The decision models (Von,
OpenJev, Laya) are third-party open models.
"""

from __future__ import annotations

from openharness.superfast.decision_gate import (
    classify_turn,
    derive_route,
    gate_enabled,
    query_system_one,
    shadow_log_turn,
)

__all__ = [
    "classify_turn",
    "derive_route",
    "gate_enabled",
    "query_system_one",
    "shadow_log_turn",
]
