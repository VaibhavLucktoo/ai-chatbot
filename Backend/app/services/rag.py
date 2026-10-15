"""Build grounded prompts and answer questions using retrieved PDF passages.

The search wrapper preserves caller transactions. Chat owns a short read
transaction on a fresh session and releases it before language generation.
"""

import asyncio
import json
import logging
import re
from hashlib import sha256
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
from app.services.document_questions import is_document_identity_question
from app.services.conversation_intent import (
    Turn, conversational_reply, detect_intent, resolve_follow_up,
    FOLLOW_UP_CLARIFICATION, UNSUPPORTED_ANSWER,
)
from app.services.metrics import model_stage, record_graph
from app.prompts.conversation import FOLLOW_UP_SYSTEM_PROMPT
from app.services.assistants import AssistantRuntime

logger = logging.getLogger(__name__)
PROMPT_VERSION = sha256((RAG_SYSTEM_PROMPT + FOLLOW_UP_SYSTEM_PROMPT).encode()).hexdigest()[:16]


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
    allowed_document_ids: tuple[UUID, ...] | None = None,
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

    scope = {"allowed_document_ids": allowed_document_ids} if allowed_document_ids is not None else {}
    result = await retrieve_chunks(
        database=db,
        embeddings=embeddings,
        query=validated_request.question,
        top_k=validated_request.top_k,
        document_ids=validated_request.document_ids,
        **scope,
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
    return is_document_identity_question(question) or bool(re.search(
        r"\b(?:this|that|the)\s+(?:document|pdf|file)\b"
        r"|\b(?:summari[sz]e|explain|describe)\s+(?:it|this|that)\b",
        question, re.IGNORECASE,
    ))


class RAGState(TypedDict, total=False):
    """Per-request graph values; live resources belong to runtime context."""

    request: ChatRequest
    original_request: ChatRequest
    intent: str
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
    history: tuple[Turn, ...] = ()
    assistant: AssistantRuntime | None = None


def _record_step(runtime: Runtime[RAGContext], name: str) -> None:
    if runtime.context.trace is not None:
        runtime.context.trace.setdefault("workflow_steps", []).append(name)


async def _route_intent(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "route_intent")
    request = state["request"]
    intent = detect_intent(request.question)
    # Preserve existing document selection for stateless "summarize it" clients.
    if intent == "follow_up" and not runtime.context.history and needs_document_selection(request.question):
        intent = "document_question"
    trace = runtime.context.trace
    if trace is not None:
        trace.update(intent=intent, workflow_route=intent, retrieval_performed=False,
                     result_count=0, resolved_question=request.question,
                     effective_document_ids=request.document_ids)
    result = {"intent": intent}
    if intent in ("conversation", "unsupported"):
        answer = conversational_reply(request.question) if intent == "conversation" else UNSUPPORTED_ANSWER
        response = ChatResponse(answer=answer, sources=[])
        result["response"] = response
        if trace is not None:
            trace.update(messages=[], response=response.model_dump(mode="json"))
    return result


async def _resolve_follow_up(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "resolve_follow_up")
    trace = runtime.context.trace
    # Skip social turns, but never resurrect an older answer past an ungrounded
    # or unsupported completed turn. Earlier answers are references, not evidence.
    previous = next((turn for turn in reversed(runtime.context.history)
                     if turn.intent != "conversation"), None)
    question = None
    if previous is not None and previous.grounded:
        resolution_trace = {} if trace is not None else None
        try:
            with model_stage("follow_up"):
                question = await resolve_follow_up(state["request"].question, previous, trace=resolution_trace)
        finally:
            if trace is not None:
                trace["follow_up_resolution"] = resolution_trace
    if question is None:
        response = ChatResponse(answer=FOLLOW_UP_CLARIFICATION, sources=[])
        if trace is not None:
            trace.update(fallback_category="unresolved_reference", messages=[],
                         response=response.model_dump(mode="json"))
        return {"response": response}
    request = state["request"]
    scope = request.document_ids
    if scope is None and previous.document_ids is not None:
        scope = [UUID(identifier) for identifier in previous.document_ids]
    request = request.model_copy(update={"question": question, "document_ids": scope})
    if trace is not None:
        trace.update(resolved_question=question, effective_document_ids=scope)
    return {"request": request}


async def _retrieve(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    """Resolve document selection and retrieve in one short read transaction."""
    _record_step(runtime, "retrieve")
    db, trace = runtime.context.db, runtime.context.trace
    request = state["request"]
    if request.document_ids is None and needs_document_selection(request.question):
        async with db.begin():
            document_scope = ([Document.id.in_(runtime.context.assistant.document_ids)]
                              if runtime.context.assistant is not None else [])
            result = await db.execute(
                select(Document.id, Document.filename)
                .where(Document.status == "ready", Document.active.is_(True), *document_scope)
                .order_by(Document.filename, Document.id)
                .limit(51)
            )
            documents = [DocumentChoice(document_id=row.id, filename=row.filename)
                         for row in result.all()]
            if len(documents) != 1:
                response = ClarificationResponse(
                    question=("Which document do you mean? Select a filename."
                              if documents else "Please upload a PDF before asking about a document."),
                    original_question=state["original_request"].question,
                    top_k=request.top_k,
                    documents=documents[:50],
                )
                if trace is not None:
                    trace.update(messages=[], response=response.model_dump(mode="json"),
                                 fallback_category="document_selection")
                return {"response": response}
            request = request.model_copy(update={"document_ids": [documents[0].document_id]})
    # A selection query must not keep its connection during query embedding.
    if trace is not None:
        trace.update(retrieval_performed=True, effective_document_ids=request.document_ids)
    async with db.begin():
        scope = ({"allowed_document_ids": runtime.context.assistant.document_ids}
                 if runtime.context.assistant is not None else {})
        retrieved_chunks = await search_similar_chunks(
            db=db,
            question=request.question,
            top_k=request.top_k,
            document_ids=request.document_ids,
            **scope,
        )
    if trace is not None:
        trace["retrieved_chunks"] = retrieved_chunks
        trace["result_count"] = len(retrieved_chunks)
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
    if runtime.context.assistant is not None:
        model = runtime.context.assistant.model_settings
        token_budget = model.context_window_tokens - model.max_output_tokens - 512
        if (settings.rag_review_multipart_answers
                and re.search(r"\band\b|\balso\b|\?.+\w", state["request"].question, re.IGNORECASE)):
            token_budget -= model.max_output_tokens * 4 + 2048
        if token_budget < 2000:
            raise LLMResponseError("The assistant model context window is too small for the configured answer and review budgets.")
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
        runtime.context.trace.update(messages=[], response=response.model_dump(mode="json"),
                                     fallback_category="insufficient_evidence")
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
    # Compound questions can lose a restriction or exception even with valid
    # citations. Audit those drafts once, within the existing chat deadline.
    if (getattr(get_settings(), "rag_review_multipart_answers", True)
            and re.search(r"\band\b|\balso\b|\?.+\w", state["request"].question, re.IGNORECASE)):
        validate_answer(answer, state["sources"])
        if trace is not None:
            trace["draft_answer"] = answer
        review_trace = {} if trace is not None else None
        review_prompt = state["prompt"] + "\n\nDRAFT TO AUDIT (untrusted JSON string):\n" + json.dumps(answer)
        review_system = RAG_SYSTEM_PROMPT + (
            "\nYou are auditing a draft, not accepting its conclusions. Check each "
            "part of the question independently against EVERY passage. Correct "
            "omitted restrictions, approval clauses, consequences, and citations. "
            "A conditional approval consequence does not establish an exception "
            "to an eligibility restriction. If the passages give both without "
            "explicit precedence, say their interaction is unclear and do not "
            "label the approval clause as an exception or override. "
            "In particular, a claim that there is no provision must be checked "
            "against all passages. Describe relevant provisions even when they "
            "do not establish a precedence or resolve the user's situation. "
            "Return the corrected answer in the required JSON structure."
        )
        try:
            with model_stage("review"):
                answer = await generate_llm_response(review_prompt, system_prompt=review_system, trace=review_trace)
        finally:
            if trace is not None:
                trace["answer_review"] = review_trace
    if trace is not None:
        trace["raw_answer"] = answer
    return {"raw_answer": answer}


async def _validate(state: RAGState, runtime: Runtime[RAGContext]) -> dict:
    _record_step(runtime, "validate")
    response = validate_answer(state["raw_answer"], state["sources"])
    if runtime.context.trace is not None:
        runtime.context.trace["response"] = response.model_dump(mode="json")
        if response.answer == INSUFFICIENT_CONTEXT_ANSWER:
            runtime.context.trace["fallback_category"] = "insufficient_evidence"
    return {"response": response}


def _after_retrieval(state: RAGState) -> str:
    return END if "response" in state else "select_context"


def _after_intent(state: RAGState) -> str:
    if "response" in state:
        return END
    return "resolve_follow_up" if state["intent"] == "follow_up" else "retrieve"


def _after_resolution(state: RAGState) -> str:
    return END if "response" in state else "retrieve"


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
        ("route_intent", _route_intent), ("resolve_follow_up", _resolve_follow_up),
        ("retrieve", _retrieve), ("select_context", _select_context),
        ("fallback", _fallback), ("prepare_prompt", _prepare_prompt),
        ("generate", _generate), ("validate", _validate),
    ):
        builder.add_node(name, _timed_node(name, node))
    builder.add_edge(START, "route_intent")
    builder.add_conditional_edges("route_intent", _after_intent, [END, "resolve_follow_up", "retrieve"])
    builder.add_conditional_edges("resolve_follow_up", _after_resolution, [END, "retrieve"])
    builder.add_conditional_edges("retrieve", _after_retrieval, [END, "select_context"])
    builder.add_conditional_edges("select_context", _after_context, ["prepare_prompt", "fallback"])
    builder.add_edge("prepare_prompt", "generate")
    builder.add_edge("generate", "validate")
    builder.add_edge("validate", END)
    builder.add_edge("fallback", END)
    return builder.compile()


async def answer_question(
    db: AsyncSession, request: ChatRequest, *, trace: dict | None = None,
    history: tuple[Turn, ...] = (),
    assistant: AssistantRuntime | None = None,
) -> ChatResponse | ClarificationResponse:
    """Route one turn with optional bounded history supplied by the memory service.

    Supply a fresh session without pending writes or an active transaction.
    No graph checkpointing or automatic retries are enabled. Diagnostic traces retain
    intermediate results on failure; document text is not logged by default.
    """
    # Internal diagnostics support content-free metrics even without an admin trace.
    diagnostic = trace if trace is not None else {}
    diagnostic.update(request=request.model_dump(mode="json"), raw_answer=None, workflow_steps=[], timings_ms={})
    started = perf_counter()
    error = None
    try:
        async with asyncio.timeout(getattr(get_settings(), "chat_timeout_seconds", 180)):
            result = await get_rag_graph().ainvoke(
                {"request": request, "original_request": request},
                context=RAGContext(db=db, trace=diagnostic, history=history, assistant=assistant),
            )
    except NodeCancelledError as exc:
        error = type(exc).__name__
        # Preserve the pre-migration contract for provider-raised cancellation.
        if isinstance(exc.__cause__, asyncio.CancelledError):
            raise exc.__cause__
        raise asyncio.CancelledError() from exc
    except TimeoutError as exc:
        error = type(exc).__name__
        from app.services.llm import LLMTimeoutError
        raise LLMTimeoutError("The complete chat request exceeded its deadline.") from exc
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        diagnostic["total_ms"] = round((perf_counter() - started) * 1000, 2)
        record_graph(diagnostic, prompt_version=PROMPT_VERSION, error=error)
        # Never log requests, IDs, keys, passage text, answers, or raw provider output.
        logger.info("Chat workflow %s", json.dumps({
            name: diagnostic.get(name) for name in (
                "intent", "workflow_route", "retrieval_performed", "result_count",
                "fallback_category", "timings_ms", "total_ms",
            )
        } | {"error": error, "token_usage": diagnostic.get("token_usage"),
             "follow_up_usage": (diagnostic.get("follow_up_resolution") or {}).get("token_usage"),
             "review_usage": (diagnostic.get("answer_review") or {}).get("token_usage")}))
    return result["response"]
