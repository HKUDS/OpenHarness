"""Plugin installation helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from openharness.plugins.loader import get_user_plugins_dir


def _resolve_user_plugin_dir(name: str) -> Path:
    """Resolve a user plugin name to a direct child of the plugin directory."""
    if not name or name != Path(name).name or "\\" in name:
        raise ValueError("invalid plugin name")

    plugins_dir = get_user_plugins_dir().resolve()
    path = (plugins_dir / name).resolve()
    if path.parent != plugins_dir:
        raise ValueError("invalid plugin name")
    return path


def install_plugin_from_path(source: str | Path) -> Path:
    """Install a plugin directory into the user plugin directory."""
    src = Path(source).resolve()
    dest = get_user_plugins_dir() / src.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def uninstall_plugin(name: str) -> bool:
    """Remove a user plugin by directory name."""
    path = _resolve_user_plugin_dir(name)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True
