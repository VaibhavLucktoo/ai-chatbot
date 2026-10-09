"""Private, loopback-only diagnostics for the first admin workspace."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.chat import get_db_session, run_chat
from app.core.local_access import require_admin_token
from app.prompts.rag import INSUFFICIENT_CONTEXT_ANSWER
from app.schemas.chat import ChatRequest, ClarificationResponse
from app.services.llm import _LLMSettings
from app.storage.models import Document, DocumentChunk

router = APIRouter(prefix="/admin", tags=["local admin"], dependencies=[Depends(require_admin_token)])


def diagnostics(trace):
    return jsonable_encoder({
        key: trace[key] for key in (
            "workflow_steps", "timings_ms", "total_ms", "retrieved_chunks", "selected_chunks",
            "sufficient_evidence", "rag_max_context_chunks", "rag_max_prompt_bytes", "llm_model",
            "generation", "generation_queue_ms", "token_usage", "raw_answer",
        ) if key in trace
    })


@router.get("/status")
async def admin_status(request: Request):
    settings = _LLMSettings()
    ready = await request.app.state.database.is_ready(check_schema=True)
    max_tokens = settings.max_output_tokens or (
        2048 if settings.model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"} else 300
    )
    return {"database_ready": ready, "model": settings.model, "temperature": settings.temperature,
            "max_output_tokens": max_tokens, "generation_timeout_seconds": settings.timeout_seconds,
            "mode": "local", "conversation_memory": False}


@router.get("/documents")
async def admin_documents(
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: AsyncSession = Depends(get_db_session, scope="function"),
):
    async with db.begin():
        total = await db.scalar(select(func.count()).select_from(Document))
        statement = select(
            Document.id, Document.filename, Document.page_count, Document.status, Document.created_at, Document.active,
            Document.processing_metadata,
            func.count(DocumentChunk.id).label("chunk_count"),
            (Document.lease_expires_at > func.now()).label("lease_active"),
        ).outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id).group_by(
            Document.id,
        ).order_by(Document.created_at.desc(), Document.id).offset(offset).limit(limit)
        rows = (await db.execute(statement)).mappings().all()
    items = [{**dict(row), "recoverable": row["status"] == "failed" or (
        row["status"] == "pending" and not row["lease_active"]
    )} for row in rows]
    return jsonable_encoder({"items": items, "total": total, "limit": limit, "offset": offset})


@router.post("/chat")
async def admin_chat(payload: ChatRequest, db: AsyncSession = Depends(get_db_session, scope="function")):
    trace = {}
    try:
        response = await run_chat(db, payload, trace=trace)
    except HTTPException as exc:
        return JSONResponse({"status": "error", "error": {"status_code": exc.status_code, "message": exc.detail},
                             "diagnostics": diagnostics(trace)}, status_code=exc.status_code)
    status = "clarification_required" if isinstance(response, ClarificationResponse) else (
        "insufficient_context" if response.answer == INSUFFICIENT_CONTEXT_ANSWER else "answered"
    )
    return {"status": status, "response": response.model_dump(mode="json"), "diagnostics": diagnostics(trace)}
