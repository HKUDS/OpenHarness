"""Tests for image_to_text tool and multimodal detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.api.provider import is_model_multimodal
from openharness.config.settings import VisionModelConfig
from openharness.tools.base import ToolExecutionContext
from openharness.tools.image_to_text_tool import ImageToTextTool, ImageToTextToolInput


# ---------------------------------------------------------------------------
# is_model_multimodal tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # Anthropic Claude 3+ (multimodal)
        ("claude-sonnet-4-6", True),
        ("claude-opus-4-6", True),
        ("claude-haiku-4-5", True),
        ("claude-3-5-sonnet-20241022", True),
        ("claude-3-opus-20240229", True),
        ("claude-3-haiku-20240307", True),
        # OpenAI multimodal
        ("gpt-4o", True),
        ("gpt-4o-mini", True),
        ("o1-mini", True),
        ("o3-mini", True),
        ("o4-mini", True),
        # Google Gemini
        ("gemini-2.5-flash", True),
        ("gemini-2.0-flash", True),
        ("gemini-pro-vision", True),
        # Qwen VL
        ("qwen-vl-max", True),
        ("qwen2.5-vl-72b", True),
        ("qvq-72b-preview", True),
        # DeepSeek VL
        ("deepseek-vl2", True),
        # Other multimodal
        ("llava-v1.6-34b", True),
        ("pixtral-12b", True),
        ("step-2-16k", True),
        ("step-1v-32k", True),
        ("kimi-k2.5", True),
        # Non-multimodal models
        ("claude-2.1", False),
        ("gpt-4", False),
        ("gpt-3.5-turbo", False),
        ("deepseek-chat", False),
        ("deepseek-reasoner", False),
        ("qwen-turbo", False),
        ("qwen-plus", False),
        ("kimi-k2", False),
        ("step-1-8k", False),
        ("glm-4", False),
        ("gemini-1.0-pro", False),
        ("unknown-model-123", False),
        ("", False),
        # With provider prefix
        ("anthropic/claude-sonnet-4-6", True),
        ("openai/gpt-4o", True),
        ("openai/gpt-4", False),
    ],
)
def test_is_model_multimodal(model: str, expected: bool) -> None:
    assert is_model_multimodal(model) == expected


# ---------------------------------------------------------------------------
# ImageToTextTool input validation tests
# ---------------------------------------------------------------------------

class TestImageToTextToolInput:
    """Validate the tool's input model."""

    def test_valid_image_data(self) -> None:
        inp = ImageToTextToolInput(
            image_data="iVBORw0KGgo=",
            media_type="image/png",
        )
        assert inp.image_data == "iVBORw0KGgo="
        assert inp.media_type == "image/png"
        assert inp.prompt  # default prompt

    def test_valid_image_path(self) -> None:
        inp = ImageToTextToolInput(
            image_path="/tmp/test.png",
        )
        assert inp.image_path == "/tmp/test.png"
        assert inp.image_data is None

    def test_default_prompt(self) -> None:
        inp = ImageToTextToolInput(image_data="data")
        assert "image" in inp.prompt.lower()

    def test_custom_prompt(self) -> None:
        inp = ImageToTextToolInput(
            image_data="data",
            prompt="Extract all text from this image",
        )
        assert inp.prompt == "Extract all text from this image"

    def test_max_tokens_range(self) -> None:
        # Default
        inp = ImageToTextToolInput(image_data="data")
        assert inp.max_tokens == 2048

        # Custom valid
        inp = ImageToTextToolInput(image_data="data", max_tokens=4096)
        assert inp.max_tokens == 4096

    def test_neither_image_data_nor_path(self) -> None:
        """Both fields are optional in the model, but the tool will error."""
        inp = ImageToTextToolInput()
        assert inp.image_data is None
        assert inp.image_path is None


# ---------------------------------------------------------------------------
# ImageToTextTool execution tests (no real API calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_no_input(tmp_path: Path) -> None:
    """Tool returns error when neither image_data nor image_path is provided."""
    tool = ImageToTextTool()
    context = ToolExecutionContext(cwd=tmp_path)
    result = await tool.execute(
        ImageToTextToolInput(),
        context,
    )
    assert result.is_error
    assert "provide either" in result.output


@pytest.mark.asyncio
async def test_execute_nonexistent_path(tmp_path: Path) -> None:
    """Tool returns error when image_path does not exist."""
    tool = ImageToTextTool()
    context = ToolExecutionContext(cwd=tmp_path)
    result = await tool.execute(
        ImageToTextToolInput(image_path="/nonexistent/path/image.png"),
        context,
    )
    assert result.is_error
    assert "provide either" in result.output


@pytest.mark.asyncio
async def test_execute_no_vision_config(tmp_path: Path) -> None:
    """Tool returns error when vision model is not configured."""
    tool = ImageToTextTool()
    context = ToolExecutionContext(
        cwd=tmp_path,
        metadata={"vision_model_config": {}},
    )
    result = await tool.execute(
        ImageToTextToolInput(image_data="iVBORw0KGgo="),
        context,
    )
    assert result.is_error
    assert "vision model is not configured" in result.output


@pytest.mark.asyncio
async def test_execute_with_image_path(tmp_path: Path) -> None:
    """Tool reads a real image file and attempts to describe it."""
    # Create a minimal valid PNG file
    png_path = tmp_path / "test_image.png"
    # Minimal valid PNG (1x1 pixel, white)
    minimal_png = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x08, 0xD7, 0x63, 0x60, 0x60, 0x00, 0x00,
        0x00, 0x04, 0x00, 0x01, 0x27, 0x34, 0x27, 0x0A,
        0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,  # IEND chunk
        0xAE, 0x42, 0x60, 0x82,
    ])
    png_path.write_bytes(minimal_png)

    tool = ImageToTextTool()
    context = ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "vision_model_config": {
                "model": "gpt-4o",
                "api_key": "test-key",
                "base_url": "",
            }
        },
    )
    result = await tool.execute(
        ImageToTextToolInput(image_path=str(png_path)),
        context,
    )
    # Should fail at API call (not at file reading), since the API key is fake
    assert result.is_error
    assert "vision model error" in result.output


@pytest.mark.asyncio
async def test_is_read_only() -> None:
    """image_to_text is a read-only tool."""
    tool = ImageToTextTool()
    assert tool.is_read_only(ImageToTextToolInput(image_data="data"))


# ---------------------------------------------------------------------------
# VisionModelConfig tests
# ---------------------------------------------------------------------------

class TestVisionModelConfig:
    """Validate the VisionModelConfig model."""

    def test_default_empty(self) -> None:
        cfg = VisionModelConfig()
        assert cfg.model == ""
        assert cfg.api_key == ""
        assert cfg.base_url == ""
        assert not cfg.is_configured

    def test_configured(self) -> None:
        cfg = VisionModelConfig(
            model="gpt-4o",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        )
        assert cfg.is_configured
        assert cfg.model == "gpt-4o"
        assert cfg.api_key == "sk-test"

    def test_partial_not_configured(self) -> None:
        cfg = VisionModelConfig(model="gpt-4o")
        assert not cfg.is_configured

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENHARNESS_VISION_MODEL", "gpt-4o")
        monkeypatch.setenv("OPENHARNESS_VISION_API_KEY", "sk-env-key")
        monkeypatch.setenv("OPENHARNESS_VISION_BASE_URL", "https://api.example.com/v1")

        cfg = VisionModelConfig.from_env()
        assert cfg.model == "gpt-4o"
        assert cfg.api_key == "sk-env-key"
        assert cfg.base_url == "https://api.example.com/v1"
        assert cfg.is_configured

    def test_from_env_partial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENHARNESS_VISION_MODEL", "gpt-4o")
        monkeypatch.delenv("OPENHARNESS_VISION_API_KEY", raising=False)

        cfg = VisionModelConfig.from_env()
        assert not cfg.is_configured


# ---------------------------------------------------------------------------
# Tool registry integration test
# ---------------------------------------------------------------------------

def test_tool_registered() -> None:
    """image_to_text tool is registered in the default registry."""
    from openharness.tools import create_default_tool_registry

    registry = create_default_tool_registry()
    tool = registry.get("image_to_text")
    assert tool is not None
    assert tool.name == "image_to_text"
    assert "vision" in tool.description.lower()
    assert tool.input_model.__name__ == "ImageToTextToolInput"
    assert tool.input_model.__module__ == "openharness.tools.image_to_text_tool"
