"""Tests for proactive notification message splitting."""

import pytest

from ohmo.gateway.notify import _chunk_text


def test_notification_chunks_preserve_newlines_and_indentation():
    text = "Summary\n    indented code block\nFinal line"
    chunks = _chunk_text(text, max_chars=15)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 15 for chunk in chunks)
    assert "".join(chunks) == text


def test_notification_chunks_reject_nonpositive_limits():
    for limit in (0, -1):
        with pytest.raises(ValueError, match="max_chars"):
            _chunk_text("Hello", max_chars=limit)
