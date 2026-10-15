"""Paginated document metadata and retained PDF access for the local client."""

from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.documents import ChunkResponse, DocumentDetail, DocumentListResponse
from app.storage import document_catalog as catalog_storage

# Deprecated helper location; retain compatibility for downstream imports.
from app.storage.document_catalog import metadata_query as metadata_query

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Literal["pending", "ready", "failed"] | None = None,
    active: bool | None = None,
):
    try:
        total, rows = await catalog_storage.list_documents(
            request.app.state.database,
            limit=limit,
            offset=offset,
            status=status,
            active=active,
        )
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    return DocumentListResponse(
        items=[DocumentDetail.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: UUID, request: Request):
    try:
        row = await catalog_storage.get_document(
            request.app.state.database, document_id
        )
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    if row is None:
        raise HTTPException(404, "Document not found.")
    return DocumentDetail.model_validate(row)


@router.get(
    "/{document_id}/source",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_source(document_id: UUID, request: Request):
    try:
        row = await catalog_storage.download_source(
            request.app.state.database, document_id
        )
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    if row is None:
        raise HTTPException(404, "Document not found.")
    if row.original_pdf is None:
        raise HTTPException(
            409,
            "Original PDF is unavailable. Re-upload the original file to retain it.",
        )
    return Response(
        bytes(row.original_pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(row.filename, safe=""),
        },
    )


@router.get("/{document_id}/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_source_chunk(document_id: UUID, chunk_id: UUID, request: Request):
    """Resolve a chat citation without requiring a retained original PDF."""
    try:
        row = await catalog_storage.get_source_chunk(
            request.app.state.database, document_id, chunk_id
        )
    except (SQLAlchemyError, TimeoutError):
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    if row is None:
        raise HTTPException(404, "Source chunk not found.")
    return ChunkResponse.model_validate(row)
