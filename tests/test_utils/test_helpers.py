"""Tests for compatibility helpers used by channel implementations."""

from __future__ import annotations

from openharness.utils.helpers import get_data_path, safe_filename, split_message


def test_split_message_prefers_word_boundaries() -> None:
    chunks = split_message("hello world again", 8)

    assert chunks == ["hello", "world", "again"]
    assert all(len(chunk) <= 8 for chunk in chunks)


def test_split_message_hard_splits_long_unbroken_text() -> None:
    chunks = split_message("abcdef", 2)

    assert chunks == ["ab", "cd", "ef"]


def test_split_message_empty_text_returns_no_chunks() -> None:
    assert split_message("", 10) == []


def test_safe_filename_strips_path_and_unsafe_characters() -> None:
    assert safe_filename("../bad name;$(rm).txt") == "bad_name_rm_.txt"


def test_safe_filename_rejects_empty_or_parent_segments() -> None:
    assert safe_filename("../") == ""
    assert safe_filename("...") == ""


def test_get_data_path_is_backwards_compatible_alias() -> None:
    assert get_data_path().name == "data"
