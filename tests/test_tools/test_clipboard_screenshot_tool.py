"""Tests for the clipboard_screenshot tool."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest import mock

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.clipboard_screenshot_tool import (
    ClipboardScreenshotTool,
    ClipboardScreenshotToolInput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_png_bytes() -> bytes:
    """Return valid minimal PNG bytes for testing. Skip if Pillow not installed."""
    try:
        from PIL import Image as _Image  # type: ignore[import-untyped]
        import io as _io

        buf = _io.BytesIO()
        img = _Image.new("RGB", (10, 10), color="red")
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        pytest.skip("Pillow not installed")



def _make_ctx(cwd: Path | None = None) -> ToolExecutionContext:
    return ToolExecutionContext(cwd=cwd or Path.cwd())


# ---------------------------------------------------------------------------
# Basic tool properties
# ---------------------------------------------------------------------------


def test_tool_name_and_description():
    tool = ClipboardScreenshotTool()
    assert tool.name == "clipboard_screenshot"
    assert "system clipboard" in tool.description.lower()


def test_input_model_is_pydantic():
    inp = ClipboardScreenshotToolInput()
    assert inp.output_format == "base64"
    assert inp.save_path is None
    assert inp.description_prompt is None


def test_is_read_only():
    tool = ClipboardScreenshotTool()
    assert tool.is_read_only(ClipboardScreenshotToolInput()) is True


def test_api_schema_generation():
    tool = ClipboardScreenshotTool()
    schema = tool.to_api_schema()
    assert schema["name"] == "clipboard_screenshot"
    assert "input_schema" in schema


# ---------------------------------------------------------------------------
# output_format = "base64"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base64_output(tmp_path: Path):
    tool = ClipboardScreenshotTool()
    png = _fake_png_bytes()

    with mock.patch.object(
        tool,
        "_read_clipboard_image",
        return_value=png,
    ):
        result = await tool.execute(
            ClipboardScreenshotToolInput(output_format="base64"),
            _make_ctx(tmp_path),
        )

    assert not result.is_error
    assert "Clipboard image captured" in result.output
    meta = result.metadata
    assert meta["size_bytes"] == len(png)
    assert meta["media_type"] == "image/png"
    # Verify it's valid base64
    decoded = base64.b64decode(meta["image_data"])
    assert decoded == png


# ---------------------------------------------------------------------------
# output_format = "file"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_output_default_path(tmp_path: Path):
    tool = ClipboardScreenshotTool()
    png = _fake_png_bytes()

    with mock.patch.object(
        tool,
        "_read_clipboard_image",
        return_value=png,
    ):
        result = await tool.execute(
            ClipboardScreenshotToolInput(output_format="file"),
            _make_ctx(tmp_path),
        )

    assert not result.is_error
    assert "Saved clipboard image" in result.output
    written_path = Path(result.metadata["path"])
    assert written_path.name == "clipboard_screenshot.png"
    assert written_path.read_bytes() == png


@pytest.mark.asyncio
async def test_file_output_custom_path(tmp_path: Path):
    tool = ClipboardScreenshotTool()
    png = _fake_png_bytes()
    custom = tmp_path / "sub" / "my_screenshot.png"

    with mock.patch.object(
        tool,
        "_read_clipboard_image",
        return_value=png,
    ):
        result = await tool.execute(
            ClipboardScreenshotToolInput(
                output_format="file",
                save_path=str(custom),
            ),
            _make_ctx(tmp_path),
        )

    assert not result.is_error
    assert custom.read_bytes() == png


# ---------------------------------------------------------------------------
# output_format = "text" (vision model)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_output_no_vision_config():
    tool = ClipboardScreenshotTool()
    png = _fake_png_bytes()
    ctx = _make_ctx()
    ctx.metadata["vision_model_config"] = {}  # key exists but empty → no fallback

    with mock.patch.object(
        tool,
        "_read_clipboard_image",
        return_value=png,
    ):
        result = await tool.execute(
            ClipboardScreenshotToolInput(output_format="text"),
            ctx,
        )

    assert result.is_error
    assert "vision model" in result.output.lower()


@pytest.mark.asyncio
async def test_text_output_with_vision_config():
    tool = ClipboardScreenshotTool()
    png = _fake_png_bytes()
    ctx = _make_ctx()
    ctx.metadata["vision_model_config"] = {
        "model": "gpt-4o",
        "api_key": "sk-fake",
        "base_url": "",
    }

    fake_description = "A screenshot of a terminal window showing a Python traceback."

    with mock.patch.object(
        tool,
        "_read_clipboard_image",
        return_value=png,
    ):
        with mock.patch.object(
            tool,
            "_call_vision",
            return_value=fake_description,
        ):
            result = await tool.execute(
                ClipboardScreenshotToolInput(output_format="text"),
                ctx,
            )

    assert not result.is_error
    assert fake_description in result.output


# ---------------------------------------------------------------------------
# Error case: no image in clipboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_image_in_clipboard():
    tool = ClipboardScreenshotTool()

    with mock.patch.object(
        tool,
        "_read_clipboard_image",
        return_value=None,
    ):
        result = await tool.execute(
            ClipboardScreenshotToolInput(),
            _make_ctx(),
        )

    assert result.is_error
    assert "no image" in result.output.lower()


# ---------------------------------------------------------------------------
# _read_clipboard_pil: unit tests
# ---------------------------------------------------------------------------


def test_read_clipboard_pil_no_pillow():
    """When Pillow is not installed, return None."""
    with mock.patch.dict("sys.modules", {"PIL": None}):
        result = ClipboardScreenshotTool._read_clipboard_pil()
        assert result is None


def test_read_clipboard_pil_no_image():
    """When clipboard has no image, ImageGrab returns None."""
    with mock.patch("PIL.ImageGrab.grabclipboard", return_value=None):
        result = ClipboardScreenshotTool._read_clipboard_pil()
        assert result is None


def test_read_clipboard_pil_with_image():
    """When clipboard has an image, return PNG bytes."""
    fake_png = _fake_png_bytes()  # real PNG from a real PIL image for realism

    mock_img = mock.MagicMock()
    mock_img.mode = "RGBA"

    def _mock_save(buf, format=None):
        buf.write(fake_png)

    mock_img.save = _mock_save

    with mock.patch("PIL.ImageGrab.grabclipboard", return_value=mock_img):
        result = ClipboardScreenshotTool._read_clipboard_pil()

    assert result is not None
    assert result == fake_png


# ---------------------------------------------------------------------------
# _read_clipboard_powershell: unit tests
# ---------------------------------------------------------------------------


def test_powershell_no_powershell_exe():
    """When powershell.exe is not found, return None."""
    with (
        mock.patch(
            "openharness.tools.clipboard_screenshot_tool._find_windows_powershell",
            return_value=None,
        ),
    ):
        result = ClipboardScreenshotTool._read_clipboard_powershell()
        assert result is None


def test_powershell_no_image_in_clipboard():
    """When clipboard is empty, PowerShell outputs NO_IMAGE."""
    fake_ps = Path(r"C:\fake\powershell.exe")

    with (
        mock.patch(
            "openharness.tools.clipboard_screenshot_tool._find_windows_powershell",
            return_value=fake_ps,
        ),
        mock.patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = mock.MagicMock(
            stdout="NO_IMAGE", stderr="", returncode=0
        )
        result = ClipboardScreenshotTool._read_clipboard_powershell()
        assert result is None


def test_powershell_image_found(tmp_path: Path):
    """When clipboard has an image, PowerShell saves it and we read it."""
    import subprocess as _subprocess

    png = _fake_png_bytes()
    tmp_file = tmp_path / "test_clip.png"
    tmp_file.write_bytes(png)

    fake_ps = Path(r"C:\fake\powershell.exe")

    fake_result = _subprocess.CompletedProcess(
        args=[], returncode=0, stdout="OK", stderr=""
    )

    with (
        mock.patch(
            "openharness.tools.clipboard_screenshot_tool._find_windows_powershell",
            return_value=fake_ps,
        ),
        mock.patch("tempfile.mkstemp", return_value=(999, str(tmp_file))),
        mock.patch(
            "openharness.tools.clipboard_screenshot_tool.subprocess.run",
            return_value=fake_result,
        ),
        mock.patch("os.close"),  # suppress OSError from fd=999 on Linux
    ):
        result = ClipboardScreenshotTool._read_clipboard_powershell()

    assert result == png


# ---------------------------------------------------------------------------
# macOS osascript: unit tests
# ---------------------------------------------------------------------------


def test_macos_osascript_not_found():
    with mock.patch("shutil.which", return_value=None):
        result = ClipboardScreenshotTool._read_clipboard_macos_osascript()
        assert result is None


def test_macos_osascript_no_image():
    with (
        mock.patch("shutil.which", return_value="/usr/bin/osascript"),
        mock.patch("subprocess.run") as mock_run,
        mock.patch("tempfile.mkstemp", return_value=(888, "/tmp/oh_test.png")),
    ):
        mock_run.return_value = mock.MagicMock(
            stdout="NO_IMAGE", stderr="", returncode=0
        )
        result = ClipboardScreenshotTool._read_clipboard_macos_osascript()
        assert result is None


# ---------------------------------------------------------------------------
# Linux xclip / wl-paste: unit tests
# ---------------------------------------------------------------------------


def test_xclip_not_found():
    with mock.patch("shutil.which", return_value=None):
        result = ClipboardScreenshotTool._read_clipboard_xclip()
        assert result is None


def test_xclip_image_found():
    png = _fake_png_bytes()

    with (
        mock.patch("shutil.which", return_value="/usr/bin/xclip"),
        mock.patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout=png
        )
        result = ClipboardScreenshotTool._read_clipboard_xclip()
        assert result == png


def test_wl_paste_not_found():
    with mock.patch("shutil.which", return_value=None):
        result = ClipboardScreenshotTool._read_clipboard_wl_paste()
        assert result is None


def test_wl_paste_image_found():
    png = _fake_png_bytes()

    with (
        mock.patch("shutil.which", return_value="/usr/bin/wl-paste"),
        mock.patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout=png
        )
        result = ClipboardScreenshotTool._read_clipboard_wl_paste()
        assert result == png


# ---------------------------------------------------------------------------
# Tool registry integration
# ---------------------------------------------------------------------------


def test_registry_includes_clipboard_screenshot():
    from openharness.tools import create_default_tool_registry

    registry = create_default_tool_registry()
    tool = registry.get("clipboard_screenshot")
    assert tool is not None
    assert tool.name == "clipboard_screenshot"