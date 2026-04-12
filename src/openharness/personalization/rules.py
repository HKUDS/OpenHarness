"""Local rules file management."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_RULES_DIR = Path("~/.openharness/local_rules").expanduser()
_RULES_FILE = _RULES_DIR / "rules.md"
_FACTS_FILE = _RULES_DIR / "facts.json"


def _ensure_dir() -> None:
    _RULES_DIR.mkdir(parents=True, exist_ok=True)


def load_local_rules() -> str:
    """Load the local rules markdown, or empty string if none exist."""
    if _RULES_FILE.exists():
        return _RULES_FILE.read_text(encoding="utf-8").strip()
    return ""


def save_local_rules(content: str) -> Path:
    """Write local rules markdown."""
    _ensure_dir()
    _RULES_FILE.write_text(content.strip() + "\n", encoding="utf-8")
    return _RULES_FILE


def load_facts() -> dict:
    """Load extracted facts as a dict."""
    if _FACTS_FILE.exists():
        return json.loads(_FACTS_FILE.read_text(encoding="utf-8"))
    return {"facts": [], "last_updated": None}


def save_facts(facts: dict) -> None:
    """Persist extracted facts."""
    _ensure_dir()
    facts["last_updated"] = datetime.now(timezone.utc).isoformat()
    _FACTS_FILE.write_text(
        json.dumps(facts, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def merge_facts(existing: dict, new_facts: list[dict]) -> dict:
    """Merge new facts into existing, deduplicating by key."""
    by_key = {}
    for f in existing.get("facts", []):
        by_key[f["key"]] = f
    for f in new_facts:
        key = f.get("key", "")
        if key:
            if key in by_key:
                # Update with newer value, keep higher confidence
                old = by_key[key]
                if f.get("confidence", 0) >= old.get("confidence", 0):
                    by_key[key] = f
            else:
                by_key[key] = f
    return {"facts": list(by_key.values())}
