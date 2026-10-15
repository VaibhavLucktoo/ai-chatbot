"""Typed provider listing, discovery and connection-test responses."""

from typing import Literal

from pydantic import BaseModel


class ProviderDescriptor(BaseModel):
    id: str
    name: str


class ProviderListResponse(BaseModel):
    items: list[ProviderDescriptor]


class ProviderModelListResponse(BaseModel):
    items: list[str]


class ProviderTestResponse(BaseModel):
    status: Literal["ok"]
    provider: str
    model: str
