import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    """Provider capabilities shared by Harbor agent adapters."""

    name: str
    api_key_env: str
    base_url_env: str
    model_env: str
    default_mini_model_class: str = "litellm"
    litellm_custom_provider: str = "openai"
    mini_model_kwargs: dict[str, Any] = field(default_factory=dict)
    pi_openai_compat: dict[str, Any] = field(default_factory=dict)

    @property
    def model_name(self) -> str:
        return f"{self.name}/{self.model}"

    @property
    def model(self) -> str:
        return os.environ[self.model_env]

    @property
    def base_url(self) -> str:
        return os.environ[self.base_url_env]

    def required_env(self) -> list[str]:
        return [self.api_key_env, self.base_url_env, self.model_env]

    def env_mapping(self) -> dict[str, str]:
        return {
            self.api_key_env: f"${{{self.api_key_env}}}",
            self.base_url_env: f"${{{self.base_url_env}}}",
            self.model_env: f"${{{self.model_env}}}",
        }

    def mini_kwargs(self, *, temperature: float, request_timeout_sec: float | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "drop_params": True,
            "custom_llm_provider": self.litellm_custom_provider,
            "api_base": self.base_url,
            **self.mini_model_kwargs,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if request_timeout_sec is not None and request_timeout_sec > 0:
            kwargs["timeout"] = request_timeout_sec
        return kwargs


def _env_name(provider: str, suffix: str) -> str:
    return f"{provider.upper()}_{suffix}"


def _base_openai_compat() -> dict[str, Any]:
    return {
        "supportsStore": False,
        "supportsDeveloperRole": False,
        "supportsReasoningEffort": False,
        "supportsUsageInStreaming": False,
        "maxTokensField": "max_tokens",
        "requiresToolResultName": False,
        "requiresAssistantAfterToolResult": False,
        "requiresThinkingAsText": False,
        "requiresReasoningContentOnAssistantMessages": False,
        "supportsStrictMode": False,
        "supportsLongCacheRetention": False,
    }


def resolve_provider(name: str) -> ProviderSpec:
    provider = name.strip().lower()
    compat = _base_openai_compat()
    default_mini_model_class = "litellm"
    mini_model_kwargs: dict[str, Any] = {}

    if provider == "macaron":
        default_mini_model_class = "litellm_response"
        mini_model_kwargs["instructions"] = (
            "You are mini-SWE-agent. Use the bash tool to solve the user's "
            "software engineering task."
        )
    elif provider == "novita":
        default_mini_model_class = "litellm_textbased"
        compat.update(
            {
                "requiresThinkingAsText": True,
                "thinkingFormat": "zai",
            }
        )
    elif provider == "tinker":
        default_mini_model_class = "litellm_textbased"

    return ProviderSpec(
        name=provider,
        api_key_env=_env_name(provider, "API_KEY"),
        base_url_env=_env_name(provider, "BASE_URL"),
        model_env=_env_name(provider, "MODEL"),
        default_mini_model_class=default_mini_model_class,
        mini_model_kwargs=mini_model_kwargs,
        pi_openai_compat=compat,
    )
