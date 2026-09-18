"""Tests for the OrcaRouter credential seam, PKCE login, and model catalog.

Everything here uses fake keys, fake codes, and a local fake auth server.  No
test reaches a real OrcaRouter origin and no test asserts on a real secret.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Self

import httpx
import pytest

from openharness.api import orcarouter as orca
from openharness.api.orcarouter import (
    ApiKeyCredentialProvider,
    ModelCatalog,
    ModelEntry,
    OrcaRouterAuthError,
    OrcaRouterCatalogError,
    OrcaRouterCredential,
    PkceCredentialProvider,
    build_authorize_url,
    cached_catalog,
    clear_catalog_cache,
    code_challenge_for,
    discover_catalog,
    exchange_code,
    fetch_models,
    filter_models,
    generate_code_verifier,
    generate_state,
    mask_api_key,
    parse_catalog,
    restore_model,
    seed_catalog,
    select_options,
    states_match,
)

FAKE_KEY = "sk-orca-fake-key-for-tests-only-000000"


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Keep credential state inside the test and out of the real home dir."""
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENHARNESS_ORCAROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ORCA_AUTH_BASE_URL", raising=False)
    monkeypatch.delenv("ORCA_API_BASE_URL", raising=False)
    monkeypatch.delenv("ORCA_BASE_URL", raising=False)
    clear_catalog_cache()
    yield
    clear_catalog_cache()


def _catalog_response(models: list[dict]) -> dict:
    return {"data": models, "object": "list", "success": True}


def _catalog_transport(models: list[dict], *, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=_catalog_response(models))

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# PKCE primitives
# ---------------------------------------------------------------------------


def test_code_challenge_is_unpadded_base64url_of_sha256():
    verifier = "fixed-verifier-for-hash-check"
    challenge = code_challenge_for(verifier)
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    assert challenge == expected
    assert "=" not in challenge
    assert "+" not in challenge and "/" not in challenge


def test_verifier_and_state_are_fresh_per_attempt():
    verifiers = {generate_code_verifier() for _ in range(50)}
    states = {generate_state() for _ in range(50)}
    assert len(verifiers) == 50
    assert len(states) == 50
    assert all(len(v) >= 43 for v in verifiers)


def test_authorize_url_carries_s256_and_never_the_verifier():
    verifier = generate_code_verifier()
    state = generate_state()
    url = build_authorize_url(
        "",
        callback_url="oob",
        code_challenge=code_challenge_for(verifier),
        state=state,
        app_name="OpenHarness",
    )
    assert url.startswith("https://www.orcarouter.ai/auth?")
    assert "code_challenge_method=S256" in url
    assert f"state={state}" in url
    assert "callback_url=oob" in url
    # The verifier must never leave the process inside a URL.
    assert verifier not in url
    assert code_challenge_for(verifier) in url


def test_authorize_url_rejects_non_loopback_plaintext_callback():
    with pytest.raises(ValueError):
        build_authorize_url(
            "",
            callback_url="http://evil.example.com/cb",
            code_challenge="x",
            state="y",
        )


def test_authorize_url_allows_loopback_http_and_any_https_host():
    for callback in ("http://127.0.0.1:51733/cb", "https://example.com/cb", "oob"):
        url = build_authorize_url("", callback_url=callback, code_challenge="c", state="s")
        assert "callback_url=" in url


def test_state_comparison_is_exact():
    assert states_match("abc", "abc")
    assert not states_match("abc", "abd")
    assert not states_match("abc", None)
    assert not states_match("", "")


# ---------------------------------------------------------------------------
# Origins: auth and inference never share a path
# ---------------------------------------------------------------------------


def test_default_origins_are_distinct_and_correct():
    assert orca.resolve_auth_base() == "https://www.orcarouter.ai"
    assert orca.resolve_api_base() == "https://api.orcarouter.ai/v1"
    assert orca.exchange_url("") == "https://www.orcarouter.ai/api/v1/auth/keys"
    assert orca.authorize_url("") == "https://www.orcarouter.ai/auth"
    # The relay's /v1/auth/keys is a 404 and must never be constructed: the
    # exchange lives on the auth origin under /api/v1/auth, not on the relay.
    assert "api.orcarouter.ai" not in orca.exchange_url("")
    assert orca.exchange_url("").startswith("https://www.orcarouter.ai/api/v1/auth/keys")
    assert not orca.exchange_url("").startswith("https://api.orcarouter.ai/v1/auth/keys")


def test_shared_base_and_explicit_overrides(monkeypatch):
    monkeypatch.setenv("ORCA_BASE_URL", "https://selfhosted.example.com")
    assert orca.resolve_auth_base() == "https://selfhosted.example.com"
    assert orca.resolve_api_base() == "https://selfhosted.example.com/v1"

    monkeypatch.setenv("ORCA_AUTH_BASE_URL", "https://auth.example.com")
    monkeypatch.setenv("ORCA_API_BASE_URL", "https://relay.example.com/v1")
    assert orca.resolve_auth_base() == "https://auth.example.com"
    assert orca.resolve_api_base() == "https://relay.example.com/v1"

    # Explicit arguments win over the environment.
    assert orca.resolve_auth_base("https://explicit.example.com") == "https://explicit.example.com"


def test_remote_plaintext_origins_are_refused(monkeypatch):
    monkeypatch.setenv("ORCA_AUTH_BASE_URL", "http://www.orcarouter.ai")
    with pytest.raises(ValueError):
        orca.resolve_auth_base()
    monkeypatch.delenv("ORCA_AUTH_BASE_URL")
    monkeypatch.setenv("ORCA_API_BASE_URL", "http://api.orcarouter.ai/v1")
    with pytest.raises(ValueError):
        orca.resolve_api_base()


def test_loopback_http_allowed_for_self_hosted_development(monkeypatch):
    monkeypatch.setenv("ORCA_BASE_URL", "http://127.0.0.1:8080")
    assert orca.resolve_auth_base() == "http://127.0.0.1:8080"
    assert orca.resolve_api_base() == "http://127.0.0.1:8080/v1"


# ---------------------------------------------------------------------------
# Code exchange
# ---------------------------------------------------------------------------


def _exchange_transport(status: int, payload: dict):
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler), captured


def test_exchange_posts_to_auth_origin_with_verifier_and_s256():
    transport, captured = _exchange_transport(200, {"key": FAKE_KEY, "user_id": "1", "scope": "api"})
    credential = exchange_code("fake-code", "fake-verifier", transport=transport)

    assert credential.api_key == FAKE_KEY
    assert credential.source == "pkce"
    assert credential.scope == "api"
    assert captured["url"] == "https://www.orcarouter.ai/api/v1/auth/keys"
    body = captured["body"]
    assert body["code_verifier"] == "fake-verifier"
    assert body["code_challenge_method"] == "S256"


def test_exchange_honours_explicit_auth_override():
    transport, captured = _exchange_transport(200, {"key": FAKE_KEY, "scope": "api"})
    exchange_code("c", "v", auth_base="https://auth.internal.example", transport=transport)
    assert captured["url"] == "https://auth.internal.example/api/v1/auth/keys"


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, "invalid_request"),
        (401, "unauthorized"),
        (403, "code_rejected"),
        (429, "rate_limited"),
        (500, "exchange_failed"),
    ],
)
def test_exchange_failures_are_classified_and_secret_free(status, kind):
    transport, _ = _exchange_transport(status, {"error": "nope", "error_description": "detail"})
    with pytest.raises(OrcaRouterAuthError) as excinfo:
        exchange_code("secret-code-value", "secret-verifier-value", transport=transport)
    error = excinfo.value
    assert error.kind == kind
    assert error.status == status
    assert error.terminal is True
    # Neither half of the PKCE pair may leak through an error message.
    assert "secret-verifier-value" not in str(error)
    assert "secret-code-value" not in str(error)


def test_exchange_echoed_verifier_is_scrubbed_from_the_error():
    transport, _ = _exchange_transport(403, {"error_description": "verifier secret-verifier-value rejected"})
    with pytest.raises(OrcaRouterAuthError) as excinfo:
        exchange_code("c", "secret-verifier-value", transport=transport)
    assert "secret-verifier-value" not in str(excinfo.value)
    assert "[REDACTED]" in str(excinfo.value)


def test_exchange_429_mentions_the_key_issuance_cap():
    transport, _ = _exchange_transport(429, {})
    with pytest.raises(OrcaRouterAuthError) as excinfo:
        exchange_code("c", "v", transport=transport)
    assert "10" in str(excinfo.value)


def test_exchange_network_failure_is_not_terminal():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(OrcaRouterAuthError) as excinfo:
        exchange_code("c", "v", transport=httpx.MockTransport(handler))
    assert excinfo.value.terminal is False
    assert excinfo.value.kind == "network_error"


def test_exchange_scope_downgrade_is_refused():
    transport, _ = _exchange_transport(200, {"key": FAKE_KEY, "scope": "connector"})
    with pytest.raises(OrcaRouterAuthError) as excinfo:
        exchange_code("c", "v", transport=transport)
    assert excinfo.value.kind == "scope_downgrade"


def test_exchange_missing_key_is_an_error():
    transport, _ = _exchange_transport(200, {"scope": "api"})
    with pytest.raises(OrcaRouterAuthError):
        exchange_code("c", "v", transport=transport)


def test_exchange_unparseable_body_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    with pytest.raises(OrcaRouterAuthError):
        exchange_code("c", "v", transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# The credential seam: both adapters produce the same thing
# ---------------------------------------------------------------------------


def test_api_key_adapter_reads_the_environment(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", FAKE_KEY)
    credential = ApiKeyCredentialProvider().acquire()
    assert credential.api_key == FAKE_KEY
    assert credential.source == "api_key"


def test_api_key_adapter_reads_the_shared_store(monkeypatch):
    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    credential = ApiKeyCredentialProvider().acquire()
    assert credential.api_key == FAKE_KEY


def test_api_key_adapter_reports_a_missing_key():
    with pytest.raises(OrcaRouterAuthError) as excinfo:
        ApiKeyCredentialProvider().acquire()
    assert excinfo.value.kind == "missing_api_key"
    assert "oh auth orcarouter" in str(excinfo.value)


class _FakeAuthServer:
    """A local stand-in for the OrcaRouter consent + exchange endpoints."""

    def __init__(self, *, grant_code: str = "fake-auth-code", scope: str = "api") -> None:
        self.grant_code = grant_code
        self.scope = scope
        self.exchange_bodies: list[dict] = []
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    def __enter__(self) -> Self:
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.exchange_bodies.append(body)
                payload = json.dumps(
                    {"key": FAKE_KEY, "user_id": "42", "scope": outer.scope}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                return

        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()


def test_pkce_adapter_loopback_end_to_end_and_persists(monkeypatch):
    """Flow A: authorize URL -> local callback -> exchange -> persist."""
    from openharness.auth import orcarouter_login

    with _FakeAuthServer() as server:
        auth_base = f"http://127.0.0.1:{server.port}"
        seen: dict[str, str] = {}

        def fake_opener(url: str) -> bool:
            seen["url"] = url
            # Simulate the browser being redirected back to our listener.
            from urllib.parse import parse_qs, urlsplit

            parts = urlsplit(url)
            params = parse_qs(parts.query)
            callback = params["callback_url"][0]
            state = params["state"][0]
            threading.Thread(
                target=lambda: httpx.get(f"{callback}?code={server.grant_code}&state={state}"),
                daemon=True,
            ).start()
            return True

        monkeypatch.setattr(orcarouter_login, "_try_open_browser", fake_opener)
        provider = PkceCredentialProvider(
            flow="loopback",
            auth_base=auth_base,
            timeout=10,
            announce=lambda _message: None,
        )
        credential = provider.acquire()

    assert credential.api_key == FAKE_KEY
    assert credential.source == "pkce"
    assert credential.scope == "api"
    assert credential.user_id == "42"

    # The authorize URL went to the auth origin, not the inference origin.
    assert seen["url"].startswith(f"{auth_base}/auth?")
    assert "code_challenge_method=S256" in seen["url"]
    assert "callback_url=http%3A%2F%2F127.0.0.1" in seen["url"]

    # The exchange carried the verifier that matches the challenge.
    challenge = None
    from urllib.parse import parse_qs, urlsplit

    challenge = parse_qs(urlsplit(seen["url"]).query)["code_challenge"][0]
    body = server.exchange_bodies[0]
    assert code_challenge_for(body["code_verifier"]) == challenge
    assert body["code"] == server.grant_code

    # Persisted, and a later API-key read sees the same credential.
    assert ApiKeyCredentialProvider().acquire().api_key == FAKE_KEY


def test_pkce_loopback_rejects_state_mismatch(monkeypatch):
    from openharness.auth import orcarouter_login

    with _FakeAuthServer() as server:
        auth_base = f"http://127.0.0.1:{server.port}"

        def bad_state_opener(url: str) -> bool:
            from urllib.parse import parse_qs, urlsplit

            params = parse_qs(urlsplit(url).query)
            callback = params["callback_url"][0]
            threading.Thread(
                target=lambda: httpx.get(f"{callback}?code=stolen-code&state=wrong-state"),
                daemon=True,
            ).start()
            return True

        monkeypatch.setattr(orcarouter_login, "_try_open_browser", bad_state_opener)
        provider = PkceCredentialProvider(
            flow="loopback", auth_base=auth_base, timeout=10, announce=lambda _m: None
        )
        with pytest.raises(OrcaRouterAuthError) as excinfo:
            provider.acquire()

    assert excinfo.value.kind == "state_mismatch"
    # A rejected redirect must not exchange anything.
    assert server.exchange_bodies == []


def test_pkce_loopback_reports_denial(monkeypatch):
    from openharness.auth import orcarouter_login

    with _FakeAuthServer() as server:
        auth_base = f"http://127.0.0.1:{server.port}"

        def denying_opener(url: str) -> bool:
            from urllib.parse import parse_qs, urlsplit

            params = parse_qs(urlsplit(url).query)
            callback = params["callback_url"][0]
            state = params["state"][0]
            threading.Thread(
                target=lambda: httpx.get(f"{callback}?error=access_denied&state={state}"),
                daemon=True,
            ).start()
            return True

        monkeypatch.setattr(orcarouter_login, "_try_open_browser", denying_opener)
        provider = PkceCredentialProvider(
            flow="loopback", auth_base=auth_base, timeout=10, announce=lambda _m: None
        )
        with pytest.raises(OrcaRouterAuthError) as excinfo:
            provider.acquire()

    assert excinfo.value.kind == "access_denied"
    assert server.exchange_bodies == []


def test_pkce_loopback_times_out_without_hanging():
    provider = PkceCredentialProvider(
        flow="loopback",
        auth_base="http://127.0.0.1:9",
        timeout=0.4,
        opener=lambda _url: True,
        announce=lambda _m: None,
    )
    with pytest.raises(OrcaRouterAuthError) as excinfo:
        provider.acquire()
    assert excinfo.value.kind == "timeout"


def test_pkce_oob_flow_exchanges_the_pasted_code(monkeypatch):
    from openharness.auth import orcarouter_login as _login_module

    assert _login_module.FLOW_OOB == "oob"
    with _FakeAuthServer() as server:
        auth_base = f"http://127.0.0.1:{server.port}"
        urls: list[str] = []
        printed: list[str] = []
        provider = PkceCredentialProvider(
            flow="oob",
            auth_base=auth_base,
            timeout=10,
            opener=lambda url: urls.append(url) or True,
            prompt_for_code=lambda: server.grant_code,
            on_authorize_url=printed.append,
            announce=lambda _m: None,
        )
        credential = provider.acquire()

    assert credential.api_key == FAKE_KEY
    # Flow B asks for oob and is still bound with S256.
    assert "callback_url=oob" in urls[0]
    assert "code_challenge_method=S256" in urls[0]
    assert code_challenge_for(server.exchange_bodies[0]["code_verifier"]) == (
        __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(
            __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(urls[0]).query
        )["code_challenge"][0]
    )
    assert printed == urls


def test_pkce_oob_rejects_an_empty_code():
    provider = PkceCredentialProvider(
        flow="oob",
        auth_base="http://127.0.0.1:9",
        timeout=5,
        opener=lambda _url: True,
        prompt_for_code=lambda: "   ",
        announce=lambda _m: None,
    )
    with pytest.raises(OrcaRouterAuthError) as excinfo:
        provider.acquire()
    assert excinfo.value.kind == "missing_code"


def test_pkce_unknown_flow_is_rejected():
    with pytest.raises(ValueError):
        PkceCredentialProvider(flow="device").acquire()


def test_both_adapters_yield_the_same_credential_shape(monkeypatch):
    """The seam is auth-method agnostic: downstream only sees one shape."""
    from openharness.auth import orcarouter_login as _login_module

    assert _login_module.FLOW_OOB == "oob"
    with _FakeAuthServer() as server:
        pkce_credential = PkceCredentialProvider(
            flow="oob",
            auth_base=f"http://127.0.0.1:{server.port}",
            timeout=10,
            opener=lambda _url: True,
            prompt_for_code=lambda: server.grant_code,
            announce=lambda _m: None,
        ).acquire()

    orca.clear_credential()
    monkeypatch.setenv("ORCAROUTER_API_KEY", FAKE_KEY)
    key_credential = ApiKeyCredentialProvider().acquire()

    for credential in (pkce_credential, key_credential):
        assert isinstance(credential, OrcaRouterCredential)
        assert credential.api_key == FAKE_KEY
        # Downstream reads only api_key; source is informational.
        assert credential.masked() != FAKE_KEY


def test_masking_never_reveals_the_key():
    masked = mask_api_key(FAKE_KEY)
    assert masked != FAKE_KEY
    assert FAKE_KEY not in masked
    assert mask_api_key("") == ""
    assert mask_api_key("short") == "…"


# ---------------------------------------------------------------------------
# Credential lifecycle: durable key, terminal 401, generation safety
# ---------------------------------------------------------------------------


def test_persist_and_clear_round_trip():
    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    assert orca.current_credential_generation() == 1
    assert orca.needs_reauth() is None

    orca.clear_credential()
    assert orca.current_credential_generation() == 0
    with pytest.raises(OrcaRouterAuthError):
        ApiKeyCredentialProvider().acquire()


def test_revoked_key_is_marked_needs_reauth_without_a_refresh_attempt():
    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    generation = orca.current_credential_generation()

    assert orca.handle_auth_failure(generation=generation, reason="relay returned 401") is True
    state = orca.needs_reauth()
    assert state is not None
    assert state["needs_reauth"] is True
    # The stored secret survives: a transient failure must not destroy it.
    assert ApiKeyCredentialProvider().acquire().api_key == FAKE_KEY


def test_stale_generation_failure_cannot_poison_a_new_credential():
    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    old_generation = orca.current_credential_generation()

    # The user reauthorizes: a new generation replaces the old one.
    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY + "-new", source="pkce"))
    new_generation = orca.current_credential_generation()
    assert new_generation != old_generation

    # A late 401 from the old request must not mark the fresh credential dead.
    assert orca.handle_auth_failure(generation=old_generation) is False
    assert orca.needs_reauth() is None

    # The current generation still transitions normally.
    assert orca.handle_auth_failure(generation=new_generation) is True
    assert orca.needs_reauth() is not None


def test_successful_reauth_clears_the_reauth_flag():
    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    orca.handle_auth_failure(generation=orca.current_credential_generation())
    assert orca.needs_reauth() is not None

    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    assert orca.needs_reauth() is None


def test_resolve_credential_prefers_an_explicit_key(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-from-env-000000")
    credential = orca.resolve_credential(api_key=FAKE_KEY)
    assert credential.api_key == FAKE_KEY
    assert credential.source == "api_key"


def test_looks_like_orcarouter_key_is_only_a_shape_check():
    assert orca.looks_like_orcarouter_key(FAKE_KEY)
    assert not orca.looks_like_orcarouter_key("sk-or-other")
    assert not orca.looks_like_orcarouter_key("sk-orca-")


# ---------------------------------------------------------------------------
# Model catalog: parsing, capability filtering, fail-closed modalities
# ---------------------------------------------------------------------------

TEXT_ONLY = {
    "id": "deepseek/deepseek-v4-pro",
    "supported_endpoint_types": ["openai", "openai-response"],
    "architecture": {"input_modalities": ["text"]},
    "context_length": 1048576,
}
IMAGE_CHAT = {
    "id": "anthropic/claude-opus-4.8",
    "supported_endpoint_types": ["openai", "anthropic"],
    "architecture": {"input_modalities": ["text", "image", "file"]},
    "context_length": 1000000,
}
UNDECLARED_MODALITY = {
    "id": "vendor/mystery-model",
    "supported_endpoint_types": ["openai"],
    # No architecture block at all: capability must not be guessed.
}
EMBEDDING = {
    "id": "openai/text-embedding-3-large",
    "supported_endpoint_types": ["embeddings"],
    "architecture": {"input_modalities": ["text"]},
}
IMAGE_GEN = {
    "id": "openai/gpt-image-1",
    "supported_endpoint_types": ["image-generation"],
    "architecture": {"input_modalities": ["text"]},
}
VIDEO = {
    "id": "kling/kling-v3",
    "supported_endpoint_types": ["openai-video"],
    "architecture": {"input_modalities": ["text", "image"]},
}
RERANK = {
    "id": "vendor/some-reranker",
    "supported_endpoint_types": ["jina-rerank"],
}
AUDIO_CHAT = {
    "id": "google/gemini-3.5-flash",
    "supported_endpoint_types": ["openai", "gemini"],
    "architecture": {"input_modalities": ["text", "image", "audio", "video"]},
}

FIXTURE_MODELS = [
    TEXT_ONLY,
    IMAGE_CHAT,
    UNDECLARED_MODALITY,
    EMBEDDING,
    IMAGE_GEN,
    VIDEO,
    RERANK,
    AUDIO_CHAT,
]


def _fixture_entries() -> list[ModelEntry]:
    return parse_catalog(_catalog_response(FIXTURE_MODELS))


def test_parse_preserves_vendor_namespace_and_drops_unknown_shapes():
    entries = parse_catalog(
        _catalog_response([TEXT_ONLY, IMAGE_CHAT, {"no_id": True}, "junk", {"id": "  "}])
    )
    assert [entry.id for entry in entries] == ["deepseek/deepseek-v4-pro", "anthropic/claude-opus-4.8"]


def test_parse_rejects_a_non_object_or_missing_data():
    with pytest.raises(OrcaRouterCatalogError):
        parse_catalog([])
    with pytest.raises(OrcaRouterCatalogError):
        parse_catalog({"nope": True})


def test_chat_filter_excludes_non_text_models():
    ids = {entry.id for entry in filter_models(_fixture_entries(), "chat")}
    assert "deepseek/deepseek-v4-pro" in ids
    assert "anthropic/claude-opus-4.8" in ids
    # Non-text-only routes must never appear in a chat selector.
    assert "openai/text-embedding-3-large" not in ids
    assert "openai/gpt-image-1" not in ids
    assert "kling/kling-v3" not in ids
    assert "vendor/some-reranker" not in ids


def test_embedding_image_video_and_rerank_filters_are_strict():
    entries = _fixture_entries()
    assert [e.id for e in filter_models(entries, "embedding")] == ["openai/text-embedding-3-large"]
    assert [e.id for e in filter_models(entries, "image")] == ["openai/gpt-image-1"]
    assert [e.id for e in filter_models(entries, "video")] == ["kling/kling-v3"]
    assert [e.id for e in filter_models(entries, "rerank")] == ["vendor/some-reranker"]


def test_multimodal_filter_fails_closed_on_undeclared_models():
    entries = _fixture_entries()
    with_image = {entry.id for entry in filter_models(entries, "chat", modalities=["image"])}
    assert "anthropic/claude-opus-4.8" in with_image
    # No architecture block => capability unknown => excluded, never assumed.
    assert "vendor/mystery-model" not in with_image
    # Declared text-only => excluded from an image request.
    assert "deepseek/deepseek-v4-pro" not in with_image


def test_audio_and_video_modalities_are_matched_exactly():
    entries = _fixture_entries()
    audio = {entry.id for entry in filter_models(entries, "chat", modalities=["audio"])}
    assert audio == {"google/gemini-3.5-flash"}
    video = {entry.id for entry in filter_models(entries, "chat", modalities=["video"])}
    assert video == {"google/gemini-3.5-flash"}


def test_unknown_capability_is_rejected():
    with pytest.raises(ValueError):
        filter_models(_fixture_entries(), "telepathy")


def test_select_options_are_filtered_and_mark_the_current_model():
    options = select_options(_fixture_entries(), current="anthropic/claude-opus-4.8", capability="chat")
    values = [option["value"] for option in options]
    assert "anthropic/claude-opus-4.8" in values
    assert "openai/gpt-image-1" not in values
    assert any(option["active"] for option in options)

    image_options = select_options(_fixture_entries(), capability="chat", modalities=["image"])
    image_values = [option["value"] for option in image_options]
    assert "deepseek/deepseek-v4-pro" not in image_values
    assert "anthropic/claude-opus-4.8" in image_values


def test_select_options_drop_a_no_longer_compatible_current_value():
    options = select_options(
        _fixture_entries(), current="deepseek/deepseek-v4-pro", capability="chat", modalities=["image"]
    )
    assert "deepseek/deepseek-v4-pro" not in [option["value"] for option in options]


def test_restore_model_revalidates_against_the_new_catalog():
    entries = _fixture_entries()
    assert restore_model("anthropic/claude-opus-4.8", entries) == "anthropic/claude-opus-4.8"
    # Gone from the catalog.
    assert restore_model("vendor/removed-model", entries) == ""
    # Present but incapable of the required modality.
    assert restore_model("deepseek/deepseek-v4-pro", entries, "chat") == "deepseek/deepseek-v4-pro"
    image_entries = filter_models(entries, "chat", modalities=["image"])
    assert restore_model("deepseek/deepseek-v4-pro", image_entries) == ""


# ---------------------------------------------------------------------------
# Live discovery: authoritative on success, bounded fallback on failure
# ---------------------------------------------------------------------------


def test_fetch_models_uses_the_api_origin_and_bearer_auth():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_catalog_response(FIXTURE_MODELS))

    fetch_models(api_key=FAKE_KEY, transport=httpx.MockTransport(handler))
    assert captured["url"] == "https://api.orcarouter.ai/v1/models"
    assert captured["auth"] == f"Bearer {FAKE_KEY}"
    # Discovery never touches the auth origin.
    assert "www.orcarouter.ai" not in str(captured["url"])


def test_fetch_models_passes_the_capability_query_parameter():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_catalog_response(FIXTURE_MODELS))

    fetch_models(api_key=FAKE_KEY, capability="embedding", transport=httpx.MockTransport(handler))
    assert "capability=embedding" in str(captured["url"])

    with pytest.raises(ValueError):
        fetch_models(api_key=FAKE_KEY, capability="bogus", transport=httpx.MockTransport(handler))


def test_live_discovery_is_authoritative_and_contains_no_seed_models():
    live = [{"id": "vendor/only-live-model", "supported_endpoint_types": ["openai"]}]
    catalog = discover_catalog(api_key=FAKE_KEY, transport=_catalog_transport(live))
    ids = [entry.id for entry in catalog.entries]
    assert ids == ["vendor/only-live-model"]
    assert catalog.source == "live"
    assert catalog.degraded is False
    # A successful live catalog must not be padded with the fallback seed.
    for seed_entry in orca.SEED_MODELS:
        assert seed_entry["id"] not in ids


def test_discovery_failure_falls_back_to_the_verified_seed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("catalog down", request=request)

    catalog = discover_catalog(api_key=FAKE_KEY, transport=httpx.MockTransport(handler))
    assert catalog.source == "seed"
    assert catalog.degraded is True
    assert "Could not reach" in catalog.detail
    assert {entry.id for entry in catalog.entries} == {m["id"] for m in orca.SEED_MODELS}


def test_discovery_failure_can_be_configured_to_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    with pytest.raises(OrcaRouterCatalogError):
        discover_catalog(
            api_key=FAKE_KEY,
            include_seed_fallback=False,
            transport=httpx.MockTransport(handler),
        )


def test_auth_rejected_catalog_reports_clearly():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    catalog = discover_catalog(api_key="sk-orca-bogus", transport=httpx.MockTransport(handler))
    assert catalog.degraded is True
    assert "401" in catalog.detail


def test_catalog_size_limit_is_enforced():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000)

    with pytest.raises(OrcaRouterCatalogError):
        fetch_models(api_key=FAKE_KEY, max_bytes=100, transport=httpx.MockTransport(handler))


def test_seed_catalog_preserves_reasoning_and_modality_metadata():
    catalog = seed_catalog()
    by_id = {entry.id: entry for entry in catalog.entries}
    gpt = by_id["openai/gpt-5.5"]
    assert gpt.reasoning is True
    assert gpt.reasoning_efforts == ("low", "medium", "high", "xhigh")
    assert "image" in gpt.input_modalities
    assert gpt.supports_text_chat

    gemini = by_id["google/gemini-3.5-flash"]
    assert {"audio", "video"} <= set(gemini.input_modalities)

    deepseek = by_id["deepseek/deepseek-v4-pro"]
    assert deepseek.input_modalities == ("text",)
    # The seed is text-only and must stay out of multimodal selectors.
    assert "deepseek/deepseek-v4-pro" not in [
        option["value"] for option in select_options(catalog.entries, capability="chat", modalities=["image"])
    ]


def test_seed_metadata_enriches_live_entries_without_adding_models():
    live = [
        {"id": "openai/gpt-5.5", "supported_endpoint_types": ["openai"]},
        {"id": "vendor/other", "supported_endpoint_types": ["openai"]},
    ]
    catalog = discover_catalog(api_key=FAKE_KEY, transport=_catalog_transport(live))
    by_id = {entry.id: entry for entry in catalog.entries}
    # Verified reasoning ladder is retained on a live model that omits it.
    assert by_id["openai/gpt-5.5"].reasoning_efforts == ("low", "medium", "high", "xhigh")
    # No seed-only model is invented into a live catalog.
    assert "anthropic/claude-opus-4.8" not in by_id


def test_live_catalog_rejects_seed_contamination_flag():
    with pytest.raises(ValueError):
        ModelCatalog(entries=(), source="live", seed_contaminated=True)


# ---------------------------------------------------------------------------
# Caching and degraded state
# ---------------------------------------------------------------------------


def test_cache_serves_the_live_catalog_within_the_ttl():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_catalog_response(FIXTURE_MODELS))

    transport = httpx.MockTransport(handler)
    first = cached_catalog(api_key=FAKE_KEY, transport=transport)
    second = cached_catalog(api_key=FAKE_KEY, transport=transport)
    assert first.source == "live" and second.source == "live"
    assert calls["n"] == 1


def test_cache_never_promotes_a_seed_to_live():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    transport = httpx.MockTransport(handler)
    first = cached_catalog(api_key=FAKE_KEY, transport=transport)
    assert first.source == "seed" and first.degraded is True

    second = cached_catalog(api_key=FAKE_KEY, transport=transport)
    assert second.source == "seed"
    assert second.degraded is True


def test_cache_falls_back_to_last_known_good_live_catalog():
    live = [{"id": "vendor/live-model", "supported_endpoint_types": ["openai"]}]
    transport_ok = _catalog_transport(live)
    good = cached_catalog(api_key=FAKE_KEY, transport=transport_ok)
    assert good.source == "live"

    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    degraded = cached_catalog(api_key=FAKE_KEY, transport=httpx.MockTransport(failing), force_refresh=True)
    assert degraded.degraded is True
    # Last known-good live entries are retained rather than replaced by the seed.
    assert [entry.id for entry in degraded.entries] == ["vendor/live-model"]


def test_catalog_metadata_documents_seed_provenance():
    metadata = orca.catalog_metadata()
    assert metadata["source"] == "https://api.orcarouter.ai/v1/models"
    assert set(metadata["models"]) == {m["id"] for m in orca.SEED_MODELS}


# ---------------------------------------------------------------------------
# Request-path integration: 401 vs 403 handling
# ---------------------------------------------------------------------------


def test_only_a_401_is_treated_as_a_reauthentication_requirement():
    """A 403 (key scope / model access) says nothing about credential validity."""
    from openharness.api.errors import AuthenticationFailure
    from openharness.engine.query import _record_orcarouter_auth_failure

    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    context = _FakeQueryContext(provider="orcarouter")

    forbidden = AuthenticationFailure("model access denied")
    forbidden.status_code = 403  # type: ignore[attr-defined]
    _record_orcarouter_auth_failure(context, forbidden)
    assert orca.needs_reauth() is None

    unauthorized = AuthenticationFailure("relay returned 401")
    unauthorized.status_code = 401  # type: ignore[attr-defined]
    _record_orcarouter_auth_failure(context, unauthorized)
    state = orca.needs_reauth()
    assert state is not None
    assert "401" in state["reason"]


def test_request_path_ignores_failures_for_other_providers():
    from openharness.api.errors import AuthenticationFailure
    from openharness.engine.query import _record_orcarouter_auth_failure

    orca.persist_credential(OrcaRouterCredential(api_key=FAKE_KEY, source="pkce"))
    exc = AuthenticationFailure("401")
    exc.status_code = 401  # type: ignore[attr-defined]

    _record_orcarouter_auth_failure(_FakeQueryContext(provider="openai"), exc)
    assert orca.needs_reauth() is None


def test_query_context_exposes_settings_for_credential_attribution():
    from openharness.engine.query import QueryContext

    assert "settings" in QueryContext.__dataclass_fields__


class _FakeQueryContext:
    """Minimal stand-in exposing the one attribute the hook reads."""

    def __init__(self, provider: str) -> None:
        self.settings = type("S", (), {"provider": provider})()
