"""Explicitly retire obsolete sources or erase a document and its chunks."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError

# Deprecated schema location; retain compatibility for downstream imports.
from app.schemas.documents import DocumentActivation as DocumentActivation
from app.storage import document_lifecycle as lifecycle_storage

router = APIRouter(prefix="/documents", tags=["document lifecycle"])


@router.patch("/{document_id}/activation", status_code=204)
async def activate_document(
    document_id: UUID, payload: DocumentActivation, request: Request
):
    try:
        rowcount = await lifecycle_storage.set_document_activation(
            request.app.state.database, document_id, payload.active
        )
    except SQLAlchemyError:
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    if rowcount != 1:
        raise HTTPException(404, "Ready document not found.")
    return Response(status_code=204)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: UUID, request: Request):
    try:
        rowcount = await lifecycle_storage.delete_document(
            request.app.state.database, document_id
        )
    except SQLAlchemyError:
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    if rowcount != 1:
        raise HTTPException(404, "Document not found.")
    return Response(status_code=204)
