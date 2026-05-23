"""Debug script for test_powershell_image_found."""
import sys
sys.path.insert(0, r'd:\iflow工作区\OpenHarness\src')

from unittest import mock
from pathlib import Path
import subprocess

from openharness.tools.clipboard_screenshot_tool import (
    ClipboardScreenshotTool,
    os_close_fd,
)

png = b'\x89PNG\r\n\x1a\ntest'
tmp_file = Path(r'd:\iflow工作区\OpenHarness\tmp_test.png')
tmp_file.write_bytes(png)

fake_ps = Path(r'C:\fake\powershell.exe')
fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")

print("tmp_file exists before:", tmp_file.exists())
print("tmp_file size before:", tmp_file.stat().st_size)
print("tmp_file content:", tmp_file.read_bytes()[:8])

# Check: what does tempfile.mkstemp return when patched?
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
    mock.patch("os.close"),
):
    # Inside the mock context, check what tempfile.mkstemp returns
    import tempfile as _tf
    print("tempfile.mkstemp inside mock:", _tf.mkstemp())
    
    result = ClipboardScreenshotTool._read_clipboard_powershell()
    print("result:", result[:8] if result else None)

print("tmp_file exists after:", tmp_file.exists())
