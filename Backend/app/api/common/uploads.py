"""Bounded HTTP upload reads and PDF envelope error mapping."""

from fastapi import HTTPException, UploadFile, status

from app.providers.documents import (
    MAX_PDF_BYTES,
    PDFExtractionError,
    PDFTooLargeError,
    validate_pdf_bytes,
)


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
