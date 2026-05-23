"""Debug script - simulate _find_windows_powershell and trace exactly what happens."""
from __future__ import annotations
from unittest import mock
from pathlib import Path
import subprocess
import tempfile
import os

def os_close_fd(fd: int) -> None:
    import os as _os
    try:
        _os.close(fd)
    except OSError:
        pass

png = b'\x89PNG\r\n\x1a\ntest'
tmp_file = Path(r'd:\iflow工作区\OpenHarness\tmp_test.png')
tmp_file.write_bytes(png)

fake_ps = Path(r'C:\fake\powershell.exe')
fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")

# Test 1: mock tempfile.mkstemp in the source module
print("=== Test 1: patch tempfile.mkstemp in source module ===")
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
    # Check what the source module sees
    from openharness.tools import clipboard_screenshot_tool as _mod
    
    # What does the module's tempfile.mkstemp return?
    fd, path = _mod.tempfile.mkstemp()
    print("Module's tempfile.mkstemp:", fd, path)
    
    # What does tempfile.mkstemp return when called directly?
    fd2, path2 = tempfile.mkstemp()
    print("Direct tempfile.mkstemp:", fd2, path2)
    
    # They're different! The mock patches the global tempfile.mkstemp,
    # but the module already imported it, so _mod.tempfile is the real tempfile module.
    # Wait, let's check...
    print("_mod.tempfile is tempfile:", _mod.tempfile is tempfile)

print()

# Test 2: patch tempfile in the source module specifically
print("=== Test 2: patch tempfile.mkstemp in source module directly ===")
with (
    mock.patch(
        "openharness.tools.clipboard_screenshot_tool._find_windows_powershell",
        return_value=fake_ps,
    ),
    mock.patch(
        "openharness.tools.clipboard_screenshot_tool.tempfile.mkstemp",
        return_value=(999, str(tmp_file)),
    ),
    mock.patch(
        "openharness.tools.clipboard_screenshot_tool.subprocess.run",
        return_value=fake_result,
    ),
    mock.patch("os.close"),
):
    from openharness.tools import clipboard_screenshot_tool as _mod2
    fd, path = _mod2.tempfile.mkstemp()
    print("Module's tempfile.mkstemp:", fd, path)
