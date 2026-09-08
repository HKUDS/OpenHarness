"""Goal verifier tests: verdict parsing and transcript building."""

from __future__ import annotations

import pytest

from openharness.api.client import ApiTextDeltaEvent
from openharness.engine.messages import ConversationMessage, ToolResultBlock, ToolUseBlock
from openharness.goal.prompts import VERIFIER_SYSTEM_PROMPT, build_verifier_prompt
from openharness.goal.types import GoalDefinition
from openharness.goal.verifier import build_transcript, render_verdict, run_goal_verifier


class TestRenderVerdict:
    def test_parses_done_verdict(self):
        verdict = render_verdict(
            '{"done": true, "confidence": 0.9, "rationale": "tests pass", '
            '"next_step_hint": "", "progress_summary": "all done"}'
        )
        assert verdict.done is True
        assert verdict.confidence == 0.9
        assert verdict.rationale == "tests pass"
        assert verdict.progress_summary == "all done"

    def test_parses_continue_verdict(self):
        verdict = render_verdict(
            '{"done": false, "confidence": 0.4, "rationale": "still red", '
            '"next_step_hint": "run pytest next"}'
        )
        assert verdict.done is False
        assert verdict.next_step_hint == "run pytest next"

    def test_tolerates_markdown_fence(self):
        verdict = render_verdict("```json\n{\"done\": true}\n```")
        assert verdict.done is True

    def test_tolerates_prose_prefix(self):
        verdict = render_verdict('Here is the JSON: {"done": true}')
        assert verdict.done is True

    def test_unparseable_output_raises(self):
        with pytest.raises(ValueError):
            render_verdict("sorry, I cannot comply")

    def test_missing_fields_default(self):
        verdict = render_verdict("{}")
        assert verdict.done is False
        assert verdict.confidence == 0.0
        assert verdict.next_step_hint == ""


class TestBuildTranscript:
    def test_renders_role_prefixed_lines(self):
        messages = [
            ConversationMessage.from_user_text("fix the bug"),
            ConversationMessage.from_user_text("and run tests"),
        ]
        transcript = build_transcript(messages)
        assert "user: fix the bug" in transcript
        assert "user: and run tests" in transcript

    def test_truncates_long_message_text(self):
        from openharness.goal.prompts import MAX_BLOCK_CHARS

        long_text = "x" * (MAX_BLOCK_CHARS + 100)
        transcript = build_transcript([ConversationMessage.from_user_text(long_text)])
        assert len(transcript) <= MAX_BLOCK_CHARS + 32  # role prefix + truncation

    def test_includes_tool_calls_and_results(self):
        messages = [
            ConversationMessage(
                role="assistant",
                content=[
                    ToolUseBlock(name="bash", input={"command": "git check-ignore .qoder"}),
                    ToolResultBlock(tool_use_id="x", content=".qoder/"),
                ],
            ),
        ]
        transcript = build_transcript(messages)
        assert "[tool_use] bash" in transcript
        assert "[tool_result] .qoder/" in transcript


class TestBuildVerifierPrompt:
    def test_includes_condition_and_transcript(self):
        prompt = build_verifier_prompt("ship the feature", "user: working on it")
        assert "ship the feature" in prompt
        assert "user: working on it" in prompt


class _CaptureClient:
    """Streams a fixed text reply and records the request for inspection."""

    def __init__(self, text: str):
        self.text = text
        self.request = None

    async def stream_message(self, request):
        self.request = request
        yield ApiTextDeltaEvent(text=self.text)


class TestRunGoalVerifier:
    def _messages(self):
        return [ConversationMessage.from_user_text("working on it")]

    @pytest.mark.asyncio
    async def test_sends_verifier_system_prompt(self):
        client = _CaptureClient('{"done": true, "rationale": "tests pass"}')
        goal = GoalDefinition(condition="ship it")

        verdict = await run_goal_verifier(client, goal, self._messages())

        assert verdict.done is True
        assert client.request.system_prompt == VERIFIER_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_rejects_signal_free_verdict(self):
        client = _CaptureClient("{}")
        goal = GoalDefinition(condition="ship it")

        with pytest.raises(ValueError):
            await run_goal_verifier(client, goal, self._messages())

    @pytest.mark.asyncio
    async def test_accepts_done_without_hint(self):
        client = _CaptureClient('{"done": true}')
        goal = GoalDefinition(condition="ship it")

        verdict = await run_goal_verifier(client, goal, self._messages())

        assert verdict.done is True