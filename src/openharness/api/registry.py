"""
LLM Provider Registry — single source of truth for provider metadata.

Adding a new provider:
  1. Add a ProviderSpec to PROVIDERS below.
  Done. Detection, display, and config all derive from here.

Order matters — it controls match priority. Gateways and cloud providers first,
standard providers by keyword, local/special providers last.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    """One LLM provider's metadata.

    backend_type:
      "anthropic"    — Anthropic SDK (default for claude-* models)
      "openai_compat" — OpenAI-compatible REST API
      "copilot"      — GitHub Copilot OAuth flow
    """

    # Identity
    name: str  # canonical name, e.g. "dashscope"
    keywords: tuple[str, ...]  # model-name substrings for detection (lowercase)
    env_key: str  # primary API key environment variable
    display_name: str = ""  # shown in status / diagnostics

    # Routing
    backend_type: str = "openai_compat"  # "anthropic" | "openai_compat" | "copilot"
    default_base_url: str = ""  # fallback base URL for this provider

    # Auto-detection signals
    detect_by_key_prefix: str = ""  # match api_key prefix, e.g. "sk-or-"
    detect_by_base_keyword: str = ""  # match substring in base_url

    # Classification flags
    is_gateway: bool = False  # routes any model (OpenRouter, AiHubMix, …)
    is_local: bool = False  # local deployment (vLLM, Ollama)
    is_oauth: bool = False  # uses OAuth instead of API key

    @property
    def label(self) -> str:
        return self.display_name or self.name.title()


# ---------------------------------------------------------------------------
# PROVIDERS registry — order = detection priority.
# ---------------------------------------------------------------------------

PROVIDERS: tuple[ProviderSpec, ...] = (
    # === GitHub Copilot (OAuth, detected by api_format="copilot") ============
    ProviderSpec(
        name="github_copilot",
        keywords=("copilot",),
        env_key="",
        display_name="GitHub Copilot",
        backend_type="copilot",
        default_base_url="",
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        is_gateway=False,
        is_local=False,
        is_oauth=True,
    ),
    # === Gateways (detected by api_key prefix / base_url keyword) ============
    # OpenRouter: global gateway, keys start with "sk-or-"
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
    # AiHubMix: OpenAI-compatible gateway
    ProviderSpec(
        name="aihubmix",
        keywords=("aihubmix",),
        env_key="OPENAI_API_KEY",
        display_name="AiHubMix",
        backend_type="openai_compat",
        default_base_url="https://aihubmix.com/v1",
        detect_by_key_prefix="",
        detect_by_base_keyword="aihubmix",
        is_gateway=True,
        is_local=False,
        is_oauth=False,
    ),
    # SiliconFlow (硅基流动): OpenAI-compatible gateway
    ProviderSpec(
        name="siliconflow",
        keywords=("siliconflow",),
        env_key="OPENAI_API_KEY",
        display_name="SiliconFlow",
        backend_type="openai_compat",
        default_base_url="https://api.siliconflow.cn/v1",
        detect_by_key_prefix="",
        detect_by_base_keyword="siliconflow",
        is_gateway=True,
        is_local=False,
        is_oauth=False,
    ),
    # VolcEngine (火山引擎 / Ark): OpenAI-compatible gateway
    ProviderSpec(
        name="volcengine",
        keywords=("volcengine", "volces", "ark"),
        env_key="OPENAI_API_KEY",
        display_name="VolcEngine",
        backend_type="openai_compat",
        default_base_url="https://ark.cn-beijing.volces.com/api/v3",
        detect_by_key_prefix="",
        detect_by_base_keyword="volces",
        is_gateway=True,
        is_local=False,
        is_oauth=False,
    ),
    # === Standard cloud providers (matched by model-name keyword) ============
    # Anthropic: native SDK for claude-* models
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),
        env_key="ANTHROPIC_API_KEY",
        display_name="Anthropic",
        backend_type="anthropic",
        default_base_url="",
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # OpenAI: gpt-* models
    ProviderSpec(
        name="openai",
        keywords=("openai", "gpt", "o1", "o3", "o4"),
        env_key="OPENAI_API_KEY",
        display_name="OpenAI",
        backend_type="openai_compat",
        default_base_url="",
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # DeepSeek
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
    # Google Gemini
    ProviderSpec(
        name="gemini",
        keywords=("gemini",),
        env_key="GEMINI_API_KEY",
        display_name="Gemini",
        backend_type="openai_compat",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        detect_by_key_prefix="",
        detect_by_base_keyword="googleapis",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # DashScope (Qwen / 阿里云)
    ProviderSpec(
        name="dashscope",
        keywords=("qwen", "dashscope"),
        env_key="DASHSCOPE_API_KEY",
        display_name="DashScope",
        backend_type="openai_compat",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        detect_by_key_prefix="",
        detect_by_base_keyword="dashscope",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # Moonshot / Kimi
    ProviderSpec(
        name="moonshot",
        keywords=("moonshot", "kimi"),
        env_key="MOONSHOT_API_KEY",
        display_name="Moonshot",
        backend_type="openai_compat",
        default_base_url="https://api.moonshot.ai/v1",
        detect_by_key_prefix="",
        detect_by_base_keyword="moonshot",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # MiniMax
    ProviderSpec(
        name="minimax",
        keywords=("minimax",),
        env_key="MINIMAX_API_KEY",
        display_name="MiniMax",
        backend_type="openai_compat",
        default_base_url="https://api.minimax.io/v1",
        detect_by_key_prefix="",
        detect_by_base_keyword="minimax",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # Zhipu AI / GLM
    ProviderSpec(
        name="zhipu",
        keywords=("zhipu", "glm", "chatglm"),
        env_key="ZHIPUAI_API_KEY",
        display_name="Zhipu AI",
        backend_type="openai_compat",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        detect_by_key_prefix="",
        detect_by_base_keyword="bigmodel",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # Groq
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
    # Mistral
    ProviderSpec(
        name="mistral",
        keywords=("mistral", "mixtral", "codestral"),
        env_key="MISTRAL_API_KEY",
        display_name="Mistral",
        backend_type="openai_compat",
        default_base_url="https://api.mistral.ai/v1",
        detect_by_key_prefix="",
        detect_by_base_keyword="mistral",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # StepFun (阶跃星辰)
    ProviderSpec(
        name="stepfun",
        keywords=("step-", "stepfun"),
        env_key="STEPFUN_API_KEY",
        display_name="StepFun",
        backend_type="openai_compat",
        default_base_url="https://api.stepfun.com/v1",
        detect_by_key_prefix="",
        detect_by_base_keyword="stepfun",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # Baidu / ERNIE
    ProviderSpec(
        name="baidu",
        keywords=("ernie", "baidu"),
        env_key="QIANFAN_ACCESS_KEY",
        display_name="Baidu",
        backend_type="openai_compat",
        default_base_url="https://qianfan.baidubce.com/v2",
        detect_by_key_prefix="",
        detect_by_base_keyword="baidubce",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # === Cloud platform providers (detected by base_url) ====================
    # AWS Bedrock
    ProviderSpec(
        name="bedrock",
        keywords=("bedrock",),
        env_key="AWS_ACCESS_KEY_ID",
        display_name="AWS Bedrock",
        backend_type="openai_compat",
        default_base_url="",
        detect_by_key_prefix="",
        detect_by_base_keyword="bedrock",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # Google Vertex AI
    ProviderSpec(
        name="vertex",
        keywords=("vertex",),
        env_key="GOOGLE_APPLICATION_CREDENTIALS",
        display_name="Vertex AI",
        backend_type="openai_compat",
        default_base_url="",
        detect_by_key_prefix="",
        detect_by_base_keyword="aiplatform",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
    # === Local deployments (matched by keyword or base_url) =================
    # Ollama
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
    # vLLM / any OpenAI-compatible local server
    ProviderSpec(
        name="vllm",
        keywords=("vllm",),
        env_key="",
        display_name="vLLM/Local",
        backend_type="openai_compat",
        default_base_url="",
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        is_gateway=False,
        is_local=True,
        is_oauth=False,
    ),
)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def find_by_name(name: str) -> ProviderSpec | None:
    """Find a provider spec by canonical name, e.g. "dashscope"."""
    for spec in PROVIDERS:
        if spec.name == name:
            return spec
    return None


def _match_by_model(model: str) -> ProviderSpec | None:
    """Match a standard/gateway provider by model-name keyword (case-insensitive)."""
    model_lower = model.lower()
    model_normalized = model_lower.replace("-", "_")
    model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
    normalized_prefix = model_prefix.replace("-", "_")

    std_specs = [s for s in PROVIDERS if not s.is_local and not s.is_oauth]

    # Prefer an explicit provider-prefix match (e.g. "deepseek/..." → deepseek spec)
    for spec in std_specs:
        if model_prefix and normalized_prefix == spec.name:
            return spec

    # Fall back to keyword scan
    for spec in std_specs:
        if any(
            kw in model_lower or kw.replace("-", "_") in model_normalized
            for kw in spec.keywords
        ):
            return spec
    return None


def detect_provider_from_registry(
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ProviderSpec | None:
    """Detect the best-matching ProviderSpec for the given inputs.

    Detection priority:
      1. api_key prefix  (e.g. "sk-or-" → OpenRouter)
      2. base_url keyword (e.g. "aihubmix" in URL → AiHubMix)
      3. model name keyword (e.g. "qwen" → DashScope)
    """
    # 1. api_key prefix
    if api_key:
        for spec in PROVIDERS:
            if spec.detect_by_key_prefix and api_key.startswith(spec.detect_by_key_prefix):
                return spec

    # 2. base_url keyword
    if base_url:
        base_lower = base_url.lower()
        for spec in PROVIDERS:
            if spec.detect_by_base_keyword and spec.detect_by_base_keyword in base_lower:
                return spec

    # 3. model keyword
    if model:
        return _match_by_model(model)

    return None
