"""Structured memory metadata helpers."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

SCHEMA_VERSION = 1

MemoryType = Literal["user", "feedback", "project", "reference"]
MemoryScope = Literal["private", "project", "team"]

MEMORY_TYPES: tuple[MemoryType, ...] = ("user", "feedback", "project", "reference")
MEMORY_SCOPES: tuple[MemoryScope, ...] = ("private", "project", "team")

DEFAULT_MEMORY_TYPE: MemoryType = "project"
DEFAULT_MEMORY_SCOPE: MemoryScope = "project"

MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000
MAX_MANIFEST_FILES = 200

FRONTMATTER_FIELDS = (
    "schema_version",
    "id",
    "name",
    "description",
    "type",
    "scope",
    "category",
    "importance",
    "source",
    "signature",
    "created_at",
    "updated_at",
    "ttl_days",
    "disabled",
    "supersedes",
    "tags",
)


@dataclass(frozen=True)
class EntrypointView:
    """A bounded view of ``MEMORY.md`` plus truncation diagnostics."""

    content: str
    was_truncated: bool
    reason: str = ""


def utc_now() -> datetime:
    """Return the current UTC time without sub-second noise."""

    return datetime.now(timezone.utc).replace(microsecond=0)


def format_datetime(value: datetime) -> str:
    """Format a datetime as an ISO-8601 UTC string."""

    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: object) -> datetime | None:
    """Parse an ISO datetime value used in memory frontmatter."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_memory_content(text: str) -> str:
    """Normalize memory content for deterministic signatures."""

    lowered = text.lower()
    collapsed = re.sub(r"\s+", " ", lowered)
    punctuation_table = str.maketrans("", "", string.punctuation)
    return collapsed.translate(punctuation_table).strip()


def compute_memory_signature(content: str, memory_type: str, category: str) -> str:
    """Compute a deterministic content signature for duplicate detection."""

    normalized = normalize_memory_content(content)
    payload = f"{normalized}|{memory_type.strip().lower()}|{category.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_memory_type(raw: Any, *, default: MemoryType | None = None) -> MemoryType | None:
    """Parse a frontmatter ``type`` value into the canonical runtime taxonomy."""

    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in MEMORY_TYPES:
            return value  # type: ignore[return-value]
        if value in {"note", "memory", "core", "knowledge"}:
            return default
    return default


def parse_memory_scope(raw: Any, *, default: MemoryScope | None = None) -> MemoryScope | None:
    """Parse a frontmatter ``scope`` value into the canonical scope taxonomy."""

    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in MEMORY_SCOPES:
            return value  # type: ignore[return-value]
        if value in {"personal", "user"}:
            return "private"
        if value in {"shared"}:
            return "team"
    return default


def truncate_entrypoint_content(
    raw: str,
    *,
    max_lines: int = MAX_ENTRYPOINT_LINES,
    max_bytes: int = MAX_ENTRYPOINT_BYTES,
) -> EntrypointView:
    """Bound ``MEMORY.md`` by line count and UTF-8 byte count."""

    lines = raw.splitlines()
    was_line_truncated = len(lines) > max_lines
    text = "\n".join(lines[:max_lines])
    encoded = text.encode("utf-8")
    was_byte_truncated = len(encoded) > max_bytes
    if was_byte_truncated:
        encoded = encoded[:max_bytes]
        text = encoded.decode("utf-8", errors="ignore")
        cut_at = text.rfind("\n")
        if cut_at > 0:
            text = text[:cut_at]
    if raw.endswith("\n") and not text.endswith("\n"):
        text += "\n"
    if not was_line_truncated and not was_byte_truncated:
        return EntrypointView(content=text, was_truncated=False)
    reason = (
        f"{len(raw.encode('utf-8'))} bytes (limit: {max_bytes})"
        if was_byte_truncated
        else f"{len(lines)} lines (limit: {max_lines})"
    )
    warning = (
        f"\n\n> WARNING: MEMORY.md is {reason}. Only part of it was loaded. "
        "Keep index entries one line and move detail into topic notes.\n"
    )
    return EntrypointView(content=text.rstrip() + warning, was_truncated=True, reason=reason)


def memory_age_days(mtime: float, *, now: float | None = None) -> int:
    """Return floor-rounded days elapsed since a file modification time."""

    import time

    current = time.time() if now is None else now
    return max(0, int((current - mtime) // 86_400))


def memory_age_label(mtime: float, *, now: float | None = None) -> str:
    """Return a model-friendly age label."""

    days = memory_age_days(mtime, now=now)
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def memory_freshness_text(mtime: float, *, now: float | None = None) -> str:
    """Return a staleness warning for older memories."""

    days = memory_age_days(mtime, now=now)
    if days <= 1:
        return ""
    return (
        f"This memory is {days} days old. Memories are point-in-time observations; "
        "verify claims against the current project state before treating them as facts."
    )


def path_is_relative_to(path: str | Path, root: str | Path) -> bool:
    """Compatibility helper for containment checks."""

    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


MEMORY_POLICY_LINES: tuple[str, ...] = (
    "## Durable memory policy",
    "- Store durable memory only when the information is not cheaply derivable from current files, docs, git history, or tool output.",
    "- Use `type: user|feedback|project|reference` and optional `scope: private|project|team` frontmatter.",
    "- `MEMORY.md` is an index, not a memory body. Keep each pointer one line.",
    "- Update or remove stale contradictions instead of duplicating notes.",
    "- If the user says to ignore memory, proceed as if no memory was loaded and do not cite, apply, or mention memory contents.",
    "- Memory can be stale. Verify remembered project/code state against current files before acting on it.",
    "- Do not save secrets, credentials, private personal context in team memory, or temporary task chatter.",
)


def generate_memory_id(now: datetime | None = None) -> str:
    """Generate a stable-looking memory id for a new memory file."""

    timestamp = format_datetime(now or utc_now()).replace("-", "").replace(":", "")
    timestamp = timestamp.replace("T", "-").replace("Z", "")
    return f"mem-{timestamp}-{secrets.token_hex(4)}"


def split_memory_file(content: str) -> tuple[dict[str, Any], str, int, bool]:
    """Split a memory file into frontmatter metadata and body text.

    Returns ``(metadata, body, body_start_line, has_closed_frontmatter)``.
    Unclosed frontmatter is treated as body content after the opening delimiter.
    """

    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, content, 0, False

    for idx, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            raw_frontmatter = "".join(lines[1:idx])
            metadata = _load_frontmatter(raw_frontmatter)
            return metadata, "".join(lines[idx + 1 :]), idx + 1, True

    return {}, "".join(lines[1:]), 1, False


def render_memory_file(metadata: dict[str, Any], body: str) -> str:
    """Render metadata and body as a memory markdown file."""

    frontmatter = render_frontmatter(metadata)
    normalized_body = body.lstrip("\n")
    if normalized_body and not normalized_body.endswith("\n"):
        normalized_body += "\n"
    return f"---\n{frontmatter}---\n\n{normalized_body}"


def render_frontmatter(metadata: dict[str, Any]) -> str:
    """Render memory frontmatter in a stable field order."""

    ordered: list[tuple[str, Any]] = []
    for field in FRONTMATTER_FIELDS:
        if field in metadata:
            ordered.append((field, metadata[field]))
    for key, value in metadata.items():
        if key not in FRONTMATTER_FIELDS:
            ordered.append((key, value))
    return "".join(f"{key}: {_format_yaml_value(value)}\n" for key, value in ordered)


def is_disabled_metadata(metadata: dict[str, Any]) -> bool:
    """Return whether a memory metadata object marks the file disabled."""

    return _as_bool(metadata.get("disabled"), default=False)


def is_memory_expired(metadata: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Return whether a memory should be hidden because its TTL has elapsed."""

    ttl_days = _as_optional_int(metadata.get("ttl_days"))
    if ttl_days is None or ttl_days <= 0:
        return False
    base_time = parse_datetime(metadata.get("updated_at")) or parse_datetime(metadata.get("created_at"))
    if base_time is None:
        return False
    return (now or utc_now()) >= base_time + timedelta(days=ttl_days)


def coerce_int(value: object, *, default: int = 0) -> int:
    """Coerce a metadata value to int."""

    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def coerce_optional_int(value: object) -> int | None:
    """Coerce a metadata value to optional int."""

    return _as_optional_int(value)


def coerce_bool(value: object, *, default: bool = False) -> bool:
    """Coerce a metadata value to bool."""

    return _as_bool(value, default=default)


def coerce_str_list(value: object) -> tuple[str, ...]:
    """Coerce a metadata value to a tuple of strings."""

    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    return ()


def memory_metadata_from_path(
    path: Path,
    metadata: dict[str, Any],
    body: str,
    *,
    now: datetime | None = None,
    source: str = "migration",
    default_type: str = "project",
    default_category: str = "knowledge",
    seen_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return complete schema-v1 metadata while preserving existing values."""

    updated = dict(metadata)
    timestamp = _mtime_timestamp(path)
    created_at = str(updated.get("created_at") or timestamp)
    updated_at = str(updated.get("updated_at") or timestamp)
    memory_type = str(updated.get("type") or default_type)
    category = str(updated.get("category") or default_category)
    memory_id = str(updated.get("id") or "")
    if not memory_id or (seen_ids is not None and memory_id in seen_ids):
        memory_id = _generate_unique_memory_id(now=now, seen_ids=seen_ids)
    if seen_ids is not None:
        seen_ids.add(memory_id)

    updated["schema_version"] = coerce_int(updated.get("schema_version"), default=SCHEMA_VERSION)
    updated["id"] = memory_id
    updated["name"] = str(updated.get("name") or path.stem)
    updated["description"] = str(updated.get("description") or first_content_line(body) or path.stem)
    updated["type"] = memory_type
    updated["category"] = category
    updated["importance"] = coerce_int(updated.get("importance"), default=0)
    updated["source"] = str(updated.get("source") or source)
    updated["signature"] = str(
        updated.get("signature") or compute_memory_signature(body, memory_type, category)
    )
    updated["created_at"] = created_at
    updated["updated_at"] = updated_at
    updated["ttl_days"] = coerce_optional_int(updated.get("ttl_days"))
    updated["disabled"] = coerce_bool(updated.get("disabled"), default=False)
    updated["supersedes"] = list(coerce_str_list(updated.get("supersedes")))
    return updated


def first_content_line(body: str, *, limit: int = 200) -> str:
    """Return the first useful body line for descriptions."""

    for line in body.splitlines():
        stripped = line.strip()
        if stripped and stripped != "---" and not stripped.startswith("#"):
            return stripped[:limit]
    return ""


def _load_frontmatter(raw_frontmatter: str) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): value for key, value in loaded.items()}


def _format_yaml_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def _mtime_timestamp(path: Path) -> str:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        modified = utc_now()
    return format_datetime(modified)


def _generate_unique_memory_id(
    *,
    now: datetime | None = None,
    seen_ids: set[str] | None = None,
) -> str:
    while True:
        memory_id = generate_memory_id(now=now)
        if seen_ids is None or memory_id not in seen_ids:
            return memory_id


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
