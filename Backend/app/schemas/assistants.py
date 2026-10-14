"""Local administrator configuration. Credentials only appear in write schemas."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, field_validator, model_validator

from app.providers.registry import ProviderName

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ModelId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200,
                                         pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")]


class ConfigurationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


def validate_key(value: SecretStr) -> SecretStr:
    key = value.get_secret_value()
    if not 1 <= len(key) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ValueError("Enter a valid provider API key without whitespace.")
    return value


class ConnectionCreate(ConfigurationSchema):
    name: Name
    provider: ProviderName
    api_key: SecretStr = Field(repr=False)

    _key = field_validator("api_key")(validate_key)


class ConnectionUpdate(ConfigurationSchema):
    name: Name
    active: bool = True
    api_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("api_key")
    @classmethod
    def check_optional_key(cls, value: SecretStr | None) -> SecretStr | None:
        return validate_key(value) if value is not None else None


class ConnectionResponse(ConfigurationSchema):
    id: UUID
    name: str
    provider: ProviderName
    active: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class ModelDiscovery(ConfigurationSchema):
    provider: ProviderName
    api_key: SecretStr = Field(repr=False)

    _key = field_validator("api_key")(validate_key)


class GenerationSettings(ConfigurationSchema):
    model: ModelId
    max_output_tokens: int = Field(default=2048, ge=64, le=8192, strict=True)
    context_window_tokens: int = Field(default=32768, ge=4096, le=1048576, strict=True)
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    timeout_seconds: float = Field(default=120, gt=0, le=600, allow_inf_nan=False)

    @model_validator(mode="after")
    def usable_context(self):
        if self.context_window_tokens <= self.max_output_tokens * 5 + 4560:
            raise ValueError("The context window must leave room for the answer, review draft, framing and at least 2000 input tokens. Increase the context window or reduce the output limit.")
        return self


class ConnectionTest(GenerationSettings):
    connection_id: UUID | None = None
    provider: ProviderName | None = None
    api_key: SecretStr | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def credentials(self):
        if self.connection_id is not None:
            if self.provider is not None or self.api_key is not None:
                raise ValueError("Choose a saved connection or supply provider credentials, not both.")
        elif self.provider is None or self.api_key is None:
            raise ValueError("Choose a saved connection or supply provider credentials.")
        if self.api_key is not None:
            validate_key(self.api_key)
        return self


class AssistantWrite(GenerationSettings):
    name: Name
    description: str = Field(default="", max_length=500)
    connection_id: UUID
    document_ids: list[UUID] = Field(default_factory=list, max_length=500)
    active: bool = True

    @field_validator("document_ids")
    @classmethod
    def unique_documents(cls, value: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(value))


class AssistantResponse(GenerationSettings):
    id: UUID
    name: str
    description: str
    connection_id: UUID
    provider: ProviderName
    document_ids: list[UUID]
    active: bool
    revision: int
    created_at: datetime
    updated_at: datetime
