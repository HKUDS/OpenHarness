"""Anthropic API client wrapper with retry logic."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Protocol

from anthropic import APIError, APIStatusError, AsyncAnthropic

from openharness.api.errors import (
    AuthenticationFailure,
    OpenHarnessApiError,
    RateLimitFailure,
    RequestFailure,
)
from openharness.auth.external import (
    claude_attribution_header,
    claude_oauth_betas,
    claude_oauth_headers,
    get_claude_code_session_id,
)
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, assistant_message_from_api

log = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds
MAX_DELAY = 30.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}
OAUTH_BETA_HEADER = "oauth-2025-04-20"
CACHE_CONTROL_EPHEMERAL: dict[str, str] = {"type": "ephemeral"}
MAX_CACHE_BREAKPOINTS = 4
_CACHEABLE_MESSAGE_BLOCK_TYPES = frozenset({"image", "document", "tool_use", "tool_result"})


@dataclass(frozen=True)
class ApiMessageRequest:
    """Input parameters for a model invocation."""

    model: str
    messages: list[ConversationMessage]
    system_prompt: str | None = None
    max_tokens: int = 4096
    tools: list[dict[str, Any]] = field(default_factory=list)
    effort: str | None = None


@dataclass(frozen=True)
class ApiTextDeltaEvent:
    """Incremental text produced by the model."""

    text: str


@dataclass(frozen=True)
class ApiMessageCompleteEvent:
    """Terminal event containing the full assistant message."""

    message: ConversationMessage
    usage: UsageSnapshot
    stop_reason: str | None = None


@dataclass(frozen=True)
class ApiRetryEvent:
    """A recoverable upstream failure that will be retried automatically."""

    message: str
    attempt: int
    max_attempts: int
    delay_seconds: float


ApiStreamEvent = ApiTextDeltaEvent | ApiMessageCompleteEvent | ApiRetryEvent


class SupportsStreamingMessages(Protocol):
    """Protocol used by the query engine in tests and production."""

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Yield streamed events for the request."""


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is retryable."""
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, APIError):
        return True  # Network errors are retryable
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    return False


def _get_retry_delay(attempt: int, exc: Exception | None = None) -> float:
    """Calculate delay with exponential backoff and jitter."""
    import random

    # Check for Retry-After header
    if isinstance(exc, APIStatusError):
        retry_after = getattr(exc, "headers", {})
        if hasattr(retry_after, "get"):
            val = retry_after.get("retry-after")
            if val:
                try:
                    return min(float(val), MAX_DELAY)
                except (ValueError, TypeError):
                    pass

    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    jitter = random.uniform(0, delay * 0.25)
    return delay + jitter


class AnthropicApiClient:
    """Thin wrapper around the Anthropic async SDK with retry logic."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        auth_token: str | None = None,
        base_url: str | None = None,
        claude_oauth: bool = False,
        auth_token_resolver: Callable[[], str] | None = None,
        prompt_caching: bool = True,
    ) -> None:
        self._api_key = api_key
        self._auth_token = auth_token
        self._base_url = base_url
        self._claude_oauth = claude_oauth
        self._auth_token_resolver = auth_token_resolver
        self._prompt_caching = prompt_caching
        self._session_id = get_claude_code_session_id() if claude_oauth else ""
        self._client = self._create_client()

    def _create_client(self) -> AsyncAnthropic:
        kwargs: dict[str, Any] = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._auth_token:
            kwargs["auth_token"] = self._auth_token
            kwargs["default_headers"] = (
                claude_oauth_headers()
                if self._claude_oauth
                else {"anthropic-beta": OAUTH_BETA_HEADER}
            )
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return AsyncAnthropic(**kwargs)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    def _refresh_client_auth(self) -> None:
        if not self._claude_oauth or self._auth_token_resolver is None:
            return
        next_token = self._auth_token_resolver()
        if next_token and next_token != self._auth_token:
            self._auth_token = next_token
            self._client = self._create_client()

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Yield text deltas and the final assistant message with retry on transient errors."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                self._refresh_client_auth()
                async for event in self._stream_once(request):
                    yield event
                return  # Success
            except OpenHarnessApiError:
                raise  # Auth errors are not retried
            except Exception as exc:
                last_error = exc
                if attempt >= MAX_RETRIES or not _is_retryable(exc):
                    if isinstance(exc, APIError):
                        raise _translate_api_error(exc) from exc
                    raise RequestFailure(str(exc)) from exc

                delay = _get_retry_delay(attempt, exc)
                status = getattr(exc, "status_code", "?")
                log.warning(
                    "API request failed (attempt %d/%d, status=%s), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, status, delay, exc,
                )
                yield ApiRetryEvent(
                    message=str(exc),
                    attempt=attempt + 1,
                    max_attempts=MAX_RETRIES + 1,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

        if last_error is not None:
            if isinstance(last_error, APIError):
                raise _translate_api_error(last_error) from last_error
            raise RequestFailure(str(last_error)) from last_error

    async def _stream_once(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Single attempt at streaming a message."""
        params: dict[str, Any] = {
            "model": request.model,
            "messages": [message.to_api_param() for message in request.messages],
            "max_tokens": request.max_tokens,
        }
        system_text = request.system_prompt or ""
        if self._claude_oauth:
            attribution = claude_attribution_header()
            system_text = f"{attribution}\n{system_text}" if system_text else attribution
        if system_text:
            params["system"] = system_text
        if request.tools:
            params["tools"] = [dict(tool) for tool in request.tools]
        if self._prompt_caching:
            _apply_prompt_caching(params)
        if self._claude_oauth:
            params["betas"] = claude_oauth_betas()
            params["metadata"] = {
                "user_id": json.dumps(
                    {
                        "device_id": "openharness",
                        "session_id": self._session_id,
                        "account_uuid": "",
                    },
                    separators=(",", ":"),
                )
            }
            params["extra_headers"] = {"x-client-request-id": str(uuid.uuid4())}

        try:
            stream_api = self._client.beta.messages if self._claude_oauth else self._client.messages
            async with stream_api.stream(**params) as stream:
                async for event in stream:
                    if getattr(event, "type", None) != "content_block_delta":
                        continue
                    delta = getattr(event, "delta", None)
                    if getattr(delta, "type", None) != "text_delta":
                        continue
                    text = getattr(delta, "text", "")
                    if text:
                        yield ApiTextDeltaEvent(text=text)

                final_message = await stream.get_final_message()
        except APIError as exc:
            if isinstance(exc, APIStatusError) and exc.status_code in RETRYABLE_STATUS_CODES:
                raise  # Let retry logic handle it
            raise _translate_api_error(exc) from exc

        usage = getattr(final_message, "usage", None)
        yield ApiMessageCompleteEvent(
            message=assistant_message_from_api(final_message),
            usage=_parse_anthropic_usage(usage),
            stop_reason=getattr(final_message, "stop_reason", None),
        )


def _is_cacheable_block(block: dict[str, Any]) -> bool:
    """Return True if a serialized content block can host a cache_control breakpoint."""
    block_type = block.get("type")
    if block_type == "text":
        text = block.get("text")
        return isinstance(text, str) and bool(text.strip())
    return block_type in _CACHEABLE_MESSAGE_BLOCK_TYPES


def _count_cache_breakpoints(params: dict[str, Any]) -> int:
    """Count existing Anthropic prompt-cache breakpoints across tools, system, and messages."""
    count = 0
    tools = params.get("tools")
    if isinstance(tools, list):
        count += sum(1 for tool in tools if isinstance(tool, dict) and tool.get("cache_control"))

    system = params.get("system")
    if isinstance(system, list):
        count += sum(1 for block in system if isinstance(block, dict) and block.get("cache_control"))

    messages = params.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                count += sum(
                    1 for block in content if isinstance(block, dict) and block.get("cache_control")
                )
    return count


def _apply_prompt_caching(params: dict[str, Any]) -> None:
    """Attach ephemeral cache_control breakpoints within Anthropic's 4-breakpoint limit."""
    remaining = max(0, MAX_CACHE_BREAKPOINTS - _count_cache_breakpoints(params))
    if remaining <= 0:
        return

    # Tools are evaluated first in Anthropic's cache prefix hierarchy, so caching
    # the last tool definition lets parent and teammates share tool schemas even
    # when their system prompts differ.
    tools = params.get("tools")
    if isinstance(tools, list) and tools and remaining > 0:
        copied_tools = [dict(tool) if isinstance(tool, dict) else tool for tool in tools]
        last_tool = copied_tools[-1]
        if isinstance(last_tool, dict) and not last_tool.get("cache_control"):
            last_tool["cache_control"] = dict(CACHE_CONTROL_EPHEMERAL)
            remaining -= 1
        params["tools"] = copied_tools

    system = params.get("system")
    if isinstance(system, str):
        if system.strip() and remaining > 0:
            params["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": dict(CACHE_CONTROL_EPHEMERAL),
                }
            ]
            remaining -= 1
    elif isinstance(system, list) and system and remaining > 0:
        copied_system = [dict(block) if isinstance(block, dict) else block for block in system]
        has_system_breakpoint = any(
            isinstance(block, dict) and block.get("cache_control") for block in copied_system
        )
        if not has_system_breakpoint:
            for block in reversed(copied_system):
                if isinstance(block, dict) and _is_cacheable_block(block):
                    block["cache_control"] = dict(CACHE_CONTROL_EPHEMERAL)
                    remaining -= 1
                    break
        params["system"] = copied_system

    messages = params.get("messages")
    if isinstance(messages, list) and messages and remaining > 0:
        has_message_breakpoint = any(
            isinstance(message, dict)
            and isinstance(message.get("content"), list)
            and any(
                isinstance(block, dict) and block.get("cache_control")
                for block in message["content"]
            )
            for message in messages
        )
        if not has_message_breakpoint:
            for message in reversed(messages):
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for block in reversed(content):
                    if isinstance(block, dict) and _is_cacheable_block(block):
                        block["cache_control"] = dict(CACHE_CONTROL_EPHEMERAL)
                        return


def _read_usage_int(usage: Any, field: str) -> int:
    if isinstance(usage, dict):
        return int(usage.get(field, 0) or 0)
    return int(getattr(usage, field, 0) or 0)


def _parse_anthropic_usage(usage: Any) -> UsageSnapshot:
    """Parse standard and prompt-cache token counts from an Anthropic usage payload."""
    if usage is None:
        return UsageSnapshot()
    return UsageSnapshot(
        input_tokens=_read_usage_int(usage, "input_tokens"),
        output_tokens=_read_usage_int(usage, "output_tokens"),
        cache_creation_input_tokens=_read_usage_int(usage, "cache_creation_input_tokens"),
        cache_read_input_tokens=_read_usage_int(usage, "cache_read_input_tokens"),
    )


def _translate_api_error(exc: APIError) -> OpenHarnessApiError:
    name = exc.__class__.__name__
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return AuthenticationFailure(str(exc))
    if name == "RateLimitError":
        return RateLimitFailure(str(exc))
    return RequestFailure(str(exc))
