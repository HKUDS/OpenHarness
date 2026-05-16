"""Tests for the image_generation tool."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from openharness.config.settings import ImageGenerationConfig
from openharness.tools.base import ToolExecutionContext
from openharness.tools.image_generation_tool import ImageGenerationTool, ImageGenerationToolInput


class _FakeStreamResponse:
    def __init__(self, *, status_code: int = 200, lines: list[str] | None = None, body: str = "") -> None:
        self.status_code = status_code
        self._lines = lines or []
        self._body = body.encode("utf-8")

    async def __aenter__(self) -> "_FakeStreamResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def aread(self) -> bytes:
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeAsyncClient:
    def __init__(self, response: _FakeStreamResponse, sink: dict[str, Any]) -> None:
        self._response = response
        self._sink = sink

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]):
        self._sink["method"] = method
        self._sink["url"] = url
        self._sink["headers"] = headers
        self._sink["json"] = json
        return self._response


def _b64url(data: dict[str, object]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _fake_codex_token() -> str:
    payload = {"https://api.openai.com/auth": {"chatgpt_account_id": "acct_test"}}
    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(payload)}.sig"


@pytest.mark.asyncio
async def test_execute_requires_api_key_for_openai(tmp_path: Path) -> None:
    tool = ImageGenerationTool()
    result = await tool.execute(
        ImageGenerationToolInput(prompt="a cat", provider="openai"),
        ToolExecutionContext(cwd=tmp_path, metadata={"image_generation_config": {}}),
    )
    assert result.is_error
    assert "API key is not configured" in result.output


@pytest.mark.asyncio
async def test_execute_generate_writes_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_bytes = b"fake-png"
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    async def fake_generate_images(arguments, model, api_key, base_url):
        assert arguments.prompt == "a cat"
        assert model == "gpt-image-2"
        assert api_key == "test-key"
        assert base_url == ""
        return [image_b64]

    monkeypatch.setattr(ImageGenerationTool, "_generate_images", staticmethod(fake_generate_images))

    tool = ImageGenerationTool()
    result = await tool.execute(
        ImageGenerationToolInput(prompt="a cat", output_path="assets/cat.png", provider="openai"),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={"image_generation_config": {"api_key": "test-key", "model": "gpt-image-2"}},
        ),
    )

    out = tmp_path / "assets" / "cat.png"
    assert not result.is_error
    assert out.read_bytes() == image_bytes
    assert result.metadata["paths"] == [str(out)]
    assert result.metadata["provider"] == "openai"


@pytest.mark.asyncio
async def test_execute_codex_hosted_generation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_bytes = b"codex-png"
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    sink: dict[str, Any] = {}
    response = _FakeStreamResponse(
        lines=[
            'data: {"type":"response.output_item.done","item":{"id":"ig_1","type":"image_generation_call","status":"completed","revised_prompt":"blue icon","result":"%s"}}' % image_b64,
            "",
            'data: {"type":"response.completed","response":{"status":"completed"}}',
            "",
        ]
    )
    monkeypatch.setattr(
        "openharness.tools.image_generation_tool.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(response, sink),
    )

    tool = ImageGenerationTool()
    result = await tool.execute(
        ImageGenerationToolInput(prompt="a blue icon", output_path="icon.png", provider="codex"),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={
                "image_generation_config": {
                    "codex_auth_token": _fake_codex_token(),
                    "codex_model": "gpt-5.4",
                }
            },
        ),
    )

    out = tmp_path / "icon.png"
    assert not result.is_error
    assert out.read_bytes() == image_bytes
    assert result.metadata["provider"] == "codex"
    assert result.metadata["revised_prompt"] == "blue icon"
    assert sink["url"].endswith("/codex/responses")
    assert sink["json"]["tools"] == [{"type": "image_generation", "output_format": "png"}]
    assert sink["json"]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_auto_provider_prefers_codex_when_token_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_b64 = base64.b64encode(b"codex").decode("ascii")

    async def fake_codex(self, arguments, config):
        return [image_b64], None

    monkeypatch.setattr(ImageGenerationTool, "_generate_with_codex", fake_codex)

    tool = ImageGenerationTool()
    result = await tool.execute(
        ImageGenerationToolInput(prompt="a cat", output_path="cat.png"),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={"image_generation_config": {"codex_auth_token": _fake_codex_token()}},
        ),
    )

    assert not result.is_error
    assert result.metadata["provider"] == "codex"


@pytest.mark.asyncio
async def test_execute_refuses_overwrite_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = tmp_path / "image.png"
    out.write_bytes(b"existing")
    image_b64 = base64.b64encode(b"new").decode("ascii")

    async def fake_generate_images(arguments, model, api_key, base_url):
        return [image_b64]

    monkeypatch.setattr(ImageGenerationTool, "_generate_images", staticmethod(fake_generate_images))

    tool = ImageGenerationTool()
    result = await tool.execute(
        ImageGenerationToolInput(prompt="a cat", output_path=str(out), provider="openai"),
        ToolExecutionContext(cwd=tmp_path, metadata={"image_generation_config": {"api_key": "test"}}),
    )

    assert result.is_error
    assert "output already exists" in result.output
    assert out.read_bytes() == b"existing"


def test_resolve_output_paths_multiple(tmp_path: Path) -> None:
    paths = ImageGenerationTool._resolve_output_paths(
        ImageGenerationToolInput(output_path="hero.png", n=2),
        tmp_path,
    )
    assert paths == [tmp_path / "hero-1.png", tmp_path / "hero-2.png"]


def test_image_generation_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_IMAGE_GENERATION_PROVIDER", "openai")
    monkeypatch.setenv("OPENHARNESS_IMAGE_GENERATION_MODEL", "gpt-image-1")
    monkeypatch.setenv("OPENHARNESS_IMAGE_GENERATION_API_KEY", "sk-test")
    monkeypatch.setenv("OPENHARNESS_IMAGE_GENERATION_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENHARNESS_IMAGE_GENERATION_CODEX_MODEL", "gpt-5.4")

    cfg = ImageGenerationConfig.from_env()

    assert cfg.provider == "openai"
    assert cfg.model == "gpt-image-1"
    assert cfg.api_key == "sk-test"
    assert cfg.base_url == "https://example.test/v1"
    assert cfg.codex_model == "gpt-5.4"
    assert cfg.is_configured
