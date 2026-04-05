# Adding LLM Providers to OpenHarness

OpenHarness supports a wide variety of LLM providers through its extensible provider registry system. This guide shows how to add new providers and configure them for use.

## How Provider Detection Works

OpenHarness automatically detects providers using a priority system:

1. **API Key Prefix**: Special key prefixes (e.g., `sk-or-` for OpenRouter)
2. **Base URL Keywords**: Substrings in the API base URL
3. **Model Name Keywords**: Keywords in model names

## Adding a New Provider

### Step 1: Add to the Provider Registry

Edit `src/openharness/api/registry.py` and add your provider to the `PROVIDERS` tuple:

```python
ProviderSpec(
    name="your_provider",
    keywords=("keyword1", "keyword2"),  # Model name keywords
    env_key="YOUR_PROVIDER_API_KEY",    # Environment variable name
    display_name="Your Provider",        # Human-readable name
    backend_type="openai_compat",       # "anthropic" | "openai_compat" | "copilot"
    default_base_url="https://api.yourprovider.com/v1",
    detect_by_key_prefix="",            # API key prefix (optional)
    detect_by_base_keyword="yourprovider",  # Base URL keyword (optional)
    is_gateway=False,                   # True if routes to multiple models
    is_local=False,                     # True for local deployments
    is_oauth=False,                     # True for OAuth providers
),
```

### Step 2: Configuration

Users can configure the provider in several ways:

#### Environment Variables
```bash
export YOUR_PROVIDER_API_KEY="your-api-key-here"
```

#### Command Line
```bash
# Auto-detection by model name
oh --model your-model-name

# Explicit base URL
oh --base-url https://api.yourprovider.com/v1

# Explicit API format (if needed)
oh --api-format openai
```

#### Settings File
```json
{
  "api_key": "your-api-key-here",
  "base_url": "https://api.yourprovider.com/v1",
  "model": "your-model-name"
}
```

## Examples

### OpenRouter

OpenRouter is already configured in the registry:

```python
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
    is_local=False,
    is_oauth=False,
),
```

Usage:
```bash
export OPENROUTER_API_KEY="sk-or-..."
oh --model openai/gpt-4o-mini
```

### Adding a Custom Provider

Let's add support for a hypothetical provider called "ExampleAI":

1. **Add to registry**:
```python
ProviderSpec(
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
),
```

2. **Usage**:
```bash
export EXAMPLEAI_API_KEY="exa_your_key_here"
oh --model example/gpt-4

# Or with explicit base URL
oh --base-url https://api.exampleai.com/v1 --model gpt-4
```

### Popular Providers

Here are some popular providers and their configurations:

#### Anthropic (Native)
- **Backend**: `anthropic`
- **Models**: `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307`
- **Key**: `ANTHROPIC_API_KEY`

#### OpenAI
- **Backend**: `openai_compat`
- **Models**: `gpt-4o`, `gpt-4-turbo`
- **Key**: `OPENAI_API_KEY`
- **Base URL**: `https://api.openai.com/v1`

#### DeepSeek
```python
ProviderSpec(
    name="deepseek",
    keywords=("deepseek",),
    env_key="DEEPSEEK_API_KEY",
    display_name="DeepSeek",
    backend_type="openai_compat",
    default_base_url="https://api.deepseek.com/v1",
    detect_by_key_prefix="",
    detect_by_base_keyword="deepseek",
    is_gateway=False,
    is_local=False,
    is_oauth=False,
),
```

Usage:
```bash
export DEEPSEEK_API_KEY="your-key"
oh --model deepseek-chat
```

#### Groq
```python
ProviderSpec(
    name="groq",
    keywords=("groq",),
    env_key="GROQ_API_KEY",
    display_name="Groq",
    backend_type="openai_compat",
    default_base_url="https://api.groq.com/openai/v1",
    detect_by_key_prefix="gsk_",
    detect_by_base_keyword="groq",
    is_gateway=False,
    is_local=False,
    is_oauth=False,
),
```

Usage:
```bash
export GROQ_API_KEY="gsk_..."
oh --model llama3-70b-8192
```

#### Ollama (Local)
```python
ProviderSpec(
    name="ollama",
    keywords=("ollama",),
    env_key="",
    display_name="Ollama",
    backend_type="openai_compat",
    default_base_url="http://localhost:11434/v1",
    detect_by_key_prefix="",
    detect_by_base_keyword="localhost:11434",
    is_gateway=False,
    is_local=True,
    is_oauth=False,
),
```

Usage:
```bash
# Start Ollama server locally
ollama serve

# Use with OpenHarness
oh --base-url http://localhost:11434/v1 --model llama2
```

## Backend Types

### Anthropic Backend
- Uses the official Anthropic Python SDK
- Best for Claude models
- Supports advanced features like tool calling

### OpenAI Compatible Backend
- Uses the OpenAI Python SDK
- Works with any OpenAI-compatible API
- Most providers use this backend

### Copilot Backend
- Special OAuth flow for GitHub Copilot
- Requires `api_format=copilot`

## Detection Priority

The system checks for providers in this order:

1. **API Key Prefix**: `sk-or-` → OpenRouter, `gsk_` → Groq
2. **Base URL**: `openrouter.ai` → OpenRouter, `deepseek.com` → DeepSeek
3. **Model Keywords**: `claude` → Anthropic, `gpt` → OpenAI

## Testing Your Provider

1. **Add to registry**
2. **Set environment variable**
3. **Test detection**:
   ```bash
   oh --model your-model-name --dry-run
   ```
4. **Test actual usage**:
   ```bash
   oh --model your-model-name "Hello world"
   ```

## Troubleshooting

### Provider Not Detected
- Check that keywords match your model names
- Verify API key prefix or base URL keywords
- Use explicit `--base-url` and `--api-format openai`

### Authentication Errors
- Verify API key is set correctly
- Check API key format (some providers have specific prefixes)
- Ensure the API key has necessary permissions

### Connection Issues
- Verify base URL is correct
- Check network connectivity
- Some providers require specific regions or endpoints

## Contributing

When adding a new provider:

1. Test with multiple models
2. Verify API compatibility
3. Add appropriate keywords for detection
4. Update this documentation
5. Consider adding tests

The provider registry in `src/openharness/api/registry.py` is the single source of truth for all provider configurations.