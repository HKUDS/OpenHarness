# Adding LLM Providers to OpenHarness

OpenHarness supports a wide variety of LLM providers through its extensible provider registry system. This guide shows you how to add new providers and configure them.

## Quick Start

### For Users: Using Existing Providers

OpenHarness already supports many popular providers. Here's how to use them:

```bash
# OpenRouter (access to 100+ models)
export OPENROUTER_API_KEY="sk-or-v1-..."
oh --model anthropic/claude-3-haiku "Hello world"

# DeepSeek
export DEEPSEEK_API_KEY="your-key"
oh --model deepseek-chat "Code review this function"

# Groq (fast inference)
export GROQ_API_KEY="gsk_..."
oh --model llama3-70b-8192 "Analyze this code"

# Ollama (local models)
oh --base-url http://localhost:11434/v1 --model llama2 "Local AI chat"
```

### For Developers: Adding New Providers

To add a new LLM provider:

1. **Edit the registry** (`src/openharness/api/registry.py`)
2. **Add your provider spec** to the `PROVIDERS` tuple
3. **Test the configuration**

Example provider spec:
```python
ProviderSpec(
    name="myprovider",
    keywords=("myprovider", "myai"),
    env_key="MYPROVIDER_API_KEY",
    display_name="MyProvider",
    backend_type="openai_compat",  # or "anthropic"
    default_base_url="https://api.myprovider.com/v1",
    detect_by_key_prefix="mp_",    # optional
    detect_by_base_keyword="myprovider",  # optional
    is_gateway=False,
    is_local=False,
    is_oauth=False,
),
```

## Demo

Run the interactive demo to see how providers work:

```bash
python scripts/demo_providers.py
```

This shows:
- How provider detection works
- How to add new providers
- Configuration examples
- CLI usage patterns

## Supported Providers

OpenHarness currently supports:

- **Anthropic** (Claude models)
- **OpenAI** (GPT models)
- **OpenRouter** (100+ models via gateway)
- **DeepSeek**
- **Groq** (fast inference)
- **GitHub Copilot** (OAuth)
- **Ollama** (local models)
- And many more...

See `docs/LLM_PROVIDERS.md` for the complete list and detailed configuration instructions.

## Key Concepts

### Provider Detection Priority
1. API key prefix (e.g., `sk-or-` → OpenRouter)
2. Base URL keywords (e.g., `deepseek.com` → DeepSeek)
3. Model name keywords (e.g., `claude` → Anthropic)

### Backend Types
- `anthropic`: Native Anthropic SDK (best for Claude)
- `openai_compat`: OpenAI SDK (works with most providers)
- `copilot`: GitHub Copilot OAuth

### Configuration Methods
- Environment variables: `export PROVIDER_API_KEY="..."`
- Command line: `oh --model model-name --base-url https://...`
- Settings file: `~/.openharness/settings.json`

## Need Help?

- Check the [full documentation](docs/LLM_PROVIDERS.md)
- Run the demo: `python scripts/demo_providers.py`
- Test detection: `oh --model your-model-name --dry-run`