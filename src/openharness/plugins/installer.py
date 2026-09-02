"""Plugin installation helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
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


def install_plugin_from_url(url: str) -> Path:
    """Clone a git URL into a temp directory and install from there."""
    clone_url = url.removeprefix("git+")
    with tempfile.TemporaryDirectory() as tmp:
        cloned = Path(tmp) / "cloned"
        result = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, str(cloned)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed for {url!r}:\n{result.stderr.strip()}")
        manifest = cloned / "plugin.json"
        if manifest.exists():
            name = json.loads(manifest.read_text())["name"]
            # Rename so install_plugin_from_path uses the declared name as the
            # destination directory. Once PR #354 lands (install_plugin_from_path
            # reads name from plugin.json directly), this rename can be removed.
            named = Path(tmp) / name
            cloned.rename(named)
            return install_plugin_from_path(named)
        return install_plugin_from_path(cloned)


def uninstall_plugin(name: str) -> bool:
    """Remove a user plugin by directory name."""
    path = _resolve_user_plugin_dir(name)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True
