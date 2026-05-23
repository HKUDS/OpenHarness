"""Debug: simulate the exact CI Linux scenario for test_powershell_image_found."""
from __future__ import annotations
from unittest import mock
from pathlib import Path
import subprocess
import tempfile
import os

# Simulate os_close_fd from the module
def os_close_fd(fd: int) -> None:
    import os as _os
    try:
        _os.close(fd)
    except OSError:
        pass

# Create a real temp file with PNG content
import pytest
try:
    from PIL import Image
    import io as _io
    buf = _io.BytesIO()
    img = Image.new("RGB", (10, 10), color="red")
    img.save(buf, format="PNG")
    png = buf.getvalue()
except ImportError:
    print("Pillow not installed, using fake PNG")
    png = b'\x89PNG\r\n\x1a\nfake'

# Use a real temp directory like CI does
import tempfile
real_tmpdir = Path(tempfile.mkdtemp())
tmp_file = real_tmpdir / "test_clip.png"
tmp_file.write_bytes(png)

fake_ps = Path(r"C:\fake\powershell.exe")
fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")

print("=== Simulating _read_clipboard_powershell ===")
print("tmp_file:", tmp_file)
print("tmp_file exists:", tmp_file.exists())
print("tmp_file size:", tmp_file.stat().st_size)
print("str(tmp_file):", str(tmp_file))

# Simulate the function with the exact same mock pattern as the test
with (
    mock.patch(
        "tempfile.mkstemp",
        return_value=(999, str(tmp_file)),
    ),
    mock.patch(
        "subprocess.run",
        return_value=fake_result,
    ),
    mock.patch("os.close"),
):
    # Now simulate _read_clipboard_powershell logic step by step
    tmp_path = None
    try:
        fd, tmp_path_str = tempfile.mkstemp(suffix=".png", prefix="oh_clip_")
        print("mkstemp returned: fd=%d, path=%s" % (fd, tmp_path_str))
        tmp_path = Path(tmp_path_str)
        print("Path(tmp_path_str):", tmp_path)
        print("tmp_path exists:", tmp_path.exists())
        
        if tmp_path.exists():
            print("tmp_path.stat().st_size:", tmp_path.stat().st_size)
        
        os_close_fd(fd)
        
        # subprocess.run is mocked
        result = subprocess.run(
            [str(fake_ps), "-NoProfile", "-NonInteractive", "-Command", "script"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        stdout = result.stdout.strip() if result.stdout else ""
        print("stdout:", repr(stdout))
        
        # The key check
        if stdout == "OK" and tmp_path.exists() and tmp_path.stat().st_size > 0:
            image_data = tmp_path.read_bytes()
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            tmp_path = None
            print("SUCCESS: got %d bytes, matches png: %s" % (len(image_data), image_data == png))
        else:
            print("FAILED check: stdout=%r, exists=%r, size=%r" % (
                stdout, tmp_path.exists(), 
                tmp_path.stat().st_size if tmp_path.exists() else 'N/A'
            ))
            
    except Exception as e:
        print("Exception:", type(e).__name__, e)
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

# Cleanup
import shutil
shutil.rmtree(real_tmpdir, ignore_errors=True)
