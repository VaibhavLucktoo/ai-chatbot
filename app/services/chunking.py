from dataclasses import dataclass
from functools import lru_cache

from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from app.providers.documents import ExtractedDocument

MODEL_NAME = "BAAI/bge-small-en-v1.5"
CHUNK_TOKENS = 350
OVERLAP_TOKENS = 40
MAX_ENCODED_TOKENS = 480  # Conservative margin below the model's 512 limit.


class ChunkingError(ValueError):
    """The extracted text cannot fit the ingestion limits."""


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_index: int      # Zero-based across the whole document.
    page_number: int      # One-based PDF page number.
    content: str


@lru_cache(maxsize=1)
def _get_tokenizer() -> Tokenizer:
    """Download/cache BGE's tokenizer configuration once."""
    tokenizer_path = hf_hub_download(
        repo_id=MODEL_NAME,
        filename="tokenizer.json",
    )
    tokenizer = Tokenizer.from_file(tokenizer_path)
    # Chunk the entire page, even if the downloaded config enables truncation.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


def chunk_document(document: ExtractedDocument) -> list[TextChunk]:
    """Split each page independently so every chunk has one source page."""
    tokenizer = _get_tokenizer()
    chunks: list[TextChunk] = []

    for page in document.pages:
        encoded = tokenizer.encode(
            page.text,
            add_special_tokens=False,
        )
        offsets = encoded.offsets
        start = 0

        while start < len(offsets):
            end = min(start + CHUNK_TOKENS, len(offsets))

            # Token offsets let us slice the ORIGINAL extracted text.
            # Decoding token IDs here could change its wording or spacing.
            content = page.text[
                offsets[start][0]:offsets[end - 1][1]
            ].strip()

            if content:
                encoded_length = len(
                    tokenizer.encode(
                        content,
                        add_special_tokens=True,
                    ).ids
                )

                if encoded_length > MAX_ENCODED_TOKENS:
                    raise ChunkingError(
                        f"Chunk on page {page.page_number} exceeds "
                        "the safe embedding token budget."
                    )

                chunks.append(
                    TextChunk(
                        chunk_index=len(chunks),
                        page_number=page.page_number,
                        content=content,
                    )
                )

            if end == len(offsets):
                break

            start = end - OVERLAP_TOKENS

    if not chunks:
        raise ChunkingError("No searchable chunks were produced.")

    return chunks
