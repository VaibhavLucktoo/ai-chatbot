"""Build grounded prompts and answer questions using retrieved PDF passages.

The search wrapper preserves caller transactions. Chat owns a short read
transaction on a fresh session and releases it before language generation.
"""

import json
import re
from dataclasses import asdict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.embeddings import get_embedding_provider
from app.prompts.rag import INSUFFICIENT_CONTEXT_ANSWER, RAG_SYSTEM_PROMPT
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.services.llm import LLMResponseError, generate_llm_response
from app.services.retrieval import RetrievalProviderError, retrieve_chunks


CITATION_PATTERN = re.compile(r"\[\s*([0-9]+(?:\s*,\s*[0-9]+)*)\s*\]")


class _PromptChunk(BaseModel):
    """Validate the passage fields included in the LLM prompt."""

    model_config = ConfigDict(extra="ignore")

    filename: str = Field(strict=True, min_length=1, max_length=255)
    page_number: int = Field(strict=True, ge=1)
    chunk_id: UUID
    content: str = Field(strict=True, min_length=1)

    @field_validator("filename", "content")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Passage filenames and content must not be blank.")
        return value


def build_rag_prompt(question: str, retrieved_chunks: list[dict]) -> str:
    """Build the user message; trusted rules live in RAG_SYSTEM_PROMPT.

    JSON encoding keeps metadata and passage boundaries explicit, including
    when source text contains newlines, quotes, or instruction-like text.
    These are prompt instructions; they do not guarantee model compliance.
    """
    question = ChatRequest(question=question).question

    if not isinstance(retrieved_chunks, list):
        raise TypeError("retrieved_chunks must be a list of dictionaries.")

    context = []
    for source_number, chunk in enumerate(retrieved_chunks, start=1):
        if not isinstance(chunk, dict):
            raise TypeError("Each retrieved chunk must be a dictionary.")

        passage = _PromptChunk.model_validate(chunk)
        context.append({
            "source_number": source_number,
            **passage.model_dump(mode="json"),
        })

    return (
        "CONTEXT (JSON array of document passages):\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
        + "\n\nQUESTION (JSON string):\n"
        + json.dumps(question, ensure_ascii=False)
        + "\n\nANSWER:\n"
    )


async def search_similar_chunks(
    db: AsyncSession,
    question: str,
    top_k: int = 5,
    *,
    document_ids: list[UUID] | None = None,
) -> list[dict]:
    """Embed a question and return ranked passages as dictionaries.

    The existing retrieval service validates the embedding space and vector,
    then searches compatible chunks belonging to ready documents.
    """
    validated_request = ChatRequest(
        question=question, top_k=top_k, document_ids=document_ids,
    )

    try:
        embeddings = get_embedding_provider()
    except (ValueError, RuntimeError) as exc:
        raise RetrievalProviderError("Embedding provider unavailable.") from exc

    result = await retrieve_chunks(
        database=db,
        embeddings=embeddings,
        query=validated_request.question,
        top_k=validated_request.top_k,
        document_ids=validated_request.document_ids,
    )
    return [asdict(chunk) for chunk in result.chunks]


def validate_answer(answer: str, sources: list[ChatSource]) -> ChatResponse:
    """Check citation references, not whether the cited text proves a claim."""
    if not isinstance(answer, str) or not answer.strip():
        raise LLMResponseError("The language model returned an empty answer.")
    answer = answer.strip()
    without_citations = CITATION_PATTERN.sub("", answer)
    normalized = " ".join(without_citations.replace("\u2019", "'").split())
    if normalized.casefold() == INSUFFICIENT_CONTEXT_ANSWER.casefold():
        return ChatResponse(answer=INSUFFICIENT_CONTEXT_ANSWER, sources=[])

    matches = list(CITATION_PATTERN.finditer(answer))
    if not matches or re.search(r"\[\s*\d", without_citations):
        raise LLMResponseError("The language model omitted or malformed its citations.")
    cited = {int(number) for match in matches for number in match[1].split(",")}
    if not cited.issubset(range(1, len(sources) + 1)):
        raise LLMResponseError("The language model cited an unknown source.")

    # Keep only cited passages and make answer numbers match the public list.
    ordered = sorted(cited)
    numbering = {old: new for new, old in enumerate(ordered, start=1)}
    answer = CITATION_PATTERN.sub(
        lambda match: "".join(f"[{numbering[int(n)]}]" for n in match[1].split(",")),
        answer,
    )
    return ChatResponse(answer=answer, sources=[sources[n - 1] for n in ordered])


async def answer_question(
    db: AsyncSession, request: ChatRequest, *, trace: dict | None = None,
) -> ChatResponse:
    """Retrieve context, generate an answer, and return validated sources.

    Empty retrieval returns immediately without invoking the LLM. Retrieval,
    validation, and LLM exceptions propagate to the API layer. Supply a fresh
    session with no pending writes or active transaction. The optional trace
    is for local diagnostics; private passage text is never logged by default.
    """
    if trace is not None:
        trace.update(request=request.model_dump(mode="json"), raw_answer=None)
    async with db.begin():
        retrieved_chunks = await search_similar_chunks(
            db=db,
            question=request.question,
            top_k=request.top_k,
            document_ids=request.document_ids,
        )
    if trace is not None:
        trace["retrieved_chunks"] = retrieved_chunks

    if not retrieved_chunks:
        response = ChatResponse(answer=INSUFFICIENT_CONTEXT_ANSWER, sources=[])
        if trace is not None:
            trace["messages"] = []
            trace["response"] = response.model_dump(mode="json")
        return response

    prompt = build_rag_prompt(request.question, retrieved_chunks)

    # Validate source metadata before sending any passages to the LLM.
    sources = [
        ChatSource.model_validate({
            "document_id": chunk.get("document_id"),
            "chunk_id": chunk.get("chunk_id"),
            "filename": chunk.get("filename"),
            "page_number": chunk.get("page_number"),
        })
        for chunk in retrieved_chunks
    ]

    if trace is not None:
        trace["messages"] = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    answer = await generate_llm_response(prompt, system_prompt=RAG_SYSTEM_PROMPT, trace=trace)
    if trace is not None:
        trace["raw_answer"] = answer
    response = validate_answer(answer, sources)
    if trace is not None:
        trace["response"] = response.model_dump(mode="json")
    return response
