"""Clipboard screenshot tool — read images from the system clipboard.

Supports Windows (PowerShell / CMD), macOS, and Linux with automatic
platform detection and multi-tier fallback. The tool can return the
clipboard image as base64 data, save it to a file, or auto-describe
it via a configured vision model.
"""

from __future__ import annotations

import base64
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from openharness.platforms import get_platform
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic input model
# ---------------------------------------------------------------------------


class ClipboardScreenshotToolInput(BaseModel):
    """Arguments for clipboard screenshot capture."""

    output_format: Literal["base64", "file", "text"] = Field(
        default="base64",
        description=(
            "Output format: 'base64' returns raw base64-encoded PNG data "
            "(pass to image_to_text for analysis), 'file' saves to disk and "
            "returns the path, 'text' auto-describes the image via a "
            "configured vision model and returns the description text."
        ),
    )
    save_path: str | None = Field(
        default=None,
        description=(
            "File path when output_format is 'file'. "
            "Defaults to 'clipboard_screenshot.png' in the current working directory."
        ),
    )
    description_prompt: str | None = Field(
        default=None,
        description="Custom instruction for vision description when output_format is 'text'.",
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


class ClipboardScreenshotTool(BaseTool):
    """Read an image from the system clipboard.

    Works regardless of where the screenshot was taken (browser, terminal,
    desktop, IDE, etc.) — as long as the image is in the system clipboard.
    """

    name = "clipboard_screenshot"
    description = (
        "Read an image from the system clipboard (screenshot or copied image) "
        "and return it as base64-encoded PNG data, save it to a file, or "
        "auto-describe it via a configured vision model. "
        "Use this when the user has taken a screenshot or copied an image and "
        "wants the AI to see and process it. The tool works on Windows, macOS, "
        "and Linux."
    )
    input_model = ClipboardScreenshotToolInput

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_read_only(self, arguments: ClipboardScreenshotToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self, arguments: ClipboardScreenshotToolInput, context: ToolExecutionContext
    ) -> ToolResult:
        # 1. Read raw PNG bytes from the clipboard
        image_bytes = await self._read_clipboard_image()
        if image_bytes is None:
            return ToolResult(
                output=(
                    "clipboard_screenshot: no image found in clipboard. "
                    "Please take a screenshot (e.g. Win+Shift+S on Windows, "
                    "Cmd+Ctrl+Shift+4 on macOS) or copy an image first, then "
                    "try again."
                ),
                is_error=True,
            )

        size_kb = len(image_bytes) / 1024

        # 2. Route by output format
        if arguments.output_format == "base64":
            b64 = base64.b64encode(image_bytes).decode("ascii")
            return ToolResult(
                output=(
                    f"[Clipboard image captured: {len(image_bytes)} bytes "
                    f"({size_kb:.1f} KB), PNG format]\n"
                    f"The image is available in the metadata. "
                    f"Use image_to_text with image_data to analyze it."
                ),
                metadata={
                    "image_data": b64,
                    "media_type": "image/png",
                    "size_bytes": len(image_bytes),
                },
            )

        if arguments.output_format == "file":
            save_path = Path(arguments.save_path or "clipboard_screenshot.png")
            if not save_path.is_absolute():
                save_path = (context.cwd / save_path).resolve()
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(image_bytes)
            return ToolResult(
                output=(
                    f"Saved clipboard image to {save_path} "
                    f"({len(image_bytes)} bytes, {size_kb:.1f} KB)"
                ),
                metadata={
                    "path": str(save_path),
                    "size_bytes": len(image_bytes),
                },
            )

        if arguments.output_format == "text":
            return await self._describe_via_vision(image_bytes, arguments, context)

        return ToolResult(output="Invalid output_format", is_error=True)

    # ------------------------------------------------------------------
    # Clipboard reading — platform dispatch
    # ------------------------------------------------------------------

    async def _read_clipboard_image(self) -> bytes | None:
        """Read an image from the clipboard, returning PNG bytes or None."""
        platform = get_platform()

        if platform == "windows":
            return self._read_clipboard_windows()
        if platform == "macos":
            return self._read_clipboard_macos()
        if platform in ("linux", "wsl"):
            return self._read_clipboard_linux()

        # Unknown platform — try PIL as a last resort
        return self._read_clipboard_pil()

    # ------------------------------------------------------------------
    # Windows: multi-tier fallback
    # ------------------------------------------------------------------

    def _read_clipboard_windows(self) -> bytes | None:
        """Windows clipboard reading with automatic fallback.

        Tier 1: Pillow ImageGrab (simplest, synchronous)
        Tier 2: PowerShell + System.Windows.Forms (always available on Win10+)
        """
        # Tier 1 — Pillow
        result = self._read_clipboard_pil()
        if result is not None:
            log.debug("clipboard_screenshot: captured via Pillow ImageGrab")
            return result

        # Tier 2 — PowerShell (Windows PowerShell 5.1)
        result = self._read_clipboard_powershell()
        if result is not None:
            log.debug("clipboard_screenshot: captured via PowerShell")
            return result

        return None

    @staticmethod
    def _read_clipboard_pil() -> bytes | None:
        """Read clipboard image via Pillow ImageGrab (cross-platform)."""
        try:
            from PIL import ImageGrab  # type: ignore[import-untyped]
        except ImportError:
            return None

        try:
            img = ImageGrab.grabclipboard()
        except Exception:
            log.debug("PIL ImageGrab.grabclipboard() raised", exc_info=True)
            return None

        if img is None:
            return None

        # Convert to PNG bytes in memory
        try:
            import io

            buf = io.BytesIO()
            # Ensure RGBA → RGB if no alpha needed (PNG handles both)
            if img.mode not in ("RGB", "RGBA", "L", "P"):
                img = img.convert("RGBA")
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            log.debug("PIL image save to PNG buffer failed", exc_info=True)
            return None

    @staticmethod
    def _read_clipboard_powershell() -> bytes | None:
        """Read clipboard image via Windows PowerShell subprocess.

        Uses Windows PowerShell 5.1 (powershell.exe), not pwsh.exe,
        because System.Windows.Forms and System.Drawing are built-in
        on every Windows 10/11 installation.
        """
        ps_exe = _find_windows_powershell()
        if ps_exe is None:
            return None

        tmp_path = None
        try:
            # Create temp file for PowerShell to write into
            fd, tmp_path_str = tempfile.mkstemp(suffix=".png", prefix="oh_clip_")
            tmp_path = Path(tmp_path_str)
            os_close_fd(fd)

            script = (
                f"Add-Type -AssemblyName System.Windows.Forms;"
                f"Add-Type -AssemblyName System.Drawing;"
                f"$img = [System.Windows.Forms.Clipboard]::GetImage();"
                f'if ($img -ne $null) {{'
                f'  $img.Save("{tmp_path}", [System.Drawing.Imaging.ImageFormat]::Png);'
                f'  Write-Output "OK"'
                f"}} else {{"
                f'  Write-Output "NO_IMAGE"'
                f"}}"
            )

            result = subprocess.run(
                [str(ps_exe), "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=15,
            )

            stdout = result.stdout.strip() if result.stdout else ""
            if stdout == "OK" and tmp_path.exists() and tmp_path.stat().st_size > 0:
                return tmp_path.read_bytes()

            if stdout == "NO_IMAGE":
                log.debug("PowerShell: clipboard contains no image")
            else:
                log.debug(
                    "PowerShell unexpected output: stdout=%r stderr=%r",
                    stdout,
                    result.stderr[:200] if result.stderr else "",
                )
            return None

        except FileNotFoundError:
            log.debug("PowerShell executable not found")
            return None
        except subprocess.TimeoutExpired:
            log.debug("PowerShell clipboard read timed out")
            return None
        except Exception:
            log.debug("PowerShell clipboard read failed", exc_info=True)
            return None
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # macOS — osascript + PNG clipboard
    # ------------------------------------------------------------------

    def _read_clipboard_macos(self) -> bytes | None:
        """Read clipboard image on macOS.

        Tier 1: Pillow ImageGrab
        Tier 2: osascript (AppKit) to extract TIFF → PNG
        """
        # Tier 1 — Pillow
        result = self._read_clipboard_pil()
        if result is not None:
            return result

        # Tier 2 — osascript
        return self._read_clipboard_macos_osascript()

    @staticmethod
    def _read_clipboard_macos_osascript() -> bytes | None:
        """Use AppleScript/AppKit to extract clipboard image as PNG."""
        osascript = shutil.which("osascript")
        if osascript is None:
            return None

        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(suffix=".png", prefix="oh_clip_")
            tmp_path = Path(tmp_path_str)
            os_close_fd(fd)

            script = (
                'use framework "AppKit"\n'
                'use scripting additions\n'
                "set pb to current application's NSPasteboard's generalPasteboard()\n"
                "set imageData to pb's dataForType:(current application's NSPasteboardTypePNG)\n"
                "if imageData is missing value then\n"
                '  return "NO_IMAGE"\n'
                "end if\n"
                f"set filePath to \"{tmp_path}\"\n"
                "imageData's writeToFile:filePath atomically:true\n"
                'return "OK"\n'
            )

            result = subprocess.run(
                [osascript, "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )

            stdout = result.stdout.strip() if result.stdout else ""
            if stdout == "OK" and tmp_path.exists() and tmp_path.stat().st_size > 0:
                return tmp_path.read_bytes()

            return None
        except Exception:
            log.debug("macOS osascript clipboard read failed", exc_info=True)
            return None
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Linux — xclip / wl-paste
    # ------------------------------------------------------------------

    def _read_clipboard_linux(self) -> bytes | None:
        """Read clipboard image on Linux / WSL.

        Tier 1: Pillow ImageGrab
        Tier 2: xclip (X11) or wl-paste (Wayland)
        """
        # Tier 1 — Pillow
        result = self._read_clipboard_pil()
        if result is not None:
            return result

        # Tier 2 — detect display server and use appropriate tool
        if _is_wayland():
            return self._read_clipboard_wl_paste()
        return self._read_clipboard_xclip()

    @staticmethod
    def _read_clipboard_xclip() -> bytes | None:
        """Read clipboard image via xclip (X11)."""
        xclip = shutil.which("xclip")
        if xclip is None:
            return None

        try:
            # xclip -selection clipboard -t image/png -o
            result = subprocess.run(
                [xclip, "-selection", "clipboard", "-t", "image/png", "-o"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
            # Try common alternative targets
            for target in ("image/jpeg", "image/bmp", "image/gif"):
                result = subprocess.run(
                    [xclip, "-selection", "clipboard", "-t", target, "-o"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout:
                    # Convert to PNG via Pillow if available
                    return _convert_to_png(result.stdout)
            return None
        except Exception:
            log.debug("xclip clipboard read failed", exc_info=True)
            return None

    @staticmethod
    def _read_clipboard_wl_paste() -> bytes | None:
        """Read clipboard image via wl-paste (Wayland)."""
        wl_paste = shutil.which("wl-paste")
        if wl_paste is None:
            return None

        try:
            result = subprocess.run(
                [wl_paste, "-t", "image/png"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
            return None
        except Exception:
            log.debug("wl-paste clipboard read failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Vision model auto-description (for output_format="text")
    # ------------------------------------------------------------------

    async def _describe_via_vision(
        self,
        image_bytes: bytes,
        arguments: ClipboardScreenshotToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        """Describe the clipboard image using a configured vision model."""
        vision_config = context.metadata.get("vision_model_config", None)

        # Fallback: load directly from settings when metadata is not injected
        # (key absent from metadata dict, not just empty value)
        if vision_config is None:
            try:
                from openharness.config.settings import load_settings

                settings_vision = load_settings().vision
                if settings_vision.is_configured:
                    vision_config = {
                        "model": settings_vision.model,
                        "api_key": settings_vision.api_key,
                        "base_url": settings_vision.base_url or "",
                    }
            except Exception:
                pass

        if not vision_config:
            return ToolResult(
                output=(
                    "clipboard_screenshot: vision model is not configured. "
                    "Set vision.model and vision.api_key in your settings, "
                    "or use output_format='base64' and pipe the result to "
                    "image_to_text manually."
                ),
                is_error=True,
            )

        model = vision_config["model"]
        api_key = vision_config["api_key"]
        base_url = vision_config.get("base_url", "")

        prompt = arguments.description_prompt or (
            "Describe this screenshot in detail, including any visible text, "
            "UI elements, error messages, code, diagrams, or data. Be precise "
            "so that a text-only AI can fully understand the content."
        )

        try:
            description = await self._call_vision(
                image_bytes=image_bytes,
                prompt=prompt,
                model=model,
                api_key=api_key,
                base_url=base_url,
            )
        except Exception as exc:
            log.exception("clipboard_screenshot: vision model call failed")
            return ToolResult(
                output=f"clipboard_screenshot: vision model error: {exc}",
                is_error=True,
            )

        return ToolResult(output=f"[Clipboard screenshot description via {model}]\n\n{description}")

    @staticmethod
    async def _call_vision(
        *,
        image_bytes: bytes,
        prompt: str,
        model: str,
        api_key: str,
        base_url: str,
    ) -> str:
        """Call a vision-capable model to describe the image."""
        from openharness.api.client import ApiMessageRequest
        from openharness.api.openai_client import OpenAICompatibleClient
        from openharness.engine.messages import (
            ConversationMessage,
            ImageBlock,
            TextBlock,
        )

        b64_data = base64.b64encode(image_bytes).decode("ascii")

        user_content: list[Any] = [TextBlock(text=prompt)]
        user_content.append(ImageBlock(media_type="image/png", data=b64_data))
        user_message = ConversationMessage(role="user", content=user_content)

        client = OpenAICompatibleClient(api_key=api_key, base_url=base_url or None)

        collected_text = ""
        async for event in client.stream_message(
            ApiMessageRequest(
                model=model,
                messages=[user_message],
                system_prompt="",
                max_tokens=2048,
                tools=[],
            )
        ):
            from openharness.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent

            if isinstance(event, ApiTextDeltaEvent):
                collected_text += event.text
            elif isinstance(event, ApiMessageCompleteEvent):
                text = event.message.text
                if text and text not in collected_text:
                    collected_text = text

        return collected_text.strip() or "(no description returned)"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _find_windows_powershell() -> Path | None:
    """Resolve the path to Windows PowerShell 5.1 (powershell.exe)."""
    # Try the canonical system path first
    candidates = [
        Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # Fall back to PATH lookup
    found = shutil.which("powershell.exe")
    if found:
        return Path(found)
    return None


def _is_wayland() -> bool:
    """Return True when the active display server is Wayland."""
    return os.environ.get("WAYLAND_DISPLAY", "") != "" or os.environ.get("XDG_SESSION_TYPE", "") == "wayland"


def _convert_to_png(raw: bytes) -> bytes | None:
    """Convert raw image bytes to PNG using Pillow (if available)."""
    try:
        from PIL import Image  # type: ignore[import-untyped]
        import io

        img = Image.open(io.BytesIO(raw))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def os_close_fd(fd: int) -> None:
    """Close an open file descriptor; best-effort."""
    import os as _os

    try:
        _os.close(fd)
    except OSError:
        pass