#!/usr/bin/env python3
"""
Demo script for adding and testing LLM providers in OpenHarness.

This script demonstrates the provider registry structure and how to add new providers.
It runs without requiring OpenHarness dependencies to be installed.

Usage:
    python scripts/demo_providers.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ProviderSpec:
    """One LLM provider's metadata."""
    name: str
    keywords: tuple[str, ...]
    env_key: str
    display_name: str = ""
    backend_type: str = "openai_compat"
    default_base_url: str = ""
    detect_by_key_prefix: str = ""
    detect_by_base_keyword: str = ""
    is_gateway: bool = False
    is_local: bool = False
    is_oauth: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.name.title()


# Sample providers (subset from the actual registry)
SAMPLE_PROVIDERS = (
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),
        env_key="ANTHROPIC_API_KEY",
        display_name="Anthropic",
        backend_type="anthropic",
    ),
    ProviderSpec(
        name="openai",
        keywords=("openai", "gpt", "o1", "o3", "o4"),
        env_key="OPENAI_API_KEY",
        display_name="OpenAI",
        backend_type="openai_compat",
    ),
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        display_name="OpenRouter",
        backend_type="openai_compat",
        default_base_url="https://openrouter.ai/api/v1",
        detect_by_key_prefix="sk-or-",
        detect_by_base_keyword="openrouter",
        is_gateway=True,
    ),
    ProviderSpec(
        name="deepseek",
        keywords=("deepseek",),
        env_key="DEEPSEEK_API_KEY",
        display_name="DeepSeek",
        backend_type="openai_compat",
        default_base_url="https://api.deepseek.com/v1",
        detect_by_base_keyword="deepseek",
    ),
    ProviderSpec(
        name="groq",
        keywords=("groq",),
        env_key="GROQ_API_KEY",
        display_name="Groq",
        backend_type="openai_compat",
        default_base_url="https://api.groq.com/openai/v1",
        detect_by_key_prefix="gsk_",
        detect_by_base_keyword="groq",
    ),
    ProviderSpec(
        name="ollama",
        keywords=("ollama",),
        env_key="",
        display_name="Ollama",
        backend_type="openai_compat",
        default_base_url="http://localhost:11434/v1",
        detect_by_base_keyword="localhost:11434",
        is_local=True,
    ),
)


def demo_provider_detection():
    """Demonstrate how provider detection works."""
    print("🔍 Provider Detection Demo")
    print("=" * 50)

    def detect_provider(model: str, api_key: str | None = None, base_url: str | None = None) -> ProviderSpec | None:
        """Simplified detection logic."""
        # 1. API key prefix
        if api_key:
            for spec in SAMPLE_PROVIDERS:
                if spec.detect_by_key_prefix and api_key.startswith(spec.detect_by_key_prefix):
                    return spec

        # 2. Base URL keyword
        if base_url:
            base_lower = base_url.lower()
            for spec in SAMPLE_PROVIDERS:
                if spec.detect_by_base_keyword and spec.detect_by_base_keyword in base_lower:
                    return spec

        # 3. Model keyword
        if model:
            model_lower = model.lower()
            for spec in SAMPLE_PROVIDERS:
                if any(kw in model_lower for kw in spec.keywords):
                    return spec
        return None

    test_cases = [
        # (model, api_key, base_url, expected_provider)
        ("claude-3-5-sonnet-20241022", None, None, "anthropic"),
        ("gpt-4o", None, None, "openai"),
        ("deepseek-chat", None, None, "deepseek"),
        ("openai/gpt-4o-mini", "sk-or-v1-123", None, "openrouter"),
        ("llama3-70b-8192", "gsk_123", None, "groq"),
        ("custom-model", None, "https://api.deepseek.com/v1", "deepseek"),
        ("ollama-model", None, "http://localhost:11434/v1", "ollama"),
    ]

    for model, api_key, base_url, expected in test_cases:
        detected = detect_provider(model, api_key, base_url)
        provider_name = detected.name if detected else "unknown"
        status = "✅" if provider_name == expected else "❌"
        print(f"{status} {model} → {provider_name} (expected: {expected})")


def demo_adding_provider():
    """Demonstrate adding a new provider."""
    print("\n🆕 Adding a New Provider Demo")
    print("=" * 50)

    # Example: Adding a fictional provider "ExampleAI"
    new_provider = ProviderSpec(
        name="exampleai",
        keywords=("example", "exampleai"),
        env_key="EXAMPLEAI_API_KEY",
        display_name="ExampleAI",
        backend_type="openai_compat",
        default_base_url="https://api.exampleai.com/v1",
        detect_by_key_prefix="exa_",
        detect_by_base_keyword="exampleai",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    )

    print("New provider spec:")
    print(f"  Name: {new_provider.name}")
    print(f"  Display: {new_provider.display_name}")
    print(f"  Backend: {new_provider.backend_type}")
    print(f"  Base URL: {new_provider.default_base_url}")
    print(f"  Keywords: {new_provider.keywords}")
    print(f"  Key Prefix: {new_provider.detect_by_key_prefix}")

    # Test detection with the new provider
    print("\nTesting detection with new provider:")

    def test_detection(model, api_key=None, base_url=None):
        """Test detection with the new provider included."""
        all_providers = list(SAMPLE_PROVIDERS) + [new_provider]

        # Check against all providers
        for spec in all_providers:
            if api_key and spec.detect_by_key_prefix and api_key.startswith(spec.detect_by_key_prefix):
                return spec
            if base_url and spec.detect_by_base_keyword and spec.detect_by_base_keyword in base_url.lower():
                return spec
            if model and any(kw in model.lower() for kw in spec.keywords):
                return spec
        return None

    test_cases = [
        ("example-gpt-4", None, None),
        ("custom-model", "exa_123", None),
        ("any-model", None, "https://api.exampleai.com/v1"),
    ]

    for model, api_key, base_url in test_cases:
        detected = test_detection(model, api_key, base_url)
        result = detected.name if detected else "not detected"
        print(f"  {model} → {result}")


def demo_provider_configuration():
    """Show different ways to configure providers."""
    print("\n⚙️ Provider Configuration Examples")
    print("=" * 50)

    providers = [
        ("Anthropic", "ANTHROPIC_API_KEY", "claude-3-5-sonnet-20241022", None),
        ("OpenAI", "OPENAI_API_KEY", "gpt-4o", "https://api.openai.com/v1"),
        ("OpenRouter", "OPENROUTER_API_KEY", "openai/gpt-4o-mini", "https://openrouter.ai/api/v1"),
        ("DeepSeek", "DEEPSEEK_API_KEY", "deepseek-chat", "https://api.deepseek.com/v1"),
        ("Groq", "GROQ_API_KEY", "llama3-70b-8192", "https://api.groq.com/openai/v1"),
        ("Ollama", None, "llama2", "http://localhost:11434/v1"),
    ]

    for name, env_var, model, base_url in providers:
        print(f"\n{name}:")
        if env_var:
            print(f"  export {env_var}='your-key-here'")
        print(f"  oh --model {model}")
        if base_url:
            print(f"  # Base URL: {base_url}")
        else:
            print("  # Uses default base URL from registry")


def demo_registry_inspection():
    """Show what's currently in the provider registry."""
    print("\n📋 Sample Provider Registry")
    print("=" * 50)

    print(f"Total providers: {len(SAMPLE_PROVIDERS)}")

    categories = {
        "Gateways": [p for p in SAMPLE_PROVIDERS if p.is_gateway],
        "Cloud Providers": [p for p in SAMPLE_PROVIDERS if not p.is_gateway and not p.is_local and not p.is_oauth],
        "Local Deployments": [p for p in SAMPLE_PROVIDERS if p.is_local],
        "OAuth Providers": [p for p in SAMPLE_PROVIDERS if p.is_oauth],
    }

    for category, providers in categories.items():
        if providers:
            print(f"\n{category} ({len(providers)}):")
            for provider in providers:
                keywords = ", ".join(provider.keywords)
                print(f"  - {provider.display_name} ({provider.name}): {keywords}")


def demo_cli_usage():
    """Show example CLI commands for different providers."""
    print("\n💻 CLI Usage Examples")
    print("=" * 50)

    examples = [
        ("Anthropic Claude", "oh --model claude-3-5-sonnet-20241022 'Hello world'"),
        ("OpenAI GPT-4", "oh --model gpt-4o 'Write a function'"),
        ("OpenRouter (any model)", "export OPENROUTER_API_KEY='sk-or-...'\noh --model anthropic/claude-3-haiku 'Quick task'"),
        ("DeepSeek", "export DEEPSEEK_API_KEY='...'\noh --model deepseek-chat 'Code review'"),
        ("Groq (fast inference)", "export GROQ_API_KEY='gsk_...'\noh --model llama3-70b-8192 'Analyze this'"),
        ("Ollama (local)", "oh --base-url http://localhost:11434/v1 --model llama2 'Local AI chat'"),
        ("Custom provider", "export CUSTOM_API_KEY='...'\noh --base-url https://api.custom.com/v1 --model gpt-4 'Use custom API'"),
    ]

    for description, command in examples:
        print(f"\n{description}:")
        print(f"  {command}")


def main():
    """Run all demos."""
    print("🚀 OpenHarness LLM Provider Demo")
    print("=" * 60)

    demo_registry_inspection()
    demo_provider_detection()
    demo_adding_provider()
    demo_provider_configuration()
    demo_cli_usage()

    print("\n" + "=" * 60)
    print("✨ Demo complete! Check docs/LLM_PROVIDERS.md for more details.")


if __name__ == "__main__":
    main()