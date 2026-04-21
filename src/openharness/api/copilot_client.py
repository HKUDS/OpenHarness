"""GitHub Copilot API client for OpenHarness.

Wraps :class:`OpenAICompatibleClient` with Copilot-specific headers.
The Copilot chat endpoint is OpenAI-compatible, so all message/tool
conversion is delegated to the inner client.

Authentication uses the persisted GitHub OAuth token directly
(``Authorization: Bearer <token>``) — no additional token exchange
is required.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from openharness.api.client import (
    ApiMessageRequest,
    ApiStreamEvent,
)
from openharness.api.copilot_auth import (
    copilot_api_base,
    load_copilot_auth,
)
from openharness.api.errors import AuthenticationFailure
from openharness.api.openai_client import OpenAICompatibleClient

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Header constants
# ---------------------------------------------------------------------------

_VERSION = "0.1.0"  # OpenHarness version for User-Agent

# Default model for Copilot requests when the configured model is not
# available in the Copilot model catalog.
COPILOT_DEFAULT_MODEL = "gpt-4o"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class CopilotClient:
    """Copilot-aware API client implementing ``SupportsStreamingMessages``.

    Uses the GitHub OAuth token directly as a Bearer token for the
    Copilot API.  No token exchange or session management is needed.

    Parameters
    ----------
    github_token:
        GitHub OAuth token (``ghu_...`` / ``gho_...``).  If *None*, the
        token is loaded from ``~/.openharness/copilot_auth.json``.
    enterprise_url:
        Optional enterprise domain.  If *None*, loaded from the
        persisted auth file (falls back to public GitHub).
    model:
        Default model to request.  Can be overridden per-request via
        ``ApiMessageRequest.model``.
    """

    def __init__(
        self,
        github_token: str | None = None,
        *,
        enterprise_url: str | None = None,
        model: str | None = None,
    ) -> None:
        auth_info = load_copilot_auth()
        token = github_token or (auth_info.github_token if auth_info else None)
        if not token:
            raise AuthenticationFailure(
                "No GitHub Copilot token found. Run 'oh auth copilot-login' first."
            )

        # Resolve enterprise_url: explicit arg > persisted auth > None (public)
        ent_url = enterprise_url or (auth_info.enterprise_url if auth_info else None)

        self._token = token
        self._enterprise_url = ent_url
        self._model = model

        # Build the inner OpenAI-compatible client once.
        base_url = copilot_api_base(ent_url)
        default_headers: dict[str, str] = {
            "User-Agent": f"openharness/{_VERSION}",
            "Openai-Intent": "conversation-edits",
        }
        raw_openai = AsyncOpenAI(
            api_key=token,
            base_url=base_url,
            default_headers=default_headers,
        )
        self._inner = OpenAICompatibleClient(
            api_key=token,
            base_url=base_url,
        )
        # Swap the underlying SDK client so Copilot headers are used.
        self._inner._client = raw_openai  # noqa: SLF001

        log.info(
            "CopilotClient initialised (api_base=%s, enterprise=%s)",
            base_url,
            ent_url or "none",
        )

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Stream a chat completion from the Copilot API.

        Satisfies the ``SupportsStreamingMessages`` protocol expected by
        the OpenHarness query engine.

        If a *model* was provided at construction time it overrides the
        model in *request*; otherwise the request model is passed through.
        """
        effective_model = self._model or request.model
        patched = ApiMessageRequest(
            model=effective_model,
            messages=request.messages,
            system_prompt=request.system_prompt,
            max_tokens=request.max_tokens,
            tools=request.tools,
        )
        async for event in self._inner.stream_message(patched):
            yield event
