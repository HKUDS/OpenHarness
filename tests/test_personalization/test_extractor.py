"""Tests for personalization fact extraction."""

from openharness.personalization.extractor import extract_facts_from_text, facts_to_rules_markdown
from openharness.personalization.rules import merge_facts


class TestExtractFacts:
    def test_extracts_ssh_host(self):
        text = "ssh konghm@192.168.91.212 'tail -20 /var/log/syslog'"
        facts = extract_facts_from_text(text)
        ssh_facts = [f for f in facts if f["type"] == "ssh_host"]
        assert len(ssh_facts) == 1
        assert "konghm@192.168.91.212" in ssh_facts[0]["value"]

    def test_extracts_data_path(self):
        text = "ls /ext/data_auto_stage/landing/CS_sp/1d/"
        facts = extract_facts_from_text(text)
        path_facts = [f for f in facts if f["type"] == "data_path"]
        assert any("/ext/data_auto_stage" in f["value"] for f in path_facts)

    def test_extracts_conda_env(self):
        text = "conda activate dev312"
        facts = extract_facts_from_text(text)
        conda_facts = [f for f in facts if f["type"] == "conda_env"]
        assert len(conda_facts) == 1
        assert conda_facts[0]["value"] == "dev312"

    def test_extracts_env_var(self):
        text = 'export OPENAI_BASE_URL="https://relay.nf.video/v1"'
        facts = extract_facts_from_text(text)
        env_facts = [f for f in facts if f["type"] == "env_var"]
        assert env_facts[0]["value"] == "OPENAI_BASE_URL"

    def test_env_var_does_not_capture_secret_value(self):
        text = "export OPENAI_API_KEY=sk-secret-value"
        facts = extract_facts_from_text(text)
        env_facts = [f for f in facts if f["type"] == "env_var"]
        assert env_facts[0]["value"] == "OPENAI_API_KEY"
        assert "sk-secret-value" not in env_facts[0]["value"]

    def test_extracts_api_endpoint(self):
        text = "curl https://api.minimax.chat/v1/chat/completions"
        facts = extract_facts_from_text(text)
        api_facts = [f for f in facts if f["type"] == "api_endpoint"]
        assert any("minimax" in f["value"] for f in api_facts)

    def test_skips_localhost(self):
        text = "ping 127.0.0.1"
        facts = extract_facts_from_text(text)
        ip_facts = [f for f in facts if f["type"] == "ip_address"]
        assert len(ip_facts) == 0

    def test_deduplicates(self):
        text = "ssh user@10.0.0.1\nssh user@10.0.0.1\nssh user@10.0.0.1"
        facts = extract_facts_from_text(text)
        ssh_facts = [f for f in facts if f["type"] == "ssh_host"]
        assert len(ssh_facts) == 1


class TestMergeFacts:
    def test_merge_new_facts(self):
        existing = {"facts": [{"key": "ssh_host:a@1.1.1.1", "value": "a@1.1.1.1", "confidence": 0.7}]}
        new = [{"key": "conda_env:dev312", "value": "dev312", "confidence": 0.7}]
        merged = merge_facts(existing, new)
        assert len(merged["facts"]) == 2

    def test_merge_updates_higher_confidence(self):
        existing = {"facts": [{"key": "ssh_host:a@1.1.1.1", "value": "a@1.1.1.1", "confidence": 0.5}]}
        new = [{"key": "ssh_host:a@1.1.1.1", "value": "a@1.1.1.1", "confidence": 0.9}]
        merged = merge_facts(existing, new)
        assert len(merged["facts"]) == 1
        assert merged["facts"][0]["confidence"] == 0.9

    def test_merge_keeps_existing_if_higher(self):
        existing = {"facts": [{"key": "ssh_host:a@1.1.1.1", "value": "a@1.1.1.1", "confidence": 0.9}]}
        new = [{"key": "ssh_host:a@1.1.1.1", "value": "a@1.1.1.1", "confidence": 0.5}]
        merged = merge_facts(existing, new)
        assert merged["facts"][0]["confidence"] == 0.9


class TestFactsToMarkdown:
    def test_empty_facts(self):
        assert facts_to_rules_markdown([]) == ""

    def test_generates_sections(self):
        facts = [
            {"key": "ssh_host:a@1.1", "type": "ssh_host", "value": "a@1.1", "confidence": 0.7},
            {"key": "conda_env:dev312", "type": "conda_env", "value": "dev312", "confidence": 0.7},
        ]
        md = facts_to_rules_markdown(facts)
        assert "## SSH Hosts" in md
        assert "## Python Environments" in md
        assert "`a@1.1`" in md
        assert "`dev312`" in md
