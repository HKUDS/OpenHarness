"""Debug script for test_powershell_image_found - minimal version."""
from __future__ import annotations
from unittest import mock
from pathlib import Path
import subprocess
import tempfile
import os

# Simulate the source code logic directly

def os_close_fd(fd: int) -> None:
    """Close an open file descriptor; best-effort."""
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

print("tmp_file str:", str(tmp_file))
print("tmp_file exists before:", tmp_file.exists())
print("tmp_file size before:", tmp_file.stat().st_size)

with (
    mock.patch("tempfile.mkstemp", return_value=(999, str(tmp_file))),
    mock.patch("subprocess.run", return_value=fake_result),
    mock.patch("os.close"),
):
    # Simulate _read_clipboard_powershell logic
    tmp_path = None
    try:
        fd, tmp_path_str = tempfile.mkstemp(suffix=".png", prefix="oh_clip_")
        print("mkstemp returned:", fd, tmp_path_str)
        tmp_path = Path(tmp_path_str)
        print("tmp_path:", tmp_path)
        print("tmp_path exists:", tmp_path.exists())
        os_close_fd(fd)
        
        result = subprocess.run(
            [str(fake_ps), "-NoProfile", "-NonInteractive", "-Command", "test"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        stdout = result.stdout.strip() if result.stdout else ""
        print("stdout:", repr(stdout))
        print("tmp_path exists after subprocess:", tmp_path.exists())
        if tmp_path.exists():
            print("tmp_path size:", tmp_path.stat().st_size)
        
        if stdout == "OK" and tmp_path.exists() and tmp_path.stat().st_size > 0:
            image_data = tmp_path.read_bytes()
            print("SUCCESS: read", len(image_data), "bytes")
        else:
            print("FAILED: stdout=%r, exists=%r, size=%r" % (
                stdout, tmp_path.exists(), tmp_path.stat().st_size if tmp_path.exists() else 'N/A'
            ))
    except Exception as e:
        print("Exception:", e)
