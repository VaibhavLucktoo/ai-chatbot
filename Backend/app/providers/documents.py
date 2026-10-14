from dataclasses import dataclass
from io import BytesIO
import re

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGES = 100
MAX_EXTRACTED_CHARS = 2_000_000
PDF_EOF_PATTERN = re.compile(rb"%%EOF[\x00\t\n\x0c\r ]*\Z")


class PDFExtractionError(ValueError):
    """A PDF cannot be accepted for text extraction."""


class PDFTooLargeError(PDFExtractionError):
    """The uploaded bytes exceed the file limit."""


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int  # One-based: matches the page shown to a reader.
    text: str


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    page_count: int
    pages: tuple[ExtractedPage, ...]


def validate_pdf_bytes(data: bytes) -> None:
    """Apply the same file checks to HTTP uploads and CLI ingestion."""
    if not data:
        raise PDFExtractionError("The PDF is empty.")

    if len(data) > MAX_PDF_BYTES:
        raise PDFTooLargeError("The PDF exceeds the 10 MB limit.")

    if not data.startswith(b"%PDF-"):
        raise PDFExtractionError("The file is not a valid PDF.")

    if not PDF_EOF_PATTERN.search(data[-2048:]):
        raise PDFExtractionError("The file does not have a valid PDF end marker.")


def extract_pdf(data: bytes) -> ExtractedDocument:
    """Extract searchable text while retaining its original page number."""
    validate_pdf_bytes(data)

    try:
        reader = PdfReader(BytesIO(data), strict=True)

        if reader.is_encrypted:
            raise PDFExtractionError(
                "Password-protected PDFs are not supported."
            )

        page_count = len(reader.pages)
        if page_count == 0:
            raise PDFExtractionError("The PDF contains no pages.")

        if page_count > MAX_PAGES:
            raise PDFExtractionError("The PDF exceeds the 100-page limit.")

        pages: list[ExtractedPage] = []
        total_chars = 0

        for page_number, page in enumerate(reader.pages, start=1):
            # PDF font mappings can produce null padding. PostgreSQL text
            # cannot store U+0000; keep a word boundary instead of joining
            # adjacent text or making an otherwise readable PDF fail storage.
            text = (page.extract_text() or "").replace("\x00", " ").strip()

            total_chars += len(text)
            if total_chars > MAX_EXTRACTED_CHARS:
                raise PDFExtractionError(
                    "The PDF contains too much extracted text."
                )

            # Empty pages retain their position in page_count but produce
            # no searchable chunk later.
            if text:
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        text=text,
                    )
                )

        if not pages:
            raise PDFExtractionError(
                "No searchable text was found. "
                "The PDF may require OCR."
            )

        return ExtractedDocument(
            page_count=page_count,
            pages=tuple(pages),
        )

    except PDFExtractionError:
        raise
    except (
        PyPdfError, OSError, ValueError, TypeError, KeyError, IndexError,
        AttributeError, ArithmeticError, RecursionError, NotImplementedError,
    ) as exc:
        raise PDFExtractionError(
            "The PDF is damaged or uses an unsupported PDF feature."
        ) from exc
