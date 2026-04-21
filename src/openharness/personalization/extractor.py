"""Extract local rules from session conversation history."""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Patterns that indicate environment-specific facts worth capturing
_FACT_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("ssh_host", "SSH connection", re.compile(
        r"ssh\s+(?:-[io]\s+\S+\s+)*(\S+@[\d.]+|\S+@\S+)", re.IGNORECASE
    )),
    ("ip_address", "Server IP", re.compile(
        r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    )),
    ("data_path", "Data path", re.compile(
        r"(/(?:ext|mnt|home|data|root)\S*/(?:data\S*|landing|derived|reference)\S*)"
    )),
    ("conda_env", "Conda environment", re.compile(
        r"conda\s+activate\s+(\S+)"
    )),
    ("python_env", "Python version", re.compile(
        r"[Pp]ython\s*(3\.\d+(?:\.\d+)?)"
    )),
    ("api_endpoint", "API endpoint", re.compile(
        r"(https?://\S+/v\d+/?)\b"
    )),
    ("env_var", "Environment variable", re.compile(
        r"export\s+([A-Z][A-Z0-9_]+)(?:=\S+)?"
    )),
    ("git_remote", "Git remote", re.compile(
        r"(?:github|gitlab)\.com[:/](\S+?)(?:\.git)?"
    )),
    ("ray_cluster", "Ray cluster", re.compile(
        r"ray\s+(?:start|init|submit)\b.*?(--address\s+\S+|\d+\.\d+\.\d+\.\d+:\d+)",
        re.IGNORECASE,
    )),
    ("cron_schedule", "Cron schedule", re.compile(
        r"((?:\d+|\*)\s+(?:\d+|\*)\s+(?:\d+|\*)\s+(?:\d+|\*)\s+(?:\d+|\*))\s+\S+"
    )),
]


def extract_facts_from_text(text: str) -> list[dict]:
    """Extract environment-specific facts from conversation text using patterns."""
    facts = []
    seen_keys = set()

    for fact_type, label, pattern in _FACT_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)
            value = value.strip().rstrip(".,;:)")
            if not value or len(value) < 3:
                continue

            # Skip common false positives
            if fact_type == "ip_address" and value.startswith(("0.", "255.", "127.0.0.1")):
                continue

            key = f"{fact_type}:{value}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            facts.append({
                "key": key,
                "type": fact_type,
                "label": label,
                "value": value,
                "confidence": 0.7,
            })

    return facts


def extract_local_rules(session_messages: list[dict]) -> list[dict]:
    """Extract environment facts from a list of session messages.

    Args:
        session_messages: List of message dicts with 'role' and 'content' keys.

    Returns:
        List of fact dicts with key, type, label, value, confidence.
    """
    all_text = []
    for msg in session_messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            all_text.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    all_text.append(block["text"])

    combined = "\n".join(all_text)
    return extract_facts_from_text(combined)


def facts_to_rules_markdown(facts: list[dict]) -> str:
    """Convert extracted facts to a markdown rules document."""
    if not facts:
        return ""

    grouped: dict[str, list[dict]] = {}
    for f in facts:
        grouped.setdefault(f["type"], []).append(f)

    lines = [
        "# Local Environment Rules",
        "",
        "*Auto-generated from session history. Do not edit manually.*",
        "",
    ]

    section_titles = {
        "ssh_host": "SSH Hosts",
        "ip_address": "Known Servers",
        "data_path": "Data Paths",
        "conda_env": "Python Environments",
        "python_env": "Python Versions",
        "api_endpoint": "API Endpoints",
        "env_var": "Environment Variables",
        "git_remote": "Git Repositories",
        "ray_cluster": "Ray Cluster Config",
        "cron_schedule": "Scheduled Jobs",
    }

    for fact_type, items in grouped.items():
        title = section_titles.get(fact_type, fact_type.replace("_", " ").title())
        lines.append(f"## {title}")
        lines.append("")
        for item in items:
            lines.append(f"- `{item['value']}`")
        lines.append("")

    return "\n".join(lines)
