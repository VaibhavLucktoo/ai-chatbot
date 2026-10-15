"""Internal, evidence-backed document metadata; no public response changes."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

METADATA_VERSION = 1

MetadataField = Literal[
    "title", "section_title", "organization", "document_owner", "author",
    "publisher", "website", "email", "effective_date", "version",
    "disclosing_party", "receiving_party",
]


class DocumentFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: MetadataField
    value: str | None = Field(max_length=240)
    status: Literal["explicit", "inferred", "unspecified"]
    chunk_id: UUID
    page_number: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=1000)
    # Page/section scope is retained instead of assuming one owner per merged PDF.
    section: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def value_matches_status(self):
        if (self.value is None) != (self.status == "unspecified"):
            raise ValueError("Only an unspecified fact may have a null value.")
        return self


class DocumentMetadataPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = METADATA_VERSION
    facts: tuple[DocumentFact, ...] = Field(max_length=128)
    summary: str = Field(min_length=1, max_length=6000)


def verified_chunk_facts(chunk) -> tuple[DocumentFact, ...]:
    """Reject metadata that cannot be checked against this exact source passage."""
    valid = []
    for item in chunk.get("metadata_evidence", ())[:128]:
        try:
            fact = DocumentFact.model_validate(item)
            if (str(fact.chunk_id) != str(chunk.get("chunk_id"))
                    or fact.page_number != chunk.get("page_number")
                    or fact.quote not in chunk.get("content", "")):
                continue
            if fact.status == "explicit" and " ".join(fact.value.split()) not in " ".join(fact.quote.split()):
                continue
            valid.append(fact)
        except (ValidationError, TypeError, ValueError):
            continue
    return tuple(valid)
