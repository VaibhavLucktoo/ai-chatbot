"""Bounded metadata extraction from original passages, independent of any LLM.

All uploads use this extractor. Labels and literal contact details are evidence;
unlabelled entities and missing values are never promoted to legal ownership.
"""

import re
import asyncio
import math
from collections.abc import Mapping, Sequence

from app.schemas.document_metadata import DocumentFact, DocumentMetadataPayload
from app.services import chunking
from app.storage.models import EMBEDDING_DIMENSIONS, EMBEDDING_SPACE

LABELS = {
    "title": "title", "document title": "title", "policy name": "title",
    "company": "organization", "organization": "organization", "organisation": "organization",
    "employer": "organization", "policy owner": "document_owner", "document owner": "document_owner",
    "author": "author", "written by": "author", "prepared by": "author",
    "publisher": "publisher", "published by": "publisher", "issued by": "publisher",
    "effective date": "effective_date", "version": "version", "revision": "version",
    "disclosing party": "disclosing_party", "receiving party": "receiving_party",
}
_LABEL = re.compile(
    r"(?:^|[\n;])\s*(?P<label>" + "|".join(re.escape(key) for key in sorted(LABELS, key=len, reverse=True))
    + r")[ \t]*[:=][ \t]*(?P<value>[^\n;]{1,240})", re.IGNORECASE,
)
_CONTACTS = (
    ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")),
    ("website", re.compile(r"\b(?:https?://|www\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:/[^\s<>\"']*)?", re.IGNORECASE)),
)
_COMPANY = re.compile(
    r"\bworking\s+for\s+(?P<value>[^,\n]{2,120})\s*,\s*"
    r"\(hereinafter\s+referred\s+to\s+as\s+the\s+[\"\u201c]Company[\"\u201d]\)", re.IGNORECASE,
)
_BLANK_DISCLOSER = re.compile(
    r"_{3,}\s*,\s*a\s+(?:private|public)\s+limited\s+company[\s\S]{0,600}?"
    r"[\"\u201c]Disclosing\s+Party[\"\u201d]", re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"(?:[_\s.\-]+|\[\s*(?:insert|enter|name|company)[^\]]*\]|\{[^}]*\})\Z", re.IGNORECASE)


def extract_document_metadata(filename: str, chunks: Sequence[Mapping]) -> DocumentMetadataPayload:
    """Keep original quotes and conflicting values; limit storage and embedding work."""
    facts = []
    seen = set()

    def add(field, value, quote, chunk, section=None):
        value = re.sub(r"\s+", " ", value).strip() if value is not None else None
        if value is not None and len(value) > 240:
            return
        if value is not None and _PLACEHOLDER.fullmatch(value):
            value = None
        key = (field, value)
        if key in seen or len(facts) >= 128:
            return
        seen.add(key)
        facts.append(DocumentFact(
            field=field, value=value, status="explicit" if value is not None else "unspecified",
            chunk_id=chunk["id"], page_number=chunk["page_number"], quote=quote,
            section=section,
        ))

    # Each fact points to an existing chunk; source pages are never invented.
    for chunk in chunks:
        content = chunk["content"]
        section = next((line.strip() for line in content.splitlines()[:12]
                        if 4 <= len(line.strip()) <= 100 and line.strip().isupper()
                        and sum(char.isalpha() for char in line) >= 4), None)
        for match in _LABEL.finditer(content):
            add(LABELS[match["label"].lower()], match["value"], match[0].strip(), chunk, section)
        for match in _COMPANY.finditer(content):
            add("organization", match["value"], match[0], chunk, section)
        for match in _BLANK_DISCLOSER.finditer(content):
            add("disclosing_party", None, match[0], chunk, section)
        for field, pattern in _CONTACTS:
            for match in pattern.finditer(content):
                value = match[0].rstrip(".,;:)")
                add(field, value, value, chunk, section)
        if section:
            add("section_title", section, section, chunk, section)

    # Titles and contact information need no model inference. Facts absent from
    # the source remain absent; a template blank is an explicit unspecified fact.
    lines = [f"Document: {filename}"]
    lines.extend(f"{fact.field}: {fact.value if fact.value is not None else '(unspecified)'} "
                 f"[page {fact.page_number}]" for fact in facts)
    if not facts and chunks:
        lines.append("Opening passage: " + chunks[0]["content"][:1600])
    summary = "\n".join(lines)
    tokens = chunking._get_tokenizer().encode(summary, add_special_tokens=False)
    if len(tokens.offsets) > chunking.CHUNK_TOKENS:
        summary = summary[:tokens.offsets[chunking.CHUNK_TOKENS - 1][1]]
    return DocumentMetadataPayload(facts=tuple(facts), summary=summary[:6000])


def metadata_record(payload, vector):
    """Validate an index vector before either upload or backfill publication."""
    vector = [float(value) for value in vector]
    if (len(vector) != EMBEDDING_DIMENSIONS or not all(math.isfinite(value) for value in vector)
            or not math.isclose(math.hypot(*vector), 1.0, rel_tol=1e-5)):
        raise ValueError("Metadata requires finite normalized vectors in the document embedding space.")
    return {**payload.model_dump(mode="json"), "embedding": vector, "embedding_space": EMBEDDING_SPACE}


async def ensure_document_metadata(database, embeddings, document_id):
    """Idempotently backfill one existing document without reparsing or reindexing it."""
    from app.storage.document_metadata import metadata_snapshot, publish_metadata_backfill
    from app.core.config import get_settings

    snapshot = await metadata_snapshot(database, document_id)
    if snapshot is None:
        return False
    if embeddings.space_id != EMBEDDING_SPACE or embeddings.dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError("Metadata embedding provider does not match the document space.")
    filename, digest, chunks = snapshot
    if not chunks:
        return False
    payload = await asyncio.to_thread(extract_document_metadata, filename, chunks)
    async with asyncio.timeout(get_settings().embedding_timeout_seconds):
        vectors = await embeddings.embed_documents([payload.summary])
    if len(vectors) != 1:
        raise ValueError("Metadata embedding count mismatch.")
    return await publish_metadata_backfill(database, document_id, digest, chunks,
                                           metadata_record(payload, vectors[0]))
