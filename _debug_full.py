"""Debug: Reproduce the exact CI Linux behavior for test_powershell_image_found.

Key insight: CI runs on Ubuntu, where `os.close(999)` raises OSError
because fd 999 is not open. The `os_close_fd` function catches this,
but we need to verify if `os.close` is properly mocked.
"""
from __future__ import annotations
from unittest import mock
from pathlib import Path
import subprocess
import tempfile
import os

def os_close_fd(fd: int) -> None:
    """Same as source module."""
    import os as _os
    try:
        _os.close(fd)
    except OSError:
        pass

# Create test file
import tempfile
real_tmpdir = Path(tempfile.mkdtemp())
tmp_file = real_tmpdir / "test_clip.png"
tmp_file.write_bytes(b'\x89PNG\r\n\x1a\ntest')

fake_ps = Path(r"C:\fake\powershell.exe")
fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="OK", stderr="")

# Test: Does mock.patch("os.close") actually affect the os module used in os_close_fd?
print("=== Test 1: mock os.close globally ===")
with mock.patch("os.close") as mock_close:
    os_close_fd(999)
    print("os_close_fd succeeded")
    print("mock_close called:", mock_close.called)
    # BUT: does this prevent the REAL os.close from being called?
    # Since os_close_fd does `import os as _os` which gets the same module object,
    # and we've replaced os.close with a mock, _os.close is now the mock.
    # So OSError won't be raised. Good.

# Now simulate the FULL _read_clipboard_powershell logic
# with ALL the mocks from the test
print("\n=== Test 2: Full simulation ===")

class SimulatedReadClipboardPowershell:
    @staticmethod
    def _read_clipboard_powershell():
        ps_exe = fake_ps  # _find_windows_powershell is mocked
        
        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(suffix=".png", prefix="oh_clip_")
            tmp_path = Path(tmp_path_str)
            os_close_fd(fd)
            
            script = "fake script"
            result = subprocess.run(
                [str(ps_exe), "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            
            stdout = result.stdout.strip() if result.stdout else ""
            print("  stdout:", repr(stdout))
            print("  tmp_path exists:", tmp_path.exists())
            if tmp_path.exists():
                print("  tmp_path size:", tmp_path.stat().st_size)
            
            if stdout == "OK" and tmp_path.exists() and tmp_path.stat().st_size > 0:
                image_data = tmp_path.read_bytes()
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                tmp_path = None
                return image_data
            
            if stdout == "NO_IMAGE":
                pass
            else:
                print("  unexpected output")
            return None
            
        except FileNotFoundError:
            print("  FileNotFoundError caught")
            return None
        except subprocess.TimeoutExpired:
            print("  TimeoutExpired caught")
            return None
        except Exception as e:
            print("  Exception caught:", type(e).__name__, e)
            return None
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

with (
    mock.patch("tempfile.mkstemp", return_value=(999, str(tmp_file))),
    mock.patch("subprocess.run", return_value=fake_result),
    mock.patch("os.close"),
):
    result = SimulatedReadClipboardPowershell._read_clipboard_powershell()
    print("Result:", result[:8] if result else None)

# Cleanup
import shutil
shutil.rmtree(real_tmpdir, ignore_errors=True)
