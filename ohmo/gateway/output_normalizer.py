"""User-facing output normalization for ohmo gateway channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from ohmo.gateway.runtime import GatewayStreamUpdate

REMOTE_CHANNELS = {
    "discord",
    "dingtalk",
    "email",
    "feishu",
    "matrix",
    "qq",
    "slack",
    "telegram",
    "wechat",
    "whatsapp",
}

_LOCAL_PATH_RE = re.compile(
    r"(?P<path>(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|(?<![:/])/)(?:[^\r\n`\"'<>|?*\x00])+)",
)
_PATH_CODE_BLOCK_RE = re.compile(
    r"```(?:text|txt|powershell|shell|bash)?\s*\n(?P<body>.*?)\n```",
    re.IGNORECASE | re.DOTALL,
)
_URL_RE = re.compile(r"https?://[^\s`<>\"']+")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@dataclass
class GatewayOutputState:
    """Per-message state for channel-facing output normalization."""

    stage_keys: set[str] = field(default_factory=set)
    media_paths: set[str] = field(default_factory=set)
    has_image_media: bool = False
    saw_media: bool = False


def normalize_gateway_update(
    update: GatewayStreamUpdate,
    *,
    channel: str,
    content: str,
    mode: str,
    state: GatewayOutputState,
) -> list[GatewayStreamUpdate]:
    """Return channel-facing updates for one runtime update."""
    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "debug" or channel not in REMOTE_CHANNELS:
        _remember_update_media(state, update)
        return [update]
    if update.kind == "media":
        _remember_update_media(state, update)
        return [_strip_media_caption(update)]
    if update.kind == "final":
        _remember_update_media(state, update)
        final_text = normalize_final_reply(update.text, state=state)
        if not final_text:
            return []
        metadata = dict(update.metadata or {})
        return [
            GatewayStreamUpdate(
                kind=update.kind,
                text=final_text,
                metadata=metadata,
                media=list(getattr(update, "media", None) or metadata.get("_media") or []),
            )
        ]
    if update.kind == "error":
        return [update]
    if normalized_mode == "silent":
        return []
    if update.kind == "progress":
        return _normalize_progress(update, content=content, state=state)
    if update.kind == "tool_hint":
        return _normalize_tool_hint(update, content=content, state=state)
    return [update]


def normalize_final_reply(reply: str, *, state: GatewayOutputState) -> str:
    """Remove local paths already represented as media from a final reply."""
    text, urls = _protect_urls(reply or "")
    text = _remove_path_code_blocks(text, state)
    text = _LOCAL_PATH_RE.sub(lambda match: _replace_local_path(match.group("path"), state), text)
    text = _restore_urls(text, urls)
    text = _clean_text(text)
    if not text and state.saw_media:
        return "已生成图片。" if state.has_image_media else "已生成文件。"
    if state.has_image_media and _only_acknowledges_generated_image(text):
        return "已生成图片。"
    return text


def _normalize_progress(
    update: GatewayStreamUpdate,
    *,
    content: str,
    state: GatewayOutputState,
) -> list[GatewayStreamUpdate]:
    if "thinking" in state.stage_keys:
        return []
    state.stage_keys.add("thinking")
    return [_copy_with_text(update, "正在处理..." if _prefers_chinese(content) else "Working on it...")]


def _normalize_tool_hint(
    update: GatewayStreamUpdate,
    *,
    content: str,
    state: GatewayOutputState,
) -> list[GatewayStreamUpdate]:
    metadata = update.metadata or {}
    tool_name = str(metadata.get("_tool_name") or "").strip()
    stage = _stage_for_tool(tool_name)
    if not stage:
        return []
    if stage in state.stage_keys:
        return []
    state.stage_keys.add(stage)
    text = _stage_text(stage, content)
    return [_copy_with_text(update, text)]


def _stage_for_tool(tool_name: str) -> str | None:
    normalized = tool_name.strip().lower().replace("-", "_")
    if normalized in {"web_search", "web_fetch"}:
        return "searching"
    if normalized == "image_generation":
        return "generating_image"
    if normalized in {"shell", "bash", "python", "run_command"}:
        return "processing_files"
    return None


def _stage_text(stage: str, content: str) -> str:
    zh = _prefers_chinese(content)
    if stage == "searching":
        return "正在检索资料..." if zh else "Searching..."
    if stage == "generating_image":
        return "正在生成图片..." if zh else "Generating image..."
    if stage == "processing_files":
        return "正在处理文件..." if zh else "Processing files..."
    return "正在处理..." if zh else "Working on it..."


def _copy_with_text(update: GatewayStreamUpdate, text: str) -> GatewayStreamUpdate:
    return GatewayStreamUpdate(
        kind=update.kind,
        text=text,
        metadata=dict(update.metadata or {}),
        media=list(getattr(update, "media", None) or []),
    )


def _strip_media_caption(update: GatewayStreamUpdate) -> GatewayStreamUpdate:
    return GatewayStreamUpdate(
        kind=update.kind,
        text="",
        metadata=dict(update.metadata or {}),
        media=list(getattr(update, "media", None) or []),
    )


def _remember_update_media(state: GatewayOutputState, update: GatewayStreamUpdate) -> None:
    raw_media = getattr(update, "media", None) or (update.metadata or {}).get("_media") or []
    if isinstance(raw_media, str):
        candidates = [raw_media]
    elif isinstance(raw_media, list):
        candidates = [str(item) for item in raw_media if isinstance(item, str) and item.strip()]
    else:
        candidates = []
    for raw in candidates:
        state.saw_media = True
        resolved = _normalize_path(raw)
        state.media_paths.add(resolved)
        if Path(raw).suffix.lower() in _IMAGE_SUFFIXES:
            state.has_image_media = True


def _remove_path_code_blocks(text: str, state: GatewayOutputState) -> str:
    def replace(match: re.Match[str]) -> str:
        body = match.group("body").strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if lines and all(_looks_like_local_path(line) for line in lines):
            kept = [_replace_local_path(line, state) for line in lines]
            kept = [item for item in kept if item]
            return "\n".join(kept)
        return match.group(0)

    return _PATH_CODE_BLOCK_RE.sub(replace, text)


def _replace_local_path(path_text: str, state: GatewayOutputState) -> str:
    cleaned = path_text.strip().rstrip(".,;:，。；：、)]}")
    normalized = _normalize_path(cleaned)
    if normalized in state.media_paths:
        return ""
    path = Path(cleaned)
    return path.name if path.name else ""


def _normalize_path(path_text: str) -> str:
    try:
        return str(Path(path_text).expanduser().resolve(strict=False))
    except Exception:
        return path_text


def _looks_like_local_path(text: str) -> bool:
    return bool(_LOCAL_PATH_RE.fullmatch(text.strip()))


def _clean_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    cleaned: list[str] = []
    blank = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if cleaned and not blank:
                cleaned.append("")
            blank = True
            continue
        cleaned.append(stripped)
        blank = False
    return "\n".join(cleaned).strip()


def _protect_urls(text: str) -> tuple[str, dict[str, str]]:
    urls: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        key = f"__OHMO_URL_{len(urls)}__"
        urls[key] = match.group(0)
        return key

    return _URL_RE.sub(replace, text), urls


def _restore_urls(text: str, urls: dict[str, str]) -> str:
    for key, value in urls.items():
        text = text.replace(key, value)
    return text


def _only_acknowledges_generated_image(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text or "")
    return normalized in {
        "已生成图片：",
        "已生成图片:",
        "已生成图片。",
        "已生成图片",
        "已生成信息图：",
        "已生成信息图:",
        "已生成信息图。",
        "已生成信息图",
    }


def _prefers_chinese(content: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", content or ""))


def _normalize_mode(mode: str) -> str:
    normalized = (mode or "user").strip().lower()
    if normalized in {"debug", "silent", "user"}:
        return normalized
    return "user"
