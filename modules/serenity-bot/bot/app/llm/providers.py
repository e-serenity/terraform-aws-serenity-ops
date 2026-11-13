"""Multi-Provider LLM Factory & Resilient Hybrid Routing for Serenity-Ops.

Supports:
- AWS Bedrock (`bedrock`): Anthropic Claude 3.5/3.7/4.x Sonnet, Haiku, Amazon Nova.
- Google Gemini API (`gemini`): Gemini 2.5 / 3.x Flash & Pro via `ChatGoogleGenerativeAI`.
- Anthropic Direct API (`anthropic`) & OpenAI API (`openai`) via `init_chat_model`.
"""

from typing import Any
from langchain.chat_models import init_chat_model
from langchain_aws import ChatBedrock
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.core.utils.logging import get_logger
from app.core.utils.redaction import is_configured_secret

logger = get_logger("llm.providers")

SUPPORTED_PROVIDERS = ("bedrock", "gemini", "anthropic", "openai")


def normalize_provider(provider: str | None) -> str:
    """Normalizes a provider string to one of SUPPORTED_PROVIDERS."""
    cleaned = (provider or "bedrock").strip().lower()
    if cleaned in ("aws", "aws_bedrock", "bedrock"):
        return "bedrock"
    if cleaned in ("google", "google_genai", "gemini"):
        return "gemini"
    if cleaned in ("anthropic", "claude"):
        return "anthropic"
    if cleaned in ("openai", "gpt"):
        return "openai"
    return cleaned


def is_provider_available(provider: str) -> bool:
    """Checks whether the required credentials exist (and are not placeholders) for a provider."""
    norm = normalize_provider(provider)
    if norm == "bedrock":
        # AWS Bedrock uses the ECS Task IAM role (or local AWS profile)
        return True
    if norm == "gemini":
        return is_configured_secret(settings.gemini_api_key)
    if norm == "anthropic":
        return is_configured_secret(settings.anthropic_api_key)
    if norm == "openai":
        return is_configured_secret(settings.openai_api_key)
    return False


def build_chat_model(
    provider: str,
    model_id: str,
    rate_limiter: InMemoryRateLimiter | None = None,
) -> BaseChatModel:
    """Instantiates a LangChain BaseChatModel for the requested provider and model_id."""
    norm = normalize_provider(provider)
    if not is_provider_available(norm):
        raise RuntimeError(f"Credentials for LLM provider '{norm}' are not configured.")

    if norm == "bedrock":
        return ChatBedrock(
            model_id=model_id,
            region_name=settings.aws_region,
            model_kwargs={"max_tokens": 4096},
        )

    if norm == "gemini":
        kwargs: dict[str, Any] = {
            "model": model_id,
            "google_api_key": settings.gemini_api_key,
            "include_thoughts": False,
            "max_retries": 1,
        }
        if rate_limiter is not None:
            kwargs["rate_limiter"] = rate_limiter
        return ChatGoogleGenerativeAI(**kwargs)

    if norm == "anthropic":
        return init_chat_model(
            model=model_id,
            model_provider="anthropic",
            api_key=settings.anthropic_api_key,
            max_tokens=4096,
        )

    if norm == "openai":
        return init_chat_model(
            model=model_id,
            model_provider="openai",
            api_key=settings.openai_api_key,
        )

    raise ValueError(f"Unsupported LLM provider '{provider}'. Supported: {SUPPORTED_PROVIDERS}")


def get_model_routing_chain() -> list[tuple[str, str, bool]]:
    """Builds the ordered list of `(provider, model_id, is_fallback)` candidates.

    Starts with the configured primary provider/model, then appends configured fallback
    models whose credentials are available.
    """
    chain: list[tuple[str, str, bool]] = []
    seen: set[tuple[str, str]] = set()

    def _add(prov: str, mod: str, is_fb: bool) -> None:
        norm_p = normalize_provider(prov)
        clean_m = (mod or "").strip()
        if not clean_m or not is_provider_available(norm_p):
            return
        key = (norm_p, clean_m)
        if key not in seen:
            seen.add(key)
            chain.append((norm_p, clean_m, is_fb))

    # 1. Primary model
    primary_prov = normalize_provider(settings.llm_primary_provider)
    primary_mod = settings.effective_primary_model
    _add(primary_prov, primary_mod, False)

    # 2. Configured Fallback model
    fallback_prov = normalize_provider(settings.llm_fallback_provider)
    fallback_mod = settings.effective_fallback_model
    if fallback_prov and fallback_mod:
        _add(fallback_prov, fallback_mod, True)

    # 3. Additional Gemini resilience tier if Gemini is the fallback provider
    if fallback_prov == "gemini" and is_provider_available("gemini"):
        for extra_gemini in (settings.gemini_fallback_model, "gemini-3.5-flash", "gemini-3.1-flash-lite"):
            _add("gemini", extra_gemini, True)

    return chain
