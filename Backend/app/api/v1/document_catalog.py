"""Paginated document metadata and retained PDF access for the local client."""

from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.documents import ChunkResponse, DocumentDetail, DocumentListResponse
from app.storage.models import Document, DocumentChunk

router = APIRouter(prefix="/documents", tags=["documents"])


def metadata_query():
    chunk_count = select(func.count()).select_from(DocumentChunk).where(
        DocumentChunk.document_id == Document.id,
    ).correlate(Document).scalar_subquery()
    return select(
        Document.id, Document.filename, Document.page_count, Document.status,
        Document.created_at, Document.active, chunk_count.label("chunk_count"),
        Document.original_pdf.is_not(None).label("source_available"),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Literal["pending", "ready", "failed"] | None = None,
    active: bool | None = None,
):
    filters = []
    if status is not None:
        filters.append(Document.status == status)
    if active is not None:
        filters.append(Document.active == active)
    try:
        async with request.app.state.database.transaction() as connection:
            total = await connection.scalar(select(func.count()).select_from(Document).where(*filters))
            rows = (await connection.execute(metadata_query().where(*filters).order_by(
                Document.created_at.desc(), Document.id,
            ).offset(offset).limit(limit))).mappings().all()
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    return DocumentListResponse(items=[DocumentDetail.model_validate(row) for row in rows],
                                total=total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: UUID, request: Request):
    try:
        async with request.app.state.database.transaction() as connection:
            row = (await connection.execute(metadata_query().where(Document.id == document_id))).mappings().one_or_none()
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    if row is None:
        raise HTTPException(404, "Document not found.")
    return DocumentDetail.model_validate(row)


@router.get("/{document_id}/source", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def download_source(document_id: UUID, request: Request):
    try:
        async with request.app.state.database.transaction() as connection:
            row = (await connection.execute(select(Document.filename, Document.original_pdf).where(
                Document.id == document_id,
            ))).one_or_none()
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    if row is None:
        raise HTTPException(404, "Document not found.")
    if row.original_pdf is None:
        raise HTTPException(409, "Original PDF is unavailable. Re-upload the original file to retain it.")
    return Response(bytes(row.original_pdf), media_type="application/pdf", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.filename, safe=""),
    })


@router.get("/{document_id}/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_source_chunk(document_id: UUID, chunk_id: UUID, request: Request):
    """Resolve a chat citation without requiring a retained original PDF."""
    try:
        async with request.app.state.database.transaction() as connection:
            row = (await connection.execute(select(
                DocumentChunk.id, DocumentChunk.document_id, Document.filename,
                DocumentChunk.page_number, DocumentChunk.chunk_index, DocumentChunk.content,
            ).join(Document, Document.id == DocumentChunk.document_id).where(
                Document.id == document_id, DocumentChunk.id == chunk_id,
            ))).mappings().one_or_none()
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    if row is None:
        raise HTTPException(404, "Source chunk not found.")
    return ChunkResponse.model_validate(row)
