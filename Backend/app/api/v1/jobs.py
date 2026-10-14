"""Durable PDF submission and status polling for the local workspace."""
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.documents import read_limited_pdf, validate_pdf_envelope
from app.schemas.documents import DocumentUploadMetadata
from app.storage.models import Document

router = APIRouter(prefix="/documents/jobs", tags=["document jobs"])


class DocumentJobResponse(BaseModel):
    document_id: UUID
    filename: str
    status: str


@router.post("", response_model=DocumentJobResponse, status_code=202)
async def submit_job(request: Request, response: Response,
                     file: Annotated[UploadFile, File(description="PDF, maximum 10 MB")]):
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(415, "File content type must be application/pdf.")
        try:
            metadata = DocumentUploadMetadata(filename=file.filename or "", content_type=file.content_type)
        except ValidationError:
            raise HTTPException(422, "Provide a path-safe .pdf filename of at most 255 characters.") from None
        data = await read_limited_pdf(file)
        validate_pdf_envelope(data)
    finally:
        await file.close()
    from app.services.document_hash import pdf_sha256
    digest = pdf_sha256(data)
    try:
        async with request.app.state.database.transaction() as connection:
            await connection.execute(insert(Document).values(
                id=uuid4(), filename=metadata.filename, content_sha256=digest,
                original_pdf=data, page_count=1, status="pending", lease_expires_at=func.now(),
            ).on_conflict_do_nothing(index_elements=[Document.content_sha256]))
            # Explicit resubmission retries failures. Preserve an active owner.
            await connection.execute(update(Document).where(
                Document.content_sha256 == digest, Document.status == "failed",
            ).values(status="pending", original_pdf=data, lease_expires_at=func.now(), attempt_id=None,
                     ingestion_attempts=0))
            await connection.execute(update(Document).where(
                Document.content_sha256 == digest, Document.status == "ready", Document.original_pdf.is_(None),
            ).values(original_pdf=data))
            row = (await connection.execute(select(Document.id, Document.filename, Document.status).where(
                Document.content_sha256 == digest,
            ))).one()
    except SQLAlchemyError:
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    response.headers["Location"] = f"/v1/documents/jobs/{row.id}"
    if row.status == "ready":
        response.status_code = 200
    return DocumentJobResponse(document_id=row.id, filename=row.filename, status=row.status)


@router.get("/{document_id}", response_model=DocumentJobResponse)
async def job_status(document_id: UUID, request: Request):
    try:
        async with request.app.state.database.transaction() as connection:
            row = (await connection.execute(select(Document.id, Document.filename, Document.status).where(
                Document.id == document_id,
            ))).one_or_none()
    except SQLAlchemyError:
        raise HTTPException(503, "Document storage is temporarily unavailable.") from None
    if row is None:
        raise HTTPException(404, "Document job not found.")
    return DocumentJobResponse(document_id=row.id, filename=row.filename, status=row.status)
