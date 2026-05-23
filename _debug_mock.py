"""Debug script - check mock behavior for tempfile.mkstemp."""
from __future__ import annotations
from unittest import mock
from pathlib import Path
import tempfile

# When we mock.patch("tempfile.mkstemp", ...), does it affect
# code that already did `import tempfile` and calls tempfile.mkstemp()?

print("Before mock, tempfile.mkstemp is:", tempfile.mkstemp)

with mock.patch("tempfile.mkstemp", return_value=(999, "/fake/path.png")):
    print("Inside mock, tempfile.mkstemp is:", tempfile.mkstemp)
    result = tempfile.mkstemp()
    print("tempfile.mkstemp() returns:", result)
    
    # Now check: if another module did `import tempfile` before the mock,
    # would it see the mock?
    # Answer: YES, because `tempfile` is a singleton module object.
    # When you patch `tempfile.mkstemp`, you're setting `tempfile.mkstemp = Mock`
    # which is visible to everyone who has a reference to the `tempfile` module.

print("After mock, tempfile.mkstemp is:", tempfile.mkstemp)
