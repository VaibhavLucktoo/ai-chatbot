"""Build grounded prompts and answer questions using retrieved PDF passages.

The search wrapper preserves caller transactions. Chat owns a short read
transaction on a fresh session and releases it before language generation.
"""

import asyncio
import json
import re
from dataclasses import asdict
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.errors import NodeCancelledError
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.providers.embeddings import get_embedding_provider
from app.prompts.rag import INSUFFICIENT_CONTEXT_ANSWER, RAG_SYSTEM_PROMPT
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource, ClarificationResponse, DocumentChoice
from app.storage.models import Document
from app.services.llm import LLMResponseError, generate_llm_response
from app.services.retrieval import RetrievalProviderError, has_sufficient_evidence, retrieve_chunks


def select_context_chunks(retrieved_chunks: list[dict], limit: int) -> list[dict]:
    """Take the first N candidates in retrieval's hybrid ranking order.

    This interim passage-count cap is not a generation-token budget. Preserve
    the original metadata and order; cosine distance is not the fused rank.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Context chunk limit must be an integer between 1 and 20.")
    return retrieved_chunks[:limit]


class _StructuredAnswer(BaseModel):
    """Validated structured response returned by the LLM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    answer: str = Field(strict=True, min_length=1)
    source_numbers: list[int]


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
    return _encode_rag_prompt(question, retrieved_chunks)


def _encode_rag_prompt(question: str, retrieved_chunks: list[dict]) -> str:

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
    """Validate original source references and cite returned source positions."""
    if not isinstance(answer, str) or not answer.strip():
        raise LLMResponseError("The language model returned an empty answer.")

    try:
        payload = json.loads(answer)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(
            "The language model returned invalid structured output."
        ) from exc

    try:
        structured = _StructuredAnswer.model_validate(payload)
    except ValidationError as exc:
        raise LLMResponseError(
            "The language model returned an invalid answer structure."
        ) from exc

    answer_text = structured.answer.strip()
    if not answer_text:
        raise LLMResponseError("The language model returned an empty answer.")

    # Source references come exclusively from source_numbers. Numeric arrays
    # and bracketed dates in prose are literal text, never parsed as citations.
    if re.search(r"\b(?:sources?|citations?)\s*\[\s*\d+(?:\s*,\s*\d+)*\s*\]", answer_text, re.IGNORECASE):
        raise LLMResponseError("The language model included inline numeric citations.")

    ordered = sorted(set(structured.source_numbers))
    if any(number < 1 or number > len(sources) for number in ordered):
        raise LLMResponseError("The language model cited an unknown source.")

    if answer_text == INSUFFICIENT_CONTEXT_ANSWER:
        if ordered:
            raise LLMResponseError("The language model cited sources for an insufficient-context answer.")
        return ChatResponse(answer=INSUFFICIENT_CONTEXT_ANSWER, sources=[])

    if not ordered:
        raise LLMResponseError("The language model omitted supporting sources.")

    citations = "".join(f"[{number}]" for number in range(1, len(ordered) + 1))
    return ChatResponse(
        answer=f"{answer_text} {citations}",
        sources=[sources[number - 1] for number in ordered],
    )


def needs_document_selection(question: str) -> bool:
    """Conservative English heuristic, not general conversation understanding."""
    return bool(re.search(
        r"\b(?:this|that|the)\s+(?:document|pdf|file)\b"
        r"|\b(?:summari[sz]e|explain|describe)\s+(?:it|this|that)\b",
        question, re.IGNORECASE,
    ))


class RAGState(TypedDict, total=False):
    """Per-request graph values; live resources belong to runtime context."""

    request: ChatRequest
    retrieved_chunks: list[dict]
    selected_chunks: list[dict]
    sufficient_evidence: bool
    prompt: str
    sources: list[ChatSource]
    raw_answer: str
    response: ChatResponse | ClarificationResponse


@dataclass(frozen=True)
class RAGContext:
    db: AsyncSession
    trace: dict | None = None


def _record_step(runtime: Runtime[RAGContext], name: str) -> None:
    if runtime.context.trace is not None:
        runtime.context.trace.setdefault("workflow_steps", []).append(name)


async def _retrieve(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    """Resolve document selection and retrieve in one short read transaction."""
    _record_step(runtime, "retrieve")
    db, trace = runtime.context.db, runtime.context.trace
    request = state["request"]
    if request.document_ids is None and needs_document_selection(request.question):
        async with db.begin():
            result = await db.execute(
                select(Document.id, Document.filename)
                .where(Document.status == "ready", Document.active.is_(True))
                .order_by(Document.filename, Document.id)
                .limit(51)
            )
            documents = [DocumentChoice(document_id=row.id, filename=row.filename)
                         for row in result.all()]
            if len(documents) != 1:
                response = ClarificationResponse(
                    question=("Which document do you mean? Select a filename."
                              if documents else "Please upload a PDF before asking about a document."),
                    original_question=request.question,
                    top_k=request.top_k,
                    documents=documents[:50],
                )
                if trace is not None:
                    trace.update(messages=[], response=response.model_dump(mode="json"))
                return {"response": response}
            request = request.model_copy(update={"document_ids": [documents[0].document_id]})
    # A selection query must not keep its connection during query embedding.
    async with db.begin():
        retrieved_chunks = await search_similar_chunks(
            db=db,
            question=request.question,
            top_k=request.top_k,
            document_ids=request.document_ids,
        )
    if trace is not None:
        trace["retrieved_chunks"] = retrieved_chunks
    return {"request": request, "retrieved_chunks": retrieved_chunks}


async def _select_context(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "select_context")
    trace = runtime.context.trace
    settings = get_settings()
    selected_chunks = select_context_chunks(state["retrieved_chunks"], settings.rag_max_context_chunks)
    byte_budget = getattr(settings, "rag_max_prompt_bytes", 24000)
    # A byte-level tokenizer cannot produce more tokens than UTF-8 bytes.
    # Reserve output and 512 tokens for provider message framing. This is
    # conservative; configure the window to the actual served model.
    token_budget = (getattr(settings, "rag_context_window_tokens", 32768)
                    - getattr(settings, "rag_output_reserve_tokens", 4096) - 512)
    byte_budget = min(byte_budget, token_budget)
    budgeted = []
    for chunk in selected_chunks:
        trial = _encode_rag_prompt(state["request"].question, budgeted + [chunk])
        if len((RAG_SYSTEM_PROMPT + trial).encode("utf-8")) > byte_budget:
            break
        budgeted.append(chunk)
    selected_chunks = budgeted
    sufficient_evidence = has_sufficient_evidence(
        selected_chunks, max_cosine_distance=settings.rag_max_cosine_distance,
    )
    if trace is not None:
        trace["selected_chunks"] = selected_chunks
        trace["rag_max_context_chunks"] = settings.rag_max_context_chunks
        trace["sufficient_evidence"] = sufficient_evidence
        trace["rag_max_prompt_bytes"] = byte_budget
    return {"selected_chunks": selected_chunks, "sufficient_evidence": sufficient_evidence}


async def _fallback(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "fallback")
    response = ChatResponse(answer=INSUFFICIENT_CONTEXT_ANSWER, sources=[])
    if runtime.context.trace is not None:
        runtime.context.trace.update(messages=[], response=response.model_dump(mode="json"))
    return {"response": response}


async def _prepare_prompt(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "prepare_prompt")
    trace = runtime.context.trace
    prompt = build_rag_prompt(state["request"].question, state["selected_chunks"])

    # Validate source metadata before sending any passages to the LLM.
    sources = [
        ChatSource.model_validate({
            "document_id": chunk.get("document_id"),
            "chunk_id": chunk.get("chunk_id"),
            "filename": chunk.get("filename"),
            "page_number": chunk.get("page_number"),
        })
        for chunk in state["selected_chunks"]
    ]

    if trace is not None:
        trace["messages"] = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    return {"prompt": prompt, "sources": sources}


async def _generate(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "generate")
    trace = runtime.context.trace
    answer = await generate_llm_response(state["prompt"], system_prompt=RAG_SYSTEM_PROMPT, trace=trace)
    if trace is not None:
        trace["raw_answer"] = answer
    return {"raw_answer": answer}


async def _validate(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "validate")
    response = validate_answer(state["raw_answer"], state["sources"])
    if runtime.context.trace is not None:
        runtime.context.trace["response"] = response.model_dump(mode="json")
    return {"response": response}


def _after_retrieval(state: RAGState) -> str:
    return END if "response" in state else "select_context"


def _after_context(state: RAGState) -> str:
    return "prepare_prompt" if state["sufficient_evidence"] else "fallback"


def _timed_node(name, node):
    async def run(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
        start = perf_counter()
        try:
            return await node(state, runtime)
        finally:
            if runtime.context.trace is not None:
                runtime.context.trace.setdefault("timings_ms", {})[name] = round(
                    (perf_counter() - start) * 1000, 2,
                )
    return run


@lru_cache(maxsize=1)
def get_rag_graph():
    """Compile once; invocations have independent state and runtime resources."""
    builder = StateGraph(RAGState, context_schema=RAGContext)
    for name, node in (
        ("retrieve", _retrieve), ("select_context", _select_context),
        ("fallback", _fallback), ("prepare_prompt", _prepare_prompt),
        ("generate", _generate), ("validate", _validate),
    ):
        builder.add_node(name, _timed_node(name, node))
    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges("retrieve", _after_retrieval, [END, "select_context"])
    builder.add_conditional_edges("select_context", _after_context, ["prepare_prompt", "fallback"])
    builder.add_edge("prepare_prompt", "generate")
    builder.add_edge("generate", "validate")
    builder.add_edge("validate", END)
    builder.add_edge("fallback", END)
    return builder.compile()


async def answer_question(
    db: AsyncSession, request: ChatRequest, *, trace: dict | None = None,
) -> ChatResponse | ClarificationResponse:
    """Run stateless RAG orchestration, preserving the public API and exceptions.

    Supply a fresh session without pending writes or an active transaction.
    No checkpointing or automatic retries are enabled. Diagnostic traces retain
    intermediate results on failure; document text is not logged by default.
    """
    if trace is not None:
        trace.update(request=request.model_dump(mode="json"), raw_answer=None, workflow_steps=[], timings_ms={})
    started = perf_counter()
    try:
        async with asyncio.timeout(getattr(get_settings(), "chat_timeout_seconds", 180)):
            result = await get_rag_graph().ainvoke(
                {"request": request}, context=RAGContext(db=db, trace=trace),
            )
    except NodeCancelledError as exc:
        # Preserve the pre-migration contract for provider-raised cancellation.
        if isinstance(exc.__cause__, asyncio.CancelledError):
            raise exc.__cause__
        raise asyncio.CancelledError() from exc
    except TimeoutError as exc:
        from app.services.llm import LLMTimeoutError
        raise LLMTimeoutError("The complete chat request exceeded its deadline.") from exc
    finally:
        if trace is not None:
            trace["total_ms"] = round((perf_counter() - started) * 1000, 2)
    return result["response"]
