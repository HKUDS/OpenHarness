"""Live OrcaRouter checks that exercise the implemented provider path.

These tests talk to the real OrcaRouter service through the code this change
adds — the credential seam (``resolve_credential``), the origin resolver
(``resolve_api_base``), the catalog discovery the model selector uses, and the
OpenAI-compatible client the agent loop already uses for gateway providers.
They are skipped unless ``ORCAROUTER_API_KEY`` is present, so the default suite
stays hermetic.

Run with:
    ORCAROUTER_API_KEY=... uv run pytest -q tests/test_api/test_orcarouter_live.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

from openharness.api import orcarouter

pytestmark = pytest.mark.skipif(
    not os.environ.get("ORCAROUTER_API_KEY", "").strip(),
    reason="live OrcaRouter checks need ORCAROUTER_API_KEY",
)


def _credential_key() -> str:
    """Resolve the key through the credential seam, not from the environment."""
    try:
        return orcarouter.resolve_credential().api_key
    except orcarouter.OrcaRouterError as exc:
        pytest.skip(f"no usable OrcaRouter credential: {type(exc).__name__}")


def _live_catalog(*, capability: str = "chat") -> orcarouter.ModelCatalog:
    """Discover the catalog for this credential, exactly as the UI does."""
    try:
        return orcarouter.cached_catalog(
            capability=capability,
            api_key=_credential_key(),
            force_refresh=True,
        )
    except orcarouter.OrcaRouterCatalogError as exc:
        pytest.skip(f"OrcaRouter catalog unavailable from this environment: {type(exc).__name__}")


def test_live_models_catalog_matches_the_configured_origin() -> None:
    """The selector's catalog comes from the configured origin's /v1/models."""
    api_base = orcarouter.resolve_api_base()
    assert api_base.startswith("https://api.orcarouter.ai")
    assert "/v1" in api_base

    catalog = _live_catalog()

    # A live success is authoritative: no seed entry may be mixed in.
    assert catalog.source == "live"
    assert catalog.degraded is False
    ids = [entry.id for entry in catalog.entries]
    assert ids, "live catalog returned no chat models"

    # Model ids are returned verbatim, with the vendor namespace preserved.
    assert any("/" in model_id for model_id in ids)

    # The origin's `?capability=chat` query is best-effort, so the client-side
    # capability filter is the authoritative guard for the selector.
    options = orcarouter.select_options(catalog.entries, capability="chat")
    assert options
    by_id = {entry.id: entry for entry in catalog.entries}
    for option in options:
        entry = by_id[option["value"]]
        assert entry.endpoint_types
        assert entry.supports_text_chat
        assert not set(entry.endpoint_types) <= orcarouter.NON_TEXT_ENDPOINT_TYPES


def test_live_text_selection_is_the_authoritative_filtered_list() -> None:
    """Every text option is chat-capable; non-chat routes are filtered out."""
    catalog = _live_catalog()
    options = orcarouter.select_options(catalog.entries, capability="chat")
    assert options

    # Every offered model exposes a text endpoint type.
    by_id = {entry.id: entry for entry in catalog.entries}
    for option in options:
        assert by_id[option["value"]].supports_text_chat

    # Any non-chat route in the payload (an endpoint type that is *only*
    # non-text) must have been dropped from the selector's options.
    rejected = {
        entry.id
        for entry in catalog.entries
        if set(entry.endpoint_types) <= orcarouter.NON_TEXT_ENDPOINT_TYPES
        or not entry.endpoint_types
    }
    assert not (rejected & {option["value"] for option in options})

    # Embedding/image/video/rerank routes must never appear either.
    for entry in catalog.entries:
        if set(entry.endpoint_types) & orcarouter.NON_TEXT_ENDPOINT_TYPES:
            assert entry.id not in {option["value"] for option in options} or entry.supports_text_chat


def test_live_multimodal_selection_is_fail_closed() -> None:
    """Image-capable options all declare image input in the live metadata."""
    catalog = _live_catalog()
    options = orcarouter.select_options(catalog.entries, capability="chat", modalities=["image"])
    by_id = {entry.id: entry for entry in catalog.entries}
    for option in options:
        assert by_id[option["value"]].accepts_modality("image")
    text_only = [
        entry.id
        for entry in catalog.entries
        if entry.supports_text_chat and not entry.accepts_modality("image")
    ]
    assert not (set(text_only) & {option["value"] for option in options})


def test_live_inference_through_the_implemented_provider_path() -> None:
    """One real inference call using the credential seam and API base resolver."""
    from openharness.api.client import ApiMessageCompleteEvent, ApiMessageRequest
    from openharness.api.openai_client import OpenAICompatibleClient
    from openharness.engine.messages import ConversationMessage, TextBlock

    api_key = _credential_key()
    assert api_key
    assert orcarouter.looks_like_orcarouter_key(api_key)

    catalog = _live_catalog()
    options = [str(option["value"]) for option in orcarouter.select_options(catalog.entries, capability="chat")]
    if not options:
        pytest.skip("this credential exposes no chat-capable model")

    async def _call(model: str) -> str:
        client = OpenAICompatibleClient(
            api_key=api_key,
            base_url=orcarouter.resolve_api_base(),
        )
        try:
            request = ApiMessageRequest(
                model=model,
                messages=[
                    ConversationMessage(
                        role="user",
                        content=[TextBlock(text="Reply with the single word: OK")],
                    )
                ],
                max_tokens=256,
            )
            text = ""
            async for event in client.stream_message(request):
                if isinstance(event, ApiMessageCompleteEvent):
                    text = "".join(
                        block.text for block in event.message.content if isinstance(block, TextBlock)
                    )
            return text
        finally:
            await client.close()

    # Walk the credential's own options: a per-model scope restriction is a
    # property of the key, not a failure of the provider path, so the check
    # passes as soon as one advertised chat model answers.
    failures: list[str] = []
    for model in options:
        try:
            text = asyncio.run(_call(model))
        except Exception as exc:  # noqa: BLE001 - the reason is reported below
            failures.append(f"{model}: {type(exc).__name__}")
            continue
        assert text.strip(), f"the provider path returned an empty completion for {model}"
        assert api_key not in text
        return

    pytest.fail(f"no live chat model could be called from this credential: {failures}")
