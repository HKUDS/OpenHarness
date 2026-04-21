"""Credential storage for OpenHarness.

Default backend: ~/.openharness/credentials.json with mode 600.
Optional backend: system keyring (if the `keyring` package is installed
and a usable backend is present).

Security model
--------------
When no keyring backend is available (common in containers, CI, and WSL),
credentials are stored as **plain-text JSON** protected only by POSIX file
permissions (mode 600).  The ``_obfuscate`` / ``_deobfuscate`` helpers in
this module are a lightweight XOR round-trip used elsewhere for non-secret
data; they are **not** encryption and must not be used to protect secrets.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openharness.config.paths import get_config_dir
from openharness.utils.file_lock import exclusive_file_lock
from openharness.utils.fs import atomic_write_text

log = logging.getLogger(__name__)

_CREDS_FILE_NAME = "credentials.json"
_KEYRING_SERVICE = "openharness"


def _creds_lock_path() -> Path:
    return _creds_path().with_suffix(".json.lock")


@dataclass(frozen=True)
class ExternalAuthBinding:
    """Pointer to credentials managed by an external CLI."""

    provider: str
    source_path: str
    source_kind: str
    managed_by: str
    profile_label: str = ""


# ---------------------------------------------------------------------------
# File-based backend (always available)
# ---------------------------------------------------------------------------


def _creds_path() -> Path:
    return get_config_dir() / _CREDS_FILE_NAME


def _load_creds_file() -> dict[str, Any]:
    path = _creds_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read credentials file: %s", exc)
        return {}


def _save_creds_file(data: dict[str, Any]) -> None:
    path = _creds_path()
    atomic_write_text(
        path,
        json.dumps(data, indent=2) + "\n",
        mode=0o600,
    )


# ---------------------------------------------------------------------------
# Keyring backend (optional)
# ---------------------------------------------------------------------------


_keyring_checked: bool = False
_keyring_usable: bool = False


def _keyring_available() -> bool:
    """Return True when a usable system keyring backend is present.

    The check is cached after the first call so the "Keyring load failed"
    warning is emitted at most once per process.
    """
    global _keyring_checked, _keyring_usable  # noqa: PLW0603
    if _keyring_checked:
        return _keyring_usable
    _keyring_checked = True
    try:
        import keyring

        # Probe the backend — merely importing keyring is not enough because
        # the package may be installed without a functioning backend (e.g. on
        # headless Linux / WSL / containers).
        keyring.get_password(_KEYRING_SERVICE, "__probe__")
        _keyring_usable = True
    except ImportError:
        _keyring_usable = False
    except Exception as exc:
        log.info("System keyring unavailable, using file backend: %s", exc)
        _keyring_usable = False
    return _keyring_usable


def _keyring_key(provider: str, key: str) -> str:
    return f"{provider}:{key}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def store_credential(provider: str, key: str, value: str, *, use_keyring: bool | None = None) -> None:
    """Persist a credential for *provider* under *key*.

    If *use_keyring* is not set, keyring is used when available.
    """
    if use_keyring is None:
        use_keyring = _keyring_available()

    if use_keyring:
        try:
            import keyring

            keyring.set_password(_KEYRING_SERVICE, _keyring_key(provider, key), value)
            log.debug("Stored %s/%s in keyring", provider, key)
            return
        except Exception as exc:
            log.warning("Keyring store failed, falling back to file: %s", exc)

    with exclusive_file_lock(_creds_lock_path()):
        data = _load_creds_file()
        data.setdefault(provider, {})[key] = value
        _save_creds_file(data)
    log.debug("Stored %s/%s in credentials file", provider, key)


def load_credential(provider: str, key: str, *, use_keyring: bool | None = None) -> str | None:
    """Return the stored credential, or None if not found."""
    if use_keyring is None:
        use_keyring = _keyring_available()

    if use_keyring:
        try:
            import keyring

            value = keyring.get_password(_KEYRING_SERVICE, _keyring_key(provider, key))
            if value is not None:
                return value
        except Exception as exc:
            log.warning("Keyring load failed, falling back to file: %s", exc)

    data = _load_creds_file()
    return data.get(provider, {}).get(key)


def clear_provider_credentials(provider: str, *, use_keyring: bool | None = None) -> None:
    """Remove all stored credentials for *provider*."""
    if use_keyring is None:
        use_keyring = _keyring_available()

    if use_keyring:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError

            # Try common keys; silently ignore missing ones.
            for key in ("api_key", "token", "github_token"):
                try:
                    keyring.delete_password(_KEYRING_SERVICE, _keyring_key(provider, key))
                except (PasswordDeleteError, Exception):
                    pass
        except ImportError:
            pass

    with exclusive_file_lock(_creds_lock_path()):
        data = _load_creds_file()
        if provider in data:
            del data[provider]
            _save_creds_file(data)
    log.debug("Cleared credentials for provider: %s", provider)


def list_stored_providers() -> list[str]:
    """Return the list of providers that have credentials in the file store."""
    return list(_load_creds_file().keys())


def store_external_binding(binding: ExternalAuthBinding) -> None:
    """Persist metadata describing an external auth source for *provider*."""
    with exclusive_file_lock(_creds_lock_path()):
        data = _load_creds_file()
        entry = data.setdefault(binding.provider, {})
        entry["external_binding"] = asdict(binding)
        _save_creds_file(data)
    log.debug("Stored external auth binding for provider: %s", binding.provider)


def load_external_binding(provider: str) -> ExternalAuthBinding | None:
    """Load external auth binding metadata for *provider* if present."""
    entry = _load_creds_file().get(provider, {})
    if not isinstance(entry, dict):
        return None
    raw = entry.get("external_binding")
    if not isinstance(raw, dict):
        return None
    try:
        return ExternalAuthBinding(
            provider=str(raw["provider"]),
            source_path=str(raw["source_path"]),
            source_kind=str(raw["source_kind"]),
            managed_by=str(raw["managed_by"]),
            profile_label=str(raw.get("profile_label", "") or ""),
        )
    except KeyError:
        log.warning("Ignoring malformed external auth binding for provider: %s", provider)
        return None


# ---------------------------------------------------------------------------
# Obfuscation helpers (XOR round-trip — NOT encryption)
# ---------------------------------------------------------------------------
# These exist for lightweight obfuscation of non-secret data (e.g. session
# tokens where the goal is to prevent casual reading, not resist attack).
# Do NOT use for API keys or passwords — those belong in the keyring or in
# the plain-text file protected by POSIX permissions.
# ---------------------------------------------------------------------------


def _obfuscation_key() -> bytes:
    """Return a per-user obfuscation key derived from the home directory path."""
    seed = str(Path.home()).encode() + b"openharness-v1"
    import hashlib

    return hashlib.sha256(seed).digest()


def _obfuscate(plaintext: str) -> str:
    """Lightly obfuscate *plaintext* (base64-encoded XOR).  **Not cryptographic.**"""
    import base64

    key = _obfuscation_key()
    data = plaintext.encode("utf-8")
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def _deobfuscate(ciphertext: str) -> str:
    """Reverse of :func:`_obfuscate`."""
    import base64

    key = _obfuscation_key()
    data = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return xored.decode("utf-8")


# Backward compatibility — deprecated, will be removed in a future version.
encrypt = _obfuscate
decrypt = _deobfuscate
