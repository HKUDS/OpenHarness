"""OrcaRouter provider support: credentials, OAuth 2.0 + PKCE, and model catalog.

OrcaRouter is an OpenAI-compatible AI gateway: many upstream vendors sit behind
one OpenAI-shaped endpoint.  This module is the single place that knows how a
credential for it is obtained, and the single place that knows how its model
catalog is discovered and filtered.

Two credential entry points produce the *same* durable ``sk-orca-…`` API key:

* :class:`ApiKeyCredentialProvider` — the user already holds a key and exports
  or pastes it.
* :class:`PkceCredentialProvider` — OAuth 2.0 + PKCE (RFC 7636) issues a key
  through a browser consent screen, either by loopback redirect (Flow A) or
  out-of-band code (Flow B).

Both adapters return one :class:`OrcaRouterCredential`, so the inference client,
the model catalog, and every AI entry point stay unaware of where the key came
from.

Origins are deliberately independent.  Authentication lives on
``https://www.orcarouter.ai`` (``/auth`` for consent, ``/api/v1/auth/keys`` for
the code exchange).  Inference and model discovery live on
``https://api.orcarouter.ai/v1``.  One is never derived from the other by
swapping a hostname or blindly appending ``/v1``: ``/v1/auth/keys`` does not
exist on the relay.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from openharness.api.errors import OpenHarnessApiError
from openharness.auth.storage import (
    clear_provider_credentials,
    load_credential,
    load_provider_state,
    store_credential,
    store_provider_state,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity and origins
# ---------------------------------------------------------------------------

PROVIDER_NAME = "orcarouter"
PROVIDER_LABEL = "OrcaRouter"
API_KEY_AUTH_SOURCE = "orcarouter_api_key"
OAUTH_AUTH_SOURCE = "orcarouter_oauth"

KEY_PREFIX = "sk-orca-"

DEFAULT_AUTH_BASE = "https://www.orcarouter.ai"
DEFAULT_API_BASE = "https://api.orcarouter.ai/v1"

AUTHORIZE_PATH = "/auth"
EXCHANGE_PATH = "/api/v1/auth/keys"

ENV_AUTH_BASE = "ORCA_AUTH_BASE_URL"
ENV_API_BASE = "ORCA_API_BASE_URL"
ENV_SHARED_BASE = "ORCA_BASE_URL"
ENV_API_KEY = "ORCAROUTER_API_KEY"
ENV_API_KEY_NAMESPACED = "OPENHARNESS_ORCAROUTER_API_KEY"

KEY_DASHBOARD_URL = "https://www.orcarouter.ai/console/keys"
AUTHORIZED_APPS_URL = "https://www.orcarouter.ai/console/authorized-apps"

#: Rows in ``~/.openharness/credentials.json`` under the ``orcarouter`` key.
CREDENTIAL_KEY = "api_key"
STATE_KEY = "reauth_state"

DEFAULT_SCOPE = "api"

#: How long a single PKCE authorization attempt may wait for the browser.
DEFAULT_LOGIN_TIMEOUT = 300.0
DEFAULT_CATALOG_TIMEOUT = 10.0
_MAX_CATALOG_BYTES = 4_000_000
_MAX_CATALOG_ITEMS = 2_000


class OrcaRouterError(OpenHarnessApiError):
    """Base class for OrcaRouter credential and catalog failures."""


class OrcaRouterAuthError(OrcaRouterError):
    """An authorization attempt failed.

    ``status`` carries the HTTP status when the failure came from the auth
    origin.  ``terminal`` is True when retrying the same authorization cannot
    help (denial, state mismatch, expired/reused code, verifier mismatch) and
    False when the same attempt could still succeed.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        terminal: bool = True,
        kind: str = "auth_error",
    ) -> None:
        super().__init__(message)
        self.status = status
        self.terminal = terminal
        self.kind = kind


class OrcaRouterCatalogError(OrcaRouterError):
    """The model catalog could not be retrieved or parsed."""


# ---------------------------------------------------------------------------
# Endpoint resolution
# ---------------------------------------------------------------------------


def _is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower().strip("[]")
    return normalized in {"localhost", "127.0.0.1", "::1"}


def _enforce_transport(url: str, *, what: str) -> str:
    """Reject plaintext HTTP for anything that is not loopback development.

    Credentials travel over these origins, so HTTPS is required off-loopback.
    """
    parts = urlsplit(url)
    if parts.scheme == "https":
        return url
    if parts.scheme == "http" and _is_loopback_host(parts.hostname or ""):
        return url
    raise ValueError(
        f"{what} must use https:// (http:// is only allowed for loopback development): {url}"
    )


def _with_api_path(base: str) -> str:
    """Attach ``/v1`` when a self-hosted base carries no explicit path."""
    parts = urlsplit(base)
    path = parts.path.rstrip("/")
    if not path:
        path = "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def resolve_auth_base(explicit: str | None = None) -> str:
    """Resolve the authentication origin.

    Precedence: explicit override, ``ORCA_AUTH_BASE_URL``, the shared
    self-hosted ``ORCA_BASE_URL``, then the public default.
    """
    candidate = (
        explicit
        or os.environ.get(ENV_AUTH_BASE)
        or os.environ.get(ENV_SHARED_BASE)
        or DEFAULT_AUTH_BASE
    )
    return _enforce_transport(candidate.strip().rstrip("/"), what="OrcaRouter auth base URL")


def resolve_api_base(explicit: str | None = None) -> str:
    """Resolve the inference/model-discovery origin.

    Precedence: explicit override, ``ORCA_API_BASE_URL``, the shared
    self-hosted ``ORCA_BASE_URL``, then the public default.
    """
    explicit_value = explicit or os.environ.get(ENV_API_BASE)
    if explicit_value:
        return _enforce_transport(
            _with_api_path(explicit_value.strip()), what="OrcaRouter API base URL"
        )
    shared = os.environ.get(ENV_SHARED_BASE)
    if shared:
        return _enforce_transport(
            _with_api_path(shared.strip()), what="OrcaRouter API base URL"
        )
    return DEFAULT_API_BASE


def authorize_url(auth_base: str) -> str:
    return f"{resolve_auth_base(auth_base)}{AUTHORIZE_PATH}"


def exchange_url(auth_base: str) -> str:
    return f"{resolve_auth_base(auth_base)}{EXCHANGE_PATH}"


@dataclass(frozen=True)
class OrcaRouterEndpoints:
    """A resolved (auth, api) origin pair."""

    auth_base: str = ""
    api_base: str = ""

    @classmethod
    def resolve(
        cls, *, auth_base: str | None = None, api_base: str | None = None
    ) -> OrcaRouterEndpoints:
        return cls(auth_base=resolve_auth_base(auth_base), api_base=resolve_api_base(api_base))


# ---------------------------------------------------------------------------
# The credential seam: one result, two adapters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrcaRouterCredential:
    """The single credential shape every OrcaRouter entry point produces.

    ``source`` is informational only.  Nothing downstream of a credential
    provider may branch on it: the inference client and the model catalog take
    the key and nothing else.
    """

    api_key: str
    source: str = "api_key"
    scope: str = DEFAULT_SCOPE
    user_id: str = ""
    generation: int = 0

    def masked(self) -> str:
        """Return a display-safe form.  Never return the raw key to a UI."""
        key = self.api_key
        if len(key) <= 12:
            return "…"
        return f"{key[:10]}…{key[-4:]}"


def mask_api_key(value: str | None) -> str:
    """Redact an OrcaRouter key for display, logs, and error text."""
    if not value:
        return ""
    if len(value) <= 12:
        return "…"
    return f"{value[:10]}…{value[-4:]}"


def looks_like_orcarouter_key(value: str) -> bool:
    """Lightweight shape check.

    This is *not* validation: the ``sk-orca-`` prefix proves nothing about
    whether a key is live.  The first real request establishes validity.
    """
    return value.strip().startswith(KEY_PREFIX) and len(value.strip()) > len(KEY_PREFIX)


def api_key_env_value() -> tuple[str, str] | None:
    """Return the first configured OrcaRouter API-key env var and its value."""
    for name in (ENV_API_KEY_NAMESPACED, ENV_API_KEY):
        value = os.environ.get(name, "")
        if value:
            return name, value
    return None


def _scrub(message: str, secrets_to_hide: Sequence[str]) -> str:
    """Remove any secret that may have been echoed back by a server."""
    cleaned = message
    for secret in secrets_to_hide:
        if secret and secret in cleaned:
            cleaned = cleaned.replace(secret, "[REDACTED]")
    return cleaned


# ---------------------------------------------------------------------------
# PKCE primitives (RFC 7636)
# ---------------------------------------------------------------------------


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_code_verifier() -> str:
    """Return a fresh high-entropy verifier.

    Cryptographically random on every call.  Never derived from a timestamp, a
    username, or a fixed salt, and never reused across attempts.
    """
    return _b64url(secrets.token_bytes(32))


def code_challenge_for(verifier: str) -> str:
    """Return ``base64url(sha256(verifier))`` with no padding."""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def generate_state() -> str:
    """Return a fresh opaque CSRF state value."""
    return _b64url(secrets.token_bytes(16))


def states_match(expected: str, received: str | None) -> bool:
    """Constant-time comparison of the state echo."""
    if not expected or received is None:
        return False
    return hmac.compare_digest(expected, received)


def build_authorize_url(
    auth_base: str,
    *,
    callback_url: str,
    code_challenge: str,
    state: str,
    app_name: str = "OpenHarness",
    scope: str = DEFAULT_SCOPE,
    login_hint: str | None = None,
    workspace_hint: str | None = None,
    prompt: str | None = None,
) -> str:
    """Assemble the consent URL.  The verifier is never part of it.

    ``callback_url`` is either ``oob`` (Flow B) or an ``http(s)`` URL.  The
    consent endpoint validates it before showing a screen, so an obviously
    malformed value is rejected here first.
    """
    if callback_url != "oob":
        parts = urlsplit(callback_url)
        if parts.scheme not in {"http", "https"}:
            raise ValueError("OrcaRouter callback_url must be 'oob' or an http(s) URL")
        if parts.scheme == "http" and not _is_loopback_host(parts.hostname or ""):
            raise ValueError("http:// callback URLs are only allowed for loopback hosts")
        if parts.username or parts.password or parts.fragment:
            raise ValueError("callback_url must not contain userinfo or a fragment")
    if scope not in {"api", "connector"}:
        raise ValueError("scope must be 'api' or 'connector'")

    params: dict[str, str] = {
        "callback_url": callback_url,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "app_name": app_name,
        "scope": scope,
    }
    if login_hint:
        params["login_hint"] = login_hint
    if workspace_hint:
        params["workspace_hint"] = workspace_hint
    if prompt:
        params["prompt"] = prompt
    return f"{authorize_url(auth_base)}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Code exchange
# ---------------------------------------------------------------------------

_EXCHANGE_TIMEOUT = 30.0


def exchange_code(
    code: str,
    code_verifier: str,
    *,
    auth_base: str | None = None,
    timeout: float = _EXCHANGE_TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> OrcaRouterCredential:
    """Redeem an auth code for a durable OrcaRouter API key.

    Always posts to the *auth* origin at ``/api/v1/auth/keys``.  ``code`` is
    single-use with a 10 minute TTL; the returned ``scope`` is what was granted,
    which may be narrower than what was requested.
    """
    url = exchange_url(auth_base or "")
    body = {
        "code": code,
        "code_verifier": code_verifier,
        "code_challenge_method": "S256",
    }
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.post(url, json=body, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise OrcaRouterAuthError(
            f"Could not reach the OrcaRouter auth endpoint ({type(exc).__name__}). "
            "Check your network connection and try again.",
            terminal=False,
            kind="network_error",
        ) from None

    if response.status_code != 200:
        raise _exchange_failure(response, code, code_verifier)

    try:
        payload = response.json()
    except ValueError:
        raise OrcaRouterAuthError(
            "The OrcaRouter auth endpoint returned a response that is not JSON.",
            status=response.status_code,
            kind="bad_response",
        ) from None

    key = str(payload.get("key") or "").strip()
    if not key:
        raise OrcaRouterAuthError(
            "The OrcaRouter auth endpoint returned no key.",
            status=response.status_code,
            kind="bad_response",
        )

    granted_scope = str(payload.get("scope") or DEFAULT_SCOPE)
    granted = _check_scope(granted_scope, required=DEFAULT_SCOPE)
    return OrcaRouterCredential(
        api_key=key,
        source="pkce",
        scope=granted,
        user_id=str(payload.get("user_id") or ""),
    )


def _check_scope(granted: str, *, required: str) -> str:
    """Return the granted scope, refusing anything that cannot serve inference."""
    if granted != required:
        raise OrcaRouterAuthError(
            f'OrcaRouter granted scope "{granted}" but this client needs "{required}". '
            "The account or workspace role may not permit this grant.",
            kind="scope_downgrade",
        )
    return granted


def _exchange_failure(response: httpx.Response, code: str, verifier: str) -> OrcaRouterAuthError:
    """Map an exchange failure onto an actionable, secret-free error."""
    status = response.status_code
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    detail = ""
    if isinstance(payload, dict):
        detail = str(
            payload.get("error_description") or payload.get("error") or payload.get("message") or ""
        )
    detail = _scrub(detail, (code, verifier))

    if status == 400:
        message = (
            "OrcaRouter rejected the exchange request (400). The code challenge method did "
            "not match the one sent at authorize time."
        )
        if detail:
            message = f"{message} {detail}"
        return OrcaRouterAuthError(message, status=status, kind="invalid_request")
    if status == 401:
        return OrcaRouterAuthError(
            "OrcaRouter rejected the authorization (401). Start the login again.",
            status=status,
            kind="unauthorized",
        )
    if status == 403:
        message = (
            "OrcaRouter refused the authorization code (403). It may be unknown, expired "
            "(codes live 10 minutes), already used, or it does not match the verifier this "
            "process generated. Run the login again from the same process."
        )
        if detail:
            message = f"{message} {detail}"
        return OrcaRouterAuthError(message, status=status, kind="code_rejected")
    if status == 429:
        return OrcaRouterAuthError(
            "OrcaRouter rate-limited this authorization (429). Each user may issue at most 10 "
            "PKCE keys per 24 hours — reuse the stored key instead of logging in again.",
            status=status,
            kind="rate_limited",
        )
    message = f"OrcaRouter authorization failed with HTTP {status}."
    if detail:
        message = f"{message} {detail}"
    return OrcaRouterAuthError(message, status=status, kind="exchange_failed")


# ---------------------------------------------------------------------------
# Credential providers
# ---------------------------------------------------------------------------


class OrcaRouterCredentialProvider(Protocol):
    """The narrow seam both authentication choices implement."""

    source: str

    def acquire(self) -> OrcaRouterCredential:
        """Return a usable OrcaRouter credential or raise :class:`OrcaRouterError`."""


@dataclass
class ApiKeyCredentialProvider:
    """Adapter for a key the user already holds.

    Resolution order matches the rest of the harness: namespaced env var, plain
    env var, then the harness credential store.  Nothing is written to disk —
    the user already decided where their key lives.
    """

    source: str = "api_key"

    def acquire(self) -> OrcaRouterCredential:
        env = api_key_env_value()
        if env is not None:
            _env_name, secret = env
            return OrcaRouterCredential(
                api_key=secret.strip(),
                source="api_key",
                generation=current_credential_generation(),
            )
        stored = load_credential(PROVIDER_NAME, CREDENTIAL_KEY, use_keyring=False)
        if stored:
            return OrcaRouterCredential(
                api_key=stored.strip(),
                source="api_key",
                generation=current_credential_generation(),
            )
        raise OrcaRouterAuthError(
            "No OrcaRouter API key is configured. Export ORCAROUTER_API_KEY, or run "
            "'oh auth orcarouter' to connect with your OrcaRouter account.",
            kind="missing_api_key",
        )


@dataclass
class PkceCredentialProvider:
    """Adapter for OAuth 2.0 + PKCE.

    Flow A (loopback redirect) is the default because this client is a local
    CLI: it can bind ``127.0.0.1`` on an ephemeral port, so the code returns
    automatically and needs no pre-registered redirect URI.  Flow B
    (out-of-band code) stays available for sandboxes and machines where a
    callback cannot be reached.
    """

    source: str = "pkce"
    app_name: str = "OpenHarness"
    flow: str = "loopback"
    auth_base: str | None = None
    timeout: float = DEFAULT_LOGIN_TIMEOUT
    opener: Callable[[str], None] | None = None
    prompt_for_code: Callable[[], str] | None = None
    on_authorize_url: Callable[[str], None] | None = None
    announce: Callable[[str], None] | None = None

    def acquire(self) -> OrcaRouterCredential:
        from openharness.auth.orcarouter_login import run_pkce_login

        credential = run_pkce_login(
            app_name=self.app_name,
            flow=self.flow,
            auth_base=self.auth_base,
            timeout=self.timeout,
            opener=self.opener,
            prompt_for_code=self.prompt_for_code,
            on_authorize_url=self.on_authorize_url,
            announce=self.announce,
        )
        persist_credential(credential)
        return credential


# ---------------------------------------------------------------------------
# Credential persistence and terminal 401 handling
# ---------------------------------------------------------------------------


def persist_credential(credential: OrcaRouterCredential) -> None:
    """Store the key in the harness credential store and clear reauth state."""
    store_credential(PROVIDER_NAME, CREDENTIAL_KEY, credential.api_key, use_keyring=False)
    state = load_provider_state(PROVIDER_NAME) or {}
    generation = int(state.get("generation") or 0) + 1
    store_provider_state(
        PROVIDER_NAME,
        {
            "generation": generation,
            "source": credential.source,
            "user_id": credential.user_id,
            "needs_reauth": False,
            "reason": "",
        },
    )


def current_credential_generation() -> int:
    state = load_provider_state(PROVIDER_NAME) or {}
    try:
        return int(state.get("generation") or 0)
    except (TypeError, ValueError):
        return 0


def clear_credential() -> None:
    """Remove the stored OrcaRouter key and its reauth state."""
    clear_provider_credentials(PROVIDER_NAME, use_keyring=False)
    store_provider_state(PROVIDER_NAME, {})


def needs_reauth() -> dict[str, Any] | None:
    """Return the reauth record when the active credential is known-dead."""
    state = load_provider_state(PROVIDER_NAME) or {}
    if state.get("needs_reauth"):
        return state
    return None


def mark_needs_reauth(*, generation: int, reason: str, source: str = "") -> bool:
    """Mark *generation* as requiring a fresh login.

    Only the exact generation that made the rejected request is marked.  A late
    failure from a request made with an older key must never invalidate a
    credential the user has since replaced, so a mismatched generation is
    ignored.
    """
    state = load_provider_state(PROVIDER_NAME) or {}
    try:
        stored_generation = int(state.get("generation") or 0)
    except (TypeError, ValueError):
        stored_generation = 0
    if generation != stored_generation:
        log.info(
            "Ignoring OrcaRouter 401 for stale credential generation %s (current %s)",
            generation,
            stored_generation,
        )
        return False

    updated = dict(state)
    updated["needs_reauth"] = True
    updated["reason"] = reason
    if source:
        updated["source"] = source
    updated["marked_at"] = int(time.time())
    store_provider_state(PROVIDER_NAME, updated)
    return True


def handle_auth_failure(*, generation: int, reason: str = "upstream rejected the credential") -> bool:
    """Terminal reauthentication path for a rejected durable key.

    OrcaRouter issues a durable API key, not an access/refresh token pair: there
    is no refresh grant to attempt.  A 401 therefore marks the exact credential
    generation that was rejected and stops; it never triggers a silent refresh
    and never deletes the stored secret before a replacement succeeds.
    """
    return mark_needs_reauth(generation=generation, reason=reason)


def resolve_credential(*, api_key: str | None = None) -> OrcaRouterCredential:
    """Return the credential the provider should use, from either entry point.

    An explicit ``api_key`` (CLI flag, profile field) wins and is attributed to
    the API-key entry point; otherwise the stored/env key is used.
    """
    if api_key:
        return OrcaRouterCredential(
            api_key=api_key.strip(), source="api_key", generation=current_credential_generation()
        )
    return ApiKeyCredentialProvider().acquire()


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

#: Endpoint types that can serve a text chat/agent turn.
TEXT_ENDPOINT_TYPES: frozenset[str] = frozenset(
    {"openai", "anthropic", "gemini", "openai-response"}
)

#: Endpoint types that are never a text chat route.
NON_TEXT_ENDPOINT_TYPES: frozenset[str] = frozenset(
    {"embeddings", "image-generation", "openai-video", "jina-rerank"}
)

#: Capability keys accepted by ``GET /v1/models?capability=…``.
CAPABILITY_ENDPOINTS: dict[str, frozenset[str]] = {
    "chat": TEXT_ENDPOINT_TYPES,
    "embedding": frozenset({"embeddings"}),
    "image": frozenset({"image-generation"}),
    "video": frozenset({"openai-video"}),
    "rerank": frozenset({"jina-rerank"}),
}

#: Verified cold-start seed.  Used only when live discovery fails.  When live
#: discovery succeeds its result is authoritative and no seed entry is merged
#: into it — the seed may only contribute *capability metadata* to a model the
#: live catalog already returned.
SEED_MODELS: tuple[dict[str, Any], ...] = (
    {
        "id": "openai/gpt-5.5",
        "context_length": 400_000,
        "input_modalities": ("text", "image"),
        "reasoning": True,
        "reasoning_efforts": ("low", "medium", "high", "xhigh"),
        "endpoint_types": ("openai", "openai-response"),
    },
    {
        "id": "anthropic/claude-opus-4.8",
        "context_length": 1_000_000,
        "input_modalities": ("text", "image"),
        "reasoning": True,
        "reasoning_efforts": ("low", "medium", "high"),
        "endpoint_types": ("openai", "anthropic", "openai-response"),
    },
    {
        "id": "google/gemini-3.5-flash",
        "context_length": 1_048_576,
        "input_modalities": ("text", "image", "audio", "video"),
        "reasoning": False,
        "reasoning_efforts": (),
        "endpoint_types": ("openai", "gemini"),
    },
    {
        "id": "deepseek/deepseek-v4-pro",
        "context_length": 1_048_576,
        "input_modalities": ("text",),
        "reasoning": False,
        "reasoning_efforts": (),
        "endpoint_types": ("openai", "openai-response"),
    },
    {
        "id": "orcarouter/auto",
        "context_length": None,
        "input_modalities": ("text",),
        "reasoning": False,
        "reasoning_efforts": (),
        "endpoint_types": ("openai", "anthropic", "gemini", "openai-response"),
    },
)

_SEED_BY_ID: dict[str, dict[str, Any]] = {entry["id"]: entry for entry in SEED_MODELS}


@dataclass(frozen=True)
class ModelEntry:
    """One model advertised by the OrcaRouter catalog."""

    id: str
    name: str = ""
    endpoint_types: tuple[str, ...] = ()
    input_modalities: tuple[str, ...] = ()
    context_length: int | None = None
    max_completion_tokens: int | None = None
    reasoning: bool = False
    reasoning_efforts: tuple[str, ...] = ()

    @property
    def supports_text_chat(self) -> bool:
        return bool(TEXT_ENDPOINT_TYPES & set(self.endpoint_types))

    def accepts_modality(self, modality: str) -> bool:
        """Fail closed: an undeclared modality is not accepted."""
        return modality in self.input_modalities


@dataclass(frozen=True)
class ModelCatalog:
    """A catalog plus where it came from."""

    entries: tuple[ModelEntry, ...]
    source: str  # "live" | "seed"
    degraded: bool = False
    detail: str = ""
    api_base: str = ""
    capability: str = ""
    seed_contaminated: bool = False

    def __post_init__(self) -> None:
        # A successful live catalog must never carry seed-only models.
        if self.source == "live" and self.seed_contaminated:
            raise ValueError("live catalog must not contain seed-only models")

    def filtered(self, capability: str, *, modalities: Sequence[str] = ()) -> list[ModelEntry]:
        return filter_models(self.entries, capability, modalities=modalities)


def _coerce_str_tuple(value: Any, *, limit: int = 32) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[str] = []
    for item in value[:limit]:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return tuple(out)


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def parse_model_entry(raw: Any) -> ModelEntry | None:
    """Validate and normalize one catalog record.

    Unknown shapes are dropped rather than guessed at: a catalog entry we
    cannot interpret must not reach a model picker.  Every model keeps its
    ``vendor/model`` namespace verbatim.
    """
    if not isinstance(raw, dict):
        return None
    model_id = raw.get("id")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    model_id = model_id.strip()
    architecture = raw.get("architecture")
    if not isinstance(architecture, dict):
        architecture = {}
    top_provider = raw.get("top_provider")
    if not isinstance(top_provider, dict):
        top_provider = {}

    context_length = _coerce_int(raw.get("context_length")) or _coerce_int(
        top_provider.get("context_length")
    )
    max_completion = _coerce_int(raw.get("max_completion_tokens")) or _coerce_int(
        top_provider.get("max_completion_tokens")
    )

    seed = _SEED_BY_ID.get(model_id, {})
    # Live metadata wins; the verified seed only fills gaps the live record
    # does not describe (notably reasoning ladders).
    input_modalities = _coerce_str_tuple(architecture.get("input_modalities"))
    if not input_modalities:
        input_modalities = tuple(seed.get("input_modalities") or ())

    return ModelEntry(
        id=model_id,
        name=str(raw.get("name") or model_id),
        endpoint_types=_coerce_str_tuple(raw.get("supported_endpoint_types")),
        input_modalities=input_modalities,
        context_length=context_length if context_length is not None else seed.get("context_length"),
        max_completion_tokens=max_completion,
        reasoning=bool(seed.get("reasoning", False)),
        reasoning_efforts=tuple(seed.get("reasoning_efforts") or ()),
    )


def parse_catalog(payload: Any, *, max_items: int = _MAX_CATALOG_ITEMS) -> list[ModelEntry]:
    """Parse a ``/v1/models`` response into validated entries."""
    if not isinstance(payload, dict):
        raise OrcaRouterCatalogError("OrcaRouter model catalog response was not a JSON object")
    data = payload.get("data")
    if not isinstance(data, list):
        raise OrcaRouterCatalogError("OrcaRouter model catalog response has no 'data' list")
    entries: list[ModelEntry] = []
    seen: set[str] = set()
    for raw in data[:max_items]:
        entry = parse_model_entry(raw)
        if entry is None or entry.id in seen:
            continue
        seen.add(entry.id)
        entries.append(entry)
    return entries


def seed_catalog(*, detail: str = "") -> ModelCatalog:
    """Return the verified cold-start catalog used when discovery fails."""
    entries: list[ModelEntry] = []
    for seed in SEED_MODELS:
        entries.append(
            ModelEntry(
                id=str(seed["id"]),
                name=str(seed["id"]),
                endpoint_types=tuple(seed.get("endpoint_types") or ()),
                input_modalities=tuple(seed.get("input_modalities") or ()),
                context_length=seed.get("context_length"),
                reasoning=bool(seed.get("reasoning", False)),
                reasoning_efforts=tuple(seed.get("reasoning_efforts") or ()),
            )
        )
    return ModelCatalog(entries=tuple(entries), source="seed", degraded=True, detail=detail)


def fetch_models(
    api_base: str | None = None,
    api_key: str | None = None,
    *,
    capability: str | None = None,
    timeout: float = DEFAULT_CATALOG_TIMEOUT,
    max_items: int = _MAX_CATALOG_ITEMS,
    max_bytes: int = _MAX_CATALOG_BYTES,
    transport: httpx.BaseTransport | None = None,
) -> list[ModelEntry]:
    """Fetch and parse the live model catalog from the configured origin.

    Bounded in timeout, response size, and item count so a hostile or broken
    catalog cannot exhaust memory.  ``capability`` is passed through as the
    documented query parameter when given.
    """
    if capability is not None and capability not in CAPABILITY_ENDPOINTS:
        raise ValueError(f"unsupported capability: {capability}")
    base = api_base or resolve_api_base()
    url = f"{base}/models"
    params = {"capability": capability} if capability else None
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise OrcaRouterCatalogError(
            f"Could not reach the OrcaRouter model catalog ({type(exc).__name__})"
        ) from None

    if response.status_code in {401, 403}:
        raise OrcaRouterCatalogError(
            f"OrcaRouter model catalog rejected the credential (HTTP {response.status_code})"
        )
    if response.status_code != 200:
        raise OrcaRouterCatalogError(
            f"OrcaRouter model catalog returned HTTP {response.status_code}"
        )
    if len(response.content) > max_bytes:
        raise OrcaRouterCatalogError("OrcaRouter model catalog response exceeded the size limit")
    try:
        payload = response.json()
    except ValueError:
        raise OrcaRouterCatalogError("OrcaRouter model catalog response was not JSON") from None
    return parse_catalog(payload, max_items=max_items)


def discover_catalog(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    capability: str | None = None,
    include_seed_fallback: bool = True,
    timeout: float = DEFAULT_CATALOG_TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> ModelCatalog:
    """Live discovery with a bounded, explicitly-degraded fallback.

    Success returns the live catalog as authoritative.  Failure returns the
    verified seed with ``degraded=True`` so the UI can say so — never a
    free-text box and never an unverified hand-written list.
    """
    try:
        entries = fetch_models(
            api_base,
            api_key,
            capability=capability,
            timeout=timeout,
            transport=transport,
        )
    except OrcaRouterCatalogError as exc:
        if not include_seed_fallback:
            raise
        return seed_catalog(detail=str(exc))
    return ModelCatalog(
        entries=tuple(entries),
        source="live",
        degraded=False,
        api_base=api_base or resolve_api_base(),
        capability=capability or "",
    )


def filter_models(
    entries: Iterable[ModelEntry],
    capability: str,
    *,
    modalities: Sequence[str] = (),
) -> list[ModelEntry]:
    """Return the entries a given AI entry point may actually call.

    Each entry point filters independently:

    * ``chat`` — must expose at least one text endpoint type, and must not be a
      non-text-only model (image generation, video, rerank, embeddings).
    * ``embedding`` / ``image`` / ``video`` / ``rerank`` — strict endpoint match.
    * ``modalities`` — every requested non-text modality must be *explicitly*
      declared in ``architecture.input_modalities``.  Undeclared means excluded.
    """
    if capability not in CAPABILITY_ENDPOINTS:
        raise ValueError(f"unsupported capability: {capability}")
    required = CAPABILITY_ENDPOINTS[capability]
    wanted = [m for m in modalities if m and m != "text"]
    out: list[ModelEntry] = []
    for entry in entries:
        endpoint_types = set(entry.endpoint_types)
        if capability == "chat":
            if not (TEXT_ENDPOINT_TYPES & endpoint_types):
                continue
            if endpoint_types <= NON_TEXT_ENDPOINT_TYPES:
                continue
        elif not (required & endpoint_types):
            continue
        if wanted and not all(entry.accepts_modality(m) for m in wanted):
            continue
        out.append(entry)
    return out


def model_ids(entries: Iterable[ModelEntry]) -> list[str]:
    return [entry.id for entry in entries]


def select_options(
    entries: Iterable[ModelEntry],
    *,
    current: str = "",
    capability: str = "chat",
    modalities: Sequence[str] = (),
) -> list[dict[str, object]]:
    """Build selector options for the TUI, filtered by capability.

    A current value that is no longer compatible is dropped instead of being
    silently kept: the caller is expected to notice its absence and clear it.
    """
    filtered = filter_models(entries, capability, modalities=modalities)
    options: list[dict[str, object]] = []
    for entry in filtered:
        details: list[str] = []
        if entry.context_length:
            details.append(f"{entry.context_length:,} ctx")
        non_text = [m for m in entry.input_modalities if m != "text"]
        if non_text:
            details.append("+".join(non_text))
        options.append(
            {
                "value": entry.id,
                "label": entry.id,
                "description": " · ".join(details),
                "active": entry.id == current,
            }
        )
    return options


def catalog_metadata() -> dict[str, Any]:
    """Seed provenance for reviewers: where the fallback list came from."""
    return {
        "source": f"{DEFAULT_API_BASE}/models",
        "verified_at": "2026-09-18",
        "models": [entry["id"] for entry in SEED_MODELS],
    }


# ---------------------------------------------------------------------------
# Catalog caching
# ---------------------------------------------------------------------------

_CATALOG_CACHE: dict[tuple[str, str], tuple[float, ModelCatalog]] = {}
DEFAULT_CACHE_TTL = 300.0


def clear_catalog_cache() -> None:
    """Drop memoized catalogs (used by tests and by an explicit refresh)."""
    _CATALOG_CACHE.clear()


def cached_catalog(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    capability: str | None = None,
    ttl: float = DEFAULT_CACHE_TTL,
    force_refresh: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> ModelCatalog:
    """Return a catalog, memoized per (origin, capability).

    Live discovery stays authoritative: only its own result is cached under the
    key, so a seed produced by an outage can never be served back as if it were
    live.  A failure falls back to the last known-good live catalog when one is
    still cached, otherwise to the verified seed; both are reported as degraded.
    """
    key = (api_base or resolve_api_base(), capability or "")
    now = time.monotonic()
    if not force_refresh:
        hit = _CATALOG_CACHE.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return hit[1]

    try:
        entries = fetch_models(api_base, api_key, capability=capability, transport=transport)
    except OrcaRouterCatalogError as exc:
        previous = _CATALOG_CACHE.get(key)
        if previous is not None and previous[1].source == "live":
            return replace(
                previous[1],
                degraded=True,
                detail=f"{exc} — showing the last known-good catalog",
            )
        return seed_catalog(detail=str(exc))

    catalog = ModelCatalog(
        entries=tuple(entries),
        source="live",
        degraded=False,
        api_base=key[0],
        capability=key[1],
    )
    _CATALOG_CACHE[key] = (now, catalog)
    return catalog


def restore_model(current: str, entries: Iterable[ModelEntry], capability: str = "chat") -> str:
    """Return *current* when it is still selectable, else an empty string.

    Restoring a persisted model id must re-validate it against the freshly
    discovered catalog: a value that no longer exists, or that lost the
    capability this entry point needs, is cleared rather than kept silently.
    """
    if not current:
        return ""
    allowed = {entry.id for entry in filter_models(entries, capability)}
    return current if current in allowed else ""


__all__ = [
    "API_KEY_AUTH_SOURCE",
    "OAUTH_AUTH_SOURCE",
    "PROVIDER_LABEL",
    "PROVIDER_NAME",
    "ApiKeyCredentialProvider",
    "ModelCatalog",
    "ModelEntry",
    "OrcaRouterAuthError",
    "OrcaRouterCatalogError",
    "OrcaRouterCredential",
    "OrcaRouterEndpoints",
    "OrcaRouterError",
    "PkceCredentialProvider",
    "build_authorize_url",
    "cached_catalog",
    "catalog_metadata",
    "clear_catalog_cache",
    "clear_credential",
    "code_challenge_for",
    "current_credential_generation",
    "discover_catalog",
    "exchange_code",
    "fetch_models",
    "filter_models",
    "generate_code_verifier",
    "generate_state",
    "handle_auth_failure",
    "looks_like_orcarouter_key",
    "mark_needs_reauth",
    "mask_api_key",
    "needs_reauth",
    "persist_credential",
    "resolve_api_base",
    "resolve_auth_base",
    "resolve_credential",
    "restore_model",
    "seed_catalog",
    "select_options",
    "states_match",
]
