"""Input helpers built on prompt_toolkit."""

from __future__ import annotations

from prompt_toolkit import PromptSession


class InputSession:
    """Async prompt wrapper."""

    def __init__(self) -> None:
        self._session: PromptSession | None = None  # Do not create immediately
        self._prompt = "> "

    @property
    def session(self) -> PromptSession:
        if self._session is None:
            self._session = PromptSession()
        return self._session

    def set_modes(self, *, vim_enabled: bool, voice_enabled: bool) -> None:
        """Update prompt decorations for active modes."""
        parts: list[str] = []
        if vim_enabled:
            parts.append("[vim]")
        if voice_enabled:
            parts.append("[voice]")
        prefix = "".join(parts)
        self._prompt = f"{prefix}> " if prefix else "> "

    async def prompt(self) -> str:
        """Prompt the user for one line of input."""
        return await self.session.prompt_async(self._prompt)

    async def ask(self, question: str) -> str:
        """Prompt the user for an ad-hoc answer."""
        prompt = f"[question] {question}\n> "
        return await self.session.prompt_async(prompt)
