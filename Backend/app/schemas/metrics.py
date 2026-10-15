"""Persisted analytics response contract."""

from pydantic import BaseModel, Field


class AnalyticsResponse(BaseModel):
    window: dict
    requests: dict
    outcomes: dict[str, int]
    intents: dict[str, int]
    calls: dict
    models: list[dict]
    call_stages: list[dict]
    workflow_stages_ms: dict[str, float]
    timeline: list[dict]
    requests_last_minute: int
    available_models: list[str]
    recent: dict
    runtime: dict | None
    pricing: dict
    quality: dict
    assistants: list[dict] = Field(default_factory=list)
    available_assistants: list[dict] = Field(default_factory=list)
    available_providers: list[str] = Field(default_factory=list)
    configuration_cache: dict | None = None
