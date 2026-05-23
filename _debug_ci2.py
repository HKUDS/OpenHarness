"""Reproduce the exact CI scenario with Linux /tmp path."""
from __future__ import annotations
from unittest import mock
from pathlib import Path
import subprocess
import tempfile
import os
import sys

# On CI, tmp_path from pytest is like /tmp/pytest-of-runner/pytest-0/test_powershell_image_found0
# The test creates a file there: tmp_file = tmp_path / "test_clip.png"
# Then mocks tempfile.mkstemp to return (999, str(tmp_file))
# str(tmp_file) on Linux would be "/tmp/pytest-of-runner/pytest-0/test_powershell_image_found0/test_clip.png"

# Simulate this with a path that looks like a Linux path
if sys.platform == "win32":
    # On Windows, we can still test the logic
    real_tmpdir = Path(tempfile.mkdtemp())
    tmp_file = real_tmpdir / "test_clip.png"
else:
    real_tmpdir = Path("/tmp/test_debug")
    real_tmpdir.mkdir(exist_ok=True)
    tmp_file = real_tmpdir / "test_clip.png"

tmp_file.write_bytes(b'\x89PNG\r\n\x1a\ntest')

# Key question: When tempfile.mkstemp is mocked to return (999, str(tmp_file)),
# and then Path(tmp_path_str) is created, does the file still exist?
# YES - because the file was already written to disk before the mock.

# But wait... on CI, the test writes png to tmp_file (which is tmp_path / "test_clip.png")
# But does tempfile.mkstemp's mock return value have the right format?

# tempfile.mkstemp normally returns (fd, absolute_path_string)
# The mock returns (999, str(tmp_file)) where tmp_file = tmp_path / "test_clip.png"

# Let me check if there's an issue with the Path conversion
print("tmp_file:", tmp_file)
print("str(tmp_file):", str(tmp_file))

# Now the critical question: is the mock for tempfile.mkstemp correct?
# When the source code does:
#   fd, tmp_path_str = tempfile.mkstemp(suffix=".png", prefix="oh_clip_")
# The mock returns (999, str(tmp_file)) regardless of the suffix/prefix arguments.
# This is fine for the mock.

# Let me now check: what if there's a race condition with the finally block?
# The source code after my fix does:
#   if stdout == "OK" and tmp_path.exists() and tmp_path.stat().st_size > 0:
#       image_data = tmp_path.read_bytes()
#       try:
#           tmp_path.unlink(missing_ok=True)
#       except Exception:
#           pass
#       tmp_path = None  # prevent double-unlink in finally
#       return image_data
#
# The finally block does:
#   if tmp_path is not None:
#       try:
#           tmp_path.unlink(missing_ok=True)
#       except Exception:
#           pass

# This should work... unless there's an exception BEFORE the return.

# Wait, let me check: what if os_close_fd(fd) with fd=999 causes an issue
# even with mock.patch("os.close")?

# The source code's os_close_fd does:
#   import os as _os
#   try:
#       _os.close(fd)
#   except OSError:
#       pass

# With mock.patch("os.close"), _os.close is the mock, so it won't raise.
# But wait... is mock.patch("os.close") affecting the os module correctly?

# Let me check more carefully...
# When we do mock.patch("os.close"), it replaces os.close with a MagicMock.
# But os_close_fd does `import os as _os` inside the function.
# `import os` always returns the same module object (sys.modules['os']).
# So _os.close should be the same as os.close, which is the mock.

# BUT WAIT: What if the mock.patch("os.close") in the test doesn't actually
# affect the `os` module seen by os_close_fd?

# Let me verify this explicitly.
print("\n=== Verifying os.close mock ===")

with mock.patch("os.close") as mock_close:
    # Check: is os.close the mock?
    print("os.close is mock:", isinstance(os.close, type(mock_close)))
    
    # Check: does os_close_fd use the mock?
    import os as _test_os
    print("_test_os.close is mock:", isinstance(_test_os.close, type(mock_close)))
    
    # The key: os_close_fd does `import os as _os` INSIDE the function.
    # This `import os` returns the cached module from sys.modules.
    # Since mock.patch already replaced os.close on that module object,
    # `import os as _os` inside the function will see the mock.
    
    # So os_close_fd(999) should NOT raise an error.
    try:
        os_close_fd(999)
        print("os_close_fd(999) succeeded (no error)")
    except OSError:
        print("os_close_fd(999) raised OSError - MOCK NOT WORKING!")

print("\n=== Checking if there's a different os module ===")
# There's only one os module in Python. import os always returns the same object.
# So mock.patch("os.close") should always work.

# Let me try one more thing: what if the issue is with `os.path`?
# No, os.path is separate from os.close.

# Let me think about this differently. The test passes locally but fails on CI.
# What's different about CI?
# 1. Linux (Ubuntu) vs Windows
# 2. Python 3.10/3.11 vs 3.13
# 3. Different file system (/tmp vs C:\Users\...)

# Could it be that on CI, the tmp_path (pytest fixture) creates the file
# in /tmp/pytest-of-runner/... and then tempfile.mkstemp is mocked to return
# that path, but the Path object constructed from the string behaves differently?

# Actually, let me re-read the test error more carefully:
# result = ClipboardScreenshotTool._read_clipboard_powershell()
# assert result == png
# AssertionError: assert None == b'\x89PNG...'

# So the function returns None. Let me trace all paths that return None:
# 1. ps_exe is None → but _find_windows_powershell is mocked to return fake_ps
# 2. stdout != "OK" or tmp_path not exists or size == 0
# 3. stdout == "NO_IMAGE" 
# 4. Exception caught

# Since subprocess.run is mocked to return stdout="OK", and tmp_path exists with content,
# the only remaining possibility is that an exception is being raised and caught.

# What exception? Let me check...

# AH WAIT! I just realized something. The mock for subprocess.run uses
# "openharness.tools.clipboard_screenshot_tool.subprocess.run" in my fix.
# But what if this doesn't work because the module hasn't been imported yet
# at the time the mock is set up? No, that can't be - the test imports from it.

# Let me try another theory: maybe the issue is that mock.patch creates a NEW
# mock object, and when the source code does `subprocess.run(...)`, it's not
# using the same mock. But that shouldn't be the case with module-level patching.

# I'm going to try a completely different approach: rewrite the test to be
# more robust and not rely on so many fragile mocks.

print("\n=== Let me check one more thing ===")
print("Python version:", sys.version)
