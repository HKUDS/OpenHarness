"""Debug: Check if os.close mock affects os_close_fd."""
from __future__ import annotations
from unittest import mock
import os

# os_close_fd as defined in the source module
def os_close_fd(fd: int) -> None:
    import os as _os
    try:
        _os.close(fd)
    except OSError:
        pass

print("=== Test: does mock.patch('os.close') affect os_close_fd? ===")

# Test 1: mock os.close at the global level
with mock.patch("os.close"):
    try:
        os_close_fd(999)  # This should NOT raise because os.close is mocked
        print("os_close_fd(999) succeeded with mock.patch('os.close')")
    except OSError as e:
        print("os_close_fd(999) raised OSError:", e)

# Test 2: Is os._os the same as os?
import os as _os
print("os is _os:", os is _os)
print("os.close is _os.close:", os.close is _os.close)

# When we do `import os as _os` inside a function, `_os` refers to the
# same module object as `os`. So mocking `os.close` should affect `_os.close`.
