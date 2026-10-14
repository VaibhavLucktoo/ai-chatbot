"""HTTP endpoints for uploading and searching PDF documents."""

import logging
from typing import Annotated, cast

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.providers.documents import (
    MAX_PDF_BYTES,
    PDFExtractionError,
    PDFTooLargeError,
    validate_pdf_bytes,
)
from app.providers.embeddings import get_embedding_provider
from app.schemas.documents import (
    DocumentChunkResult,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentUploadMetadata,
    DocumentUploadResponse,
)
from app.services.chunking import ChunkingError
from app.services.ingestion import IngestionProcessingError, ingest_pdf
from app.services.retrieval import RetrievalProviderError, retrieve_chunks
from app.storage.db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

READ_SIZE = 64 * 1024


async def read_limited_pdf(file: UploadFile) -> bytes:
    """Read in bounded blocks and reject files above MAX_PDF_BYTES."""

    if file.size is not None and file.size > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="PDF exceeds the 10 MB limit.",
        )

    data = bytearray()

    while True:
        remaining = MAX_PDF_BYTES + 1 - len(data)
        part = await file.read(min(READ_SIZE, remaining))

        if not part:
            break

        data.extend(part)

        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="PDF exceeds the 10 MB limit.",
            )

    return bytes(data)


def validate_pdf_envelope(data: bytes) -> None:
    """Translate shared PDF byte checks into HTTP errors."""
    try:
        validate_pdf_bytes(data)
    except PDFTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except PDFExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": DocumentUploadResponse},
        409: {"description": "This PDF is already being processed; retry later"},
        413: {"description": "PDF exceeds the size limit"},
        415: {"description": "Expected application/pdf"},
        422: {"description": "Invalid filename or PDF"},
        500: {"description": "Internal ingestion error"},
        503: {"description": "Document storage or processing unavailable"},
    },
)
async def upload_document(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="PDF, maximum 10 MB")],
) -> DocumentUploadResponse:
    """Validate a PDF and ingest it through the existing service."""

    try:
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="File content type must be application/pdf.",
            )

        try:
            metadata = DocumentUploadMetadata(
                filename=file.filename or "",
                content_type=file.content_type,
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Provide a path-safe .pdf filename "
                    "of at most 255 characters."
                ),
            ) from exc

        data = await read_limited_pdf(file)
        validate_pdf_envelope(data)
    finally:
        await file.close()

    try:
        database = cast(Database, request.app.state.database)
        try:
            embedding_provider = get_embedding_provider()
        except (ValueError, RuntimeError) as exc:
            raise IngestionProcessingError("Embedding provider unavailable.") from exc

        result = await ingest_pdf(
            database=database,
            embeddings=embedding_provider,
            filename=metadata.filename,
            data=data,
        )
    except PDFTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except (PDFExtractionError, ChunkingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (IngestionProcessingError, SQLAlchemyError, TimeoutError) as exc:
        logger.warning("Document upload failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document processing is temporarily unavailable. Please retry.",
        ) from exc
    except Exception as exc:
        logger.error("Unexpected PDF ingestion failure (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document ingestion failed.",
        ) from exc

    if result.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This PDF is already being processed. Please retry later.",
            headers={"Retry-After": "5"},
        )

    if result.already_existed:
        response.status_code = status.HTTP_200_OK

    return DocumentUploadResponse(
        document_id=result.document_id,
        filename=result.filename,
        page_count=result.page_count,
        chunk_count=result.chunk_count,
        status="ready",
        already_existed=result.already_existed,
    )


@router.post(
    "/search",
    response_model=DocumentSearchResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid search parameters"},
        422: {"description": "Request schema validation failed"},
        500: {"description": "Search failed"},
        503: {"description": "Document storage unavailable"},
    },
)
async def search_documents(
    payload: DocumentSearchRequest,
    request: Request,
) -> DocumentSearchResponse:
    """Retrieve relevant passages with filenames and page numbers."""

    try:
        database = cast(Database, request.app.state.database)
        try:
            embedding_provider = get_embedding_provider()
        except (ValueError, RuntimeError) as exc:
            raise RetrievalProviderError("Embedding provider unavailable.") from exc

        result = await retrieve_chunks(
            database=database,
            embeddings=embedding_provider,
            query=payload.query,
            top_k=payload.top_k,
            document_ids=payload.document_ids,
        )

        chunks = [
            DocumentChunkResult(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                cosine_distance=chunk.cosine_distance,
            )
            for chunk in result.chunks
        ]

        return DocumentSearchResponse(
            query=result.query,
            top_k=result.top_k,
            matches=len(chunks),
            results=chunks,
        )

    except ValidationError as exc:
        # Response construction errors are server failures.
        logger.error("Invalid internal document search result (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document search returned an invalid result.",
        ) from exc
    except RetrievalProviderError as exc:
        logger.error("Embedding failure during document search (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The query embedding could not be generated.",
        ) from exc
    except ValueError as exc:
        logger.warning("Search parameters rejected (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid search parameters.",
        ) from exc
    except (SQLAlchemyError, TimeoutError) as exc:
        logger.warning("Database failure during document search (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        logger.error("Unexpected document search failure (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document search failed.",
        ) from exc
