"""Backend-owned provider endpoints and validated per-request model settings."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

ProviderName = Literal["groq", "gemini"]


@dataclass(frozen=True)
class ProviderPreset:
    id: ProviderName
    name: str
    base_url: str


PROVIDERS: dict[str, ProviderPreset] = {
    "groq": ProviderPreset("groq", "Groq", "https://api.groq.com/openai/v1"),
    "gemini": ProviderPreset("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
}


class ProviderModelSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    base_url: str
    model: str
    api_key: SecretStr = Field(repr=False)
    timeout_seconds: float = Field(default=120, gt=0, le=600, allow_inf_nan=False)
    max_output_tokens: int = Field(default=2048, ge=64, le=8192)
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    max_input_bytes: int = Field(default=64000, ge=2000, le=256000)
    context_window_tokens: int = Field(default=32768, ge=4096, le=1048576)


def provider_settings(provider: ProviderName, model: str, api_key: SecretStr, **options) -> ProviderModelSettings:
    return ProviderModelSettings(base_url=PROVIDERS[provider].base_url, model=model, api_key=api_key, **options)
