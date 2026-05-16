"""Extract local rules from session conversation history."""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

_RULE_KEY_TYPES = {
    "pitfall",
    "guardrail",
    "forbidden_command",
    "protected_path",
    "style_rule",
    "naming_rule",
    "validation_rule",
    "retry_rule",
}


def _compile_rule_pattern(*labels: str, optional_colon: bool = False) -> re.Pattern:
    escaped = "|".join(re.escape(label) for label in labels)
    separator = r"\s*:?\s*" if optional_colon else r"\s*:\s*"
    return re.compile(rf"(?im)^(?:[-*•]\s*)?(?:{escaped}){separator}(.+)$")


def _normalize_extraction_input(text: str) -> str:
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("：", ":")
        .replace("（", "(")
        .replace("）", ")")
        .replace("　", " ")
    )


def _clean_fact_value(value: str) -> str:
    cleaned = " ".join(value.split()).strip()
    cleaned = cleaned.strip("`'\"“”‘’[]()（）")
    cleaned = cleaned.rstrip("。；：，,.!！?？:;")
    return cleaned.strip()


def _rule_fact_key(fact_type: str, value: str) -> str:
    if fact_type not in _RULE_KEY_TYPES:
        return value
    return " ".join(value.split()).strip().casefold()

# Patterns that indicate durable facts, guardrails, and workflow rules worth capturing.
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
    ("pitfall", "Pitfall", _compile_rule_pattern(
        "pitfall", "gotcha", "common mistake", "easy mistake", "repair pattern", "fix pattern", "workaround",
        "高频易错点", "常见坑", "易错点", "避坑", "避坑经验", "修复套路", "修复模式"
    )),
    ("guardrail", "Guardrail", _compile_rule_pattern(
        "guardrail", "safety rule", "security rule", "red line", "hard rule", "fixed constraint",
        "安全红线", "红线规则", "硬规则", "固定约束", "长期约束", "保护规则"
    )),
    ("forbidden_command", "Forbidden command", _compile_rule_pattern(
        "forbidden command", "never run", "do not run", "don't run",
        "禁止命令", "不要运行", "不要执行", "禁止执行", "不可运行", "不可执行",
        optional_colon=True,
    )),
    ("protected_path", "Protected path", _compile_rule_pattern(
        "protected file", "protected path", "do not delete", "don't delete", "never delete", "do not edit", "don't edit", "never edit",
        "保护文件", "保护路径", "不要删除", "禁止删除", "不可删除", "不要修改", "禁止修改", "不可修改",
        optional_colon=True,
    )),
    ("style_rule", "Style rule", _compile_rule_pattern(
        "output style", "response style", "reply style", "style rule",
        "输出风格", "回复风格", "回答风格", "风格规则"
    )),
    ("naming_rule", "Naming rule", _compile_rule_pattern(
        "naming rule", "naming convention", "命名规则", "命名约定"
    )),
    ("validation_rule", "Validation rule", _compile_rule_pattern(
        "validation rule", "validation step", "always validate with", "verify with",
        "验证规则", "验证步骤", "校验规则", "校验步骤",
        optional_colon=True,
    )),
    ("retry_rule", "Retry rule", _compile_rule_pattern(
        "retry rule", "retry strategy", "retry policy", "重试规则", "重试策略", "重试机制"
    )),
]


def extract_facts_from_text(text: str) -> list[dict]:
    """Extract environment-specific facts from conversation text using patterns."""
    facts = []
    seen_keys = set()
    normalized_text = _normalize_extraction_input(text)

    for fact_type, label, pattern in _FACT_PATTERNS:
        for match in pattern.finditer(normalized_text):
            value = match.group(1) if match.lastindex else match.group(0)
            value = _clean_fact_value(value)
            if not value or len(value) < 3:
                continue

            # Skip common false positives
            if fact_type == "ip_address" and value.startswith(("0.", "255.", "127.0.0.1")):
                continue

            key = f"{fact_type}:{_rule_fact_key(fact_type, value)}"
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
        "pitfall": "Pitfalls And Fix Patterns",
        "guardrail": "Guardrails",
        "forbidden_command": "Forbidden Commands",
        "protected_path": "Protected Paths",
        "style_rule": "Style Rules",
        "naming_rule": "Naming Rules",
        "validation_rule": "Validation Rules",
        "retry_rule": "Retry Rules",
    }

    for fact_type, items in grouped.items():
        title = section_titles.get(fact_type, fact_type.replace("_", " ").title())
        lines.append(f"## {title}")
        lines.append("")
        for item in items:
            lines.append(f"- `{item['value']}`")
        lines.append("")

    return "\n".join(lines)
