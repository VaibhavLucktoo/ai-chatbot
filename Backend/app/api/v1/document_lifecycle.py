"""Explicitly retire obsolete sources or erase a document and its chunks."""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import delete, update
from sqlalchemy.exc import SQLAlchemyError

from app.storage.models import Document

router = APIRouter(prefix="/documents", tags=["document lifecycle"])


class DocumentActivation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: StrictBool


@router.patch("/{document_id}/activation", status_code=204)
async def activate_document(document_id: UUID, payload: DocumentActivation, request: Request):
    try:
        async with request.app.state.database.transaction() as connection:
            result = await connection.execute(update(Document).where(
                Document.id == document_id, Document.status == "ready",
            ).values(active=payload.active))
    except SQLAlchemyError:
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    if result.rowcount != 1:
        raise HTTPException(404, "Ready document not found.")
    return Response(status_code=204)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: UUID, request: Request):
    try:
        async with request.app.state.database.transaction() as connection:
            result = await connection.execute(delete(Document).where(Document.id == document_id))
    except SQLAlchemyError:
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    if result.rowcount != 1:
        raise HTTPException(404, "Document not found.")
    return Response(status_code=204)
