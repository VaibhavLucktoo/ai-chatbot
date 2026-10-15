"""Durable PDF submission and status polling for the local workspace."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.common.uploads import read_limited_pdf, validate_pdf_envelope
from app.schemas.documents import DocumentUploadMetadata

# Deprecated schema location; retain compatibility for downstream imports.
from app.schemas.documents import DocumentJobResponse as DocumentJobResponse
from app.storage import document_jobs as job_storage

router = APIRouter(prefix="/documents/jobs", tags=["document jobs"])


@router.post("", response_model=DocumentJobResponse, status_code=202)
async def submit_job(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="PDF, maximum 10 MB")],
):
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(415, "File content type must be application/pdf.")
        try:
            metadata = DocumentUploadMetadata(
                filename=file.filename or "", content_type=file.content_type
            )
        except ValidationError:
            raise HTTPException(
                422, "Provide a path-safe .pdf filename of at most 255 characters."
            ) from None
        data = await read_limited_pdf(file)
        validate_pdf_envelope(data)
    finally:
        await file.close()
    from app.services.document_hash import pdf_sha256

    digest = pdf_sha256(data)
    try:
        row = await job_storage.enqueue_document(
            request.app.state.database,
            filename=metadata.filename,
            digest=digest,
            data=data,
        )
    except SQLAlchemyError:
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    response.headers["Location"] = f"/v1/documents/jobs/{row.id}"
    if row.status == "ready":
        response.status_code = 200
    return DocumentJobResponse(
        document_id=row.id, filename=row.filename, status=row.status
    )


@router.get("/{document_id}", response_model=DocumentJobResponse)
async def job_status(document_id: UUID, request: Request):
    try:
        row = await job_storage.job_status(request.app.state.database, document_id)
    except SQLAlchemyError:
        raise HTTPException(
            503, "Document storage is temporarily unavailable."
        ) from None
    if row is None:
        raise HTTPException(404, "Document job not found.")
    return DocumentJobResponse(
        document_id=row.id, filename=row.filename, status=row.status
    )
