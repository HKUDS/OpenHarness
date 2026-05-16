"""Helpers for managing memory files."""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path
import re
from re import sub

from openharness.memory.provider import get_memory_provider
from openharness.memory.paths import get_memory_entrypoint, get_project_memory_dir, get_project_memory_entries_dir
from openharness.memory.scan import _parse_memory_file, scan_memory_files_in_file_store, write_memory_index
from openharness.memory.types import MemoryHeader
from openharness.utils.file_lock import exclusive_file_lock
from openharness.utils.fs import atomic_write_text


_MAX_MEMORY_FILENAME_CHARS = 72
_GENERIC_MEMORY_FILENAME_STEMS = {"", "memory", "entry"}
_MEMORY_TYPE_GROUPS = {
	"guardrail": "guardrail_family",
	"forbidden_command": "guardrail_family",
	"protected_path": "guardrail_family",
	"style_rule": "style_rule_family",
	"naming_rule": "style_rule_family",
	"validation_rule": "style_rule_family",
	"retry_rule": "style_rule_family",
}


def _memory_lock_path(cwd: str | Path) -> Path:
	return get_project_memory_dir(cwd) / ".memory.lock"


def list_memory_files_in_file_store(cwd: str | Path) -> list[Path]:
	"""List memory markdown files for the project."""
	return [header.path for header in scan_memory_files_in_file_store(cwd, max_files=None)]


def _slugify_english_memory_name(
	value: str,
	*,
	max_length: int = _MAX_MEMORY_FILENAME_CHARS,
	fallback: str = "memory",
) -> str:
	normalized = " ".join(value.split()).strip().lower()
	normalized = normalized.replace("/", " ").replace("\\", " ").replace(":", " ")
	slug = sub(r"[^a-z0-9]+", "_", normalized)
	slug = sub(r"_+", "_", slug).strip("._ ")
	if len(slug) <= max_length:
		return slug or fallback
	tokens = [token for token in slug.split("_") if token]
	kept: list[str] = []
	kept_len = 0
	for token in tokens:
		extra = len(token) + (1 if kept else 0)
		if kept_len + extra > max_length - 9:
			break
		kept.append(token)
		kept_len += extra
	shortened = "_".join(kept).strip("._ ")
	if not shortened:
		shortened = slug[: max_length - 9].rstrip("._ ")
	suffix = sha1(slug.encode("utf-8")).hexdigest()[:8]
	return f"{shortened}_{suffix}" if shortened else f"{fallback}_{suffix}"


def _ascii_tokens(text: str) -> list[str]:
	return re.findall(r"[A-Za-z0-9]+", text)


def _first_memory_content_line(content: str) -> str:
	for line in content.splitlines():
		stripped = line.strip()
		if stripped:
			return sub(r"[。！？.!?].*$", "", stripped)[:120]
	return ""


def _memory_filename_stem(title: str, description: str, content: str, key: str, memory_type: str) -> str:
	key_slug = _slugify_english_memory_name(key, fallback="")
	if key_slug not in _GENERIC_MEMORY_FILENAME_STEMS:
		return key_slug
	for candidate in (title, description, _first_memory_content_line(content)):
		tokens = _ascii_tokens(candidate)
		if tokens:
			slug = _slugify_english_memory_name(" ".join(tokens), fallback="")
			if slug not in _GENERIC_MEMORY_FILENAME_STEMS:
				return slug
	type_slug = _slugify_english_memory_name(memory_type, fallback="")
	if type_slug not in _GENERIC_MEMORY_FILENAME_STEMS:
		suffix = sha1(f"{title}\n{description}\n{content}".encode("utf-8")).hexdigest()[:8]
		return f"{type_slug}_{suffix}"
	return f"memory_{sha1((key or title or content).encode('utf-8')).hexdigest()[:8]}"


def _normalize_frontmatter_value(value: str) -> str:
	cleaned = " ".join(value.split()).strip()
	return cleaned.replace('"', "'")


def _normalize_semantic_value(value: str) -> str:
	return " ".join(value.split()).strip().casefold()


def _default_description(content: str) -> str:
	for line in content.splitlines():
		stripped = line.strip()
		if stripped:
			return stripped[:200]
	return ""


def _render_memory_document(
	*,
	key: str,
	title: str,
	content: str,
	description: str,
	memory_type: str,
) -> str:
	frontmatter = ["---", f"key: {_normalize_frontmatter_value(key)}", f"name: {_normalize_frontmatter_value(title)}"]
	normalized_description = _normalize_frontmatter_value(description)
	if normalized_description:
		frontmatter.append(f"description: {normalized_description}")
	normalized_type = _normalize_frontmatter_value(memory_type)
	if normalized_type:
		frontmatter.append(f"type: {normalized_type}")
	frontmatter.extend(["---", ""])
	return "\n".join(frontmatter) + content.strip() + "\n"


def _find_memory_file_by_key(headers: list[MemoryHeader], key: str) -> Path | None:
	normalized = key.strip()
	if not normalized:
		return None
	for header in headers:
		if header.memory_key == normalized:
			return header.path
	return None


def _memory_type_group(value: str) -> str:
	normalized = _normalize_semantic_value(value)
	return _MEMORY_TYPE_GROUPS.get(normalized, normalized)


def _memory_types_are_compatible(existing_type: str, incoming_type: str) -> bool:
	existing = _normalize_semantic_value(existing_type)
	incoming = _normalize_semantic_value(incoming_type)
	if not existing or not incoming or existing == incoming:
		return True
	return _memory_type_group(existing) == _memory_type_group(incoming)


def _find_semantic_duplicate_paths(headers: list[MemoryHeader], title: str, memory_type: str) -> list[Path]:
	normalized_title = _normalize_semantic_value(title)
	if not normalized_title:
		return []

	matches = [
		header
		for header in headers
		if _normalize_semantic_value(header.title) == normalized_title
		and _memory_types_are_compatible(header.memory_type, memory_type)
	]
	matches.sort(key=lambda header: header.modified_at, reverse=True)
	return [header.path for header in matches]


def _replace_memory_header(
	headers: list[MemoryHeader],
	*,
	path: Path,
	rendered: str,
	removed_paths: list[Path],
) -> list[MemoryHeader]:
	remaining = [header for header in headers if header.path != path and header.path not in removed_paths]
	remaining.append(_parse_memory_file(path, rendered))
	remaining.sort(key=lambda header: header.modified_at, reverse=True)
	return remaining


def _memory_relative_path(entrypoint: Path, path: Path) -> str:
	return path.relative_to(entrypoint.parent).as_posix()


def _allocate_memory_path(
	cwd: str | Path,
	title: str,
	key: str,
	description: str = "",
	content: str = "",
	memory_type: str = "",
) -> Path:
	entries_dir = get_project_memory_entries_dir(cwd)
	slug = _memory_filename_stem(title, description, content, key, memory_type)
	candidate = entries_dir / f"{slug}.md"
	if not candidate.exists():
		return candidate
	suffix_source = key.strip() or f"{title}\n{description}\n{content}"
	suffix = sha1(suffix_source.encode("utf-8")).hexdigest()[:8]
	if suffix and candidate.stem != f"{slug}_{suffix}":
		alt = entries_dir / f"{slug}_{suffix}.md"
		if not alt.exists():
			return alt
	counter = 2
	while True:
		alt = entries_dir / f"{slug}_{counter}.md"
		if not alt.exists():
			return alt
		counter += 1


def _sync_memory_index(entrypoint: Path, *, path: Path, title: str) -> None:
	relative_path = _memory_relative_path(entrypoint, path)
	entry_line = f"- [{title}]({relative_path})"
	existing_lines = entrypoint.read_text(encoding="utf-8").splitlines() if entrypoint.exists() else ["# Memory Index"]
	replaced = False
	updated_lines: list[str] = []
	for line in existing_lines:
		if f"({relative_path})" in line:
			updated_lines.append(entry_line)
			replaced = True
		else:
			updated_lines.append(line)
	if not replaced:
		updated_lines.append(entry_line)
	atomic_write_text(entrypoint, "\n".join(updated_lines).rstrip() + "\n")


def _prune_memory_index_paths(entrypoint: Path, paths: list[Path]) -> None:
	if not paths or not entrypoint.exists():
		return
	removed_names = {_memory_relative_path(entrypoint, path) for path in paths}
	updated_lines = [
		line
		for line in entrypoint.read_text(encoding="utf-8").splitlines()
		if not any(f"({name})" in line for name in removed_names)
	]
	atomic_write_text(entrypoint, "\n".join(updated_lines).rstrip() + "\n")


def upsert_memory_entry_in_file_store(
	cwd: str | Path,
	*,
	key: str,
	title: str,
	content: str,
	description: str = "",
	memory_type: str = "",
) -> tuple[Path, str]:
	"""Create or update a structured memory entry keyed by durable identity."""
	normalized_key = key.strip()
	if not normalized_key:
		raise ValueError("Memory key must not be empty")
	normalized_title = title.strip() or normalized_key
	normalized_content = content.strip()
	if not normalized_content:
		raise ValueError("Memory content must not be empty")
	normalized_description = description.strip() or _default_description(normalized_content)
	normalized_type = memory_type.strip()

	with exclusive_file_lock(_memory_lock_path(cwd)):
		headers = scan_memory_files_in_file_store(cwd, max_files=None)
		path = _find_memory_file_by_key(headers, normalized_key)
		semantic_matches = _find_semantic_duplicate_paths(headers, normalized_title, normalized_type)
		duplicate_paths: list[Path] = []
		if path is None:
			if semantic_matches:
				path = semantic_matches[0]
				duplicate_paths = semantic_matches[1:]
		else:
			duplicate_paths = [candidate for candidate in semantic_matches if candidate != path]
		status = "created"
		if path is None:
			path = _allocate_memory_path(
				cwd,
				normalized_title,
				normalized_key,
				normalized_description,
				normalized_content,
				normalized_type,
			)
		else:
			status = "updated"

		rendered = _render_memory_document(
			key=normalized_key,
			title=normalized_title,
			content=normalized_content,
			description=normalized_description,
			memory_type=normalized_type,
		)
		if path.exists() and path.read_text(encoding="utf-8") == rendered:
			status = "unchanged"
		else:
			atomic_write_text(path, rendered)

		for duplicate_path in duplicate_paths:
			if duplicate_path.exists() and duplicate_path != path:
				duplicate_path.unlink()

		entrypoint = get_memory_entrypoint(cwd)
		_prune_memory_index_paths(entrypoint, duplicate_paths)
		_sync_memory_index(entrypoint, path=path, title=normalized_title)
		write_memory_index(
			cwd,
			_replace_memory_header(headers, path=path, rendered=rendered, removed_paths=duplicate_paths),
		)
		if duplicate_paths and status == "unchanged":
			status = "updated"
	return path, status


def add_memory_entry_in_file_store(cwd: str | Path, title: str, content: str) -> Path:
	"""Create a memory file and append it to MEMORY.md."""
	with exclusive_file_lock(_memory_lock_path(cwd)):
		headers = scan_memory_files_in_file_store(cwd, max_files=None)
		path = _allocate_memory_path(
			cwd,
			title.strip(),
			"",
			_default_description(content),
			content,
			"",
		)
		atomic_write_text(path, content.strip() + "\n")
		_sync_memory_index(get_memory_entrypoint(cwd), path=path, title=title.strip() or path.stem)
		write_memory_index(cwd, _replace_memory_header(headers, path=path, rendered=content.strip() + "\n", removed_paths=[]))
	return path


def remove_memory_entry_in_file_store(cwd: str | Path, name: str) -> bool:
	"""Delete a memory file and remove its index entry."""
	identifier = name.strip()
	with exclusive_file_lock(_memory_lock_path(cwd)):
		headers = scan_memory_files_in_file_store(cwd, max_files=None)
		entrypoint = get_memory_entrypoint(cwd)
		matches = [
			header.path
			for header in headers
			if header.path.stem == identifier
			or header.path.name == identifier
			or _memory_relative_path(entrypoint, header.path) == identifier
		]
		path = matches[0] if matches else _find_memory_file_by_key(headers, identifier)
		if path is None:
			return False
		if path.exists():
			path.unlink()

		if entrypoint.exists():
			_prune_memory_index_paths(entrypoint, [path])
		write_memory_index(cwd, [header for header in headers if header.path != path])
	return True


def list_memory_files(cwd: str | Path) -> list[Path]:
	"""List memory markdown files from the active memory provider."""
	return get_memory_provider(cwd).list_memory_files(cwd)


def upsert_memory_entry(
	cwd: str | Path,
	*,
	key: str,
	title: str,
	content: str,
	description: str = "",
	memory_type: str = "",
) -> tuple[Path, str]:
	"""Create or update a structured memory entry via the active provider."""
	return get_memory_provider(cwd).upsert_memory_entry(
		cwd,
		key=key,
		title=title,
		content=content,
		description=description,
		memory_type=memory_type,
	)


def add_memory_entry(cwd: str | Path, title: str, content: str) -> Path:
	"""Create a memory entry via the active provider."""
	return get_memory_provider(cwd).add_memory_entry(cwd, title, content)


def remove_memory_entry(cwd: str | Path, name: str) -> bool:
	"""Delete a memory entry via the active provider."""
	return get_memory_provider(cwd).remove_memory_entry(cwd, name)


__all__ = ["add_memory_entry", "list_memory_files", "remove_memory_entry", "upsert_memory_entry"]
