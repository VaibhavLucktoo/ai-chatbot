# AI Chatbot

A FastAPI backend for answering questions from documents. PDF ingestion includes
page-aware extraction, token-aware chunking, FastEmbed embeddings, PostgreSQL
persistence, duplicate detection, and retries. Retrieval and chat are next.

## Local setup

Requirements: Python 3.12 or newer, uv, and Docker Desktop running Linux containers.

### 1. Configure the environment

For a new checkout, create your local configuration:

```powershell
Copy-Item .env.example .env
uv sync --locked
```

If `.env` already exists, add any missing settings from `.env.example` instead of
overwriting it. Set `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` in `.env`;
both the API and Docker Compose read these values. The API connects to
`DB_HOST=127.0.0.1` and `DB_PORT=5433` by default.

The database volume keeps its data between container restarts. Changing database
credentials in `.env` does not change credentials in an existing database volume.

### 2. Start the database and apply migrations

Start Docker Desktop, then run:

```powershell
docker compose config --quiet
docker compose up -d db
docker compose ps
uv run alembic upgrade head
uv run alembic current
```

Wait for the database to show as healthy before applying migrations. The expected
current revision is `7f7483ec3680 (head)`.

The initialization script enables pgvector when a fresh database volume is
created. An existing volume must already have the `vector` extension enabled.
API startup checks the connection and extension; it does not apply migrations.

### 3. Start and check the API

```powershell
uv run python run.py
```

Keep this terminal running. In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/health
Invoke-RestMethod http://127.0.0.1:8000/v1/ready
```

Both endpoints should return HTTP 200, with readiness reporting `ready`.
Interactive API documentation is available at <http://127.0.0.1:8000/docs>.
Use `run.py` on Windows so Psycopg gets a compatible event loop.

The embedding provider loads `BAAI/bge-small-en-v1.5` on first use and caches model
files in `.cache/fastembed`. Health endpoints do not load or verify the model.

## Upload a PDF

Use `POST /v1/documents/upload` in the interactive API docs, or run:

```powershell
curl.exe -F "file=@C:/path/to/document.pdf;type=application/pdf" http://127.0.0.1:8000/v1/documents/upload
```

To ingest a local file without starting the API:

```powershell
uv run python -m scripts.ingest C:/path/to/document.pdf
```

Direct invocation with `uv run python scripts/ingest.py ...` also works. Both
entry points use the same extraction, chunking, and persistence service.
Restart the API with `uv run python run.py` after changing its source; the local
launcher does not automatically reload code.

The upload response contains `document_id`, `filename`, `page_count`,
`chunk_count`, `status` (`ready`), and `already_existed`.

| Result | HTTP status | Behavior |
| --- | --- | --- |
| New PDF indexed | 201 | Returns the new document and chunk count. |
| Identical bytes already ready | 200 | Returns the original ID and filename without repeating inference. |
| Failed PDF uploaded again | 200 on success | Retries using the original ID and filename; `already_existed` is true. |
| Identical PDF currently pending | 409 | Includes `Retry-After: 5`; retry after processing finishes. |
| File exceeds 10 MiB | 413 | Rejects the upload. |
| Content type is not `application/pdf` | 415 | Rejects the upload. |
| Invalid filename/PDF, unsupported PDF features, or content limit | 422 | Explains the rejection. |
| Storage, tokenizer, or embedding failure | 503 | Retry the same file after the dependency recovers. |

### Limits and storage behavior

- Maximum 100 pages, 2,000,000 extracted characters, and 1,000 chunks per PDF.
  Exceeding a limit produces an error; documents are never silently truncated.
- Password-protected PDFs and PDFs with no searchable text are rejected. OCR is
  not implemented. Blank or image-only pages in a PDF with searchable text are
  skipped while retaining the original total page count and page numbering.
- Chunks contain up to 350 tokens with 40-token overlap within each page. Chunk
  indexes are zero-based across the document; page numbers are one-based.
- Inference uses batches of 32. Internal batches are validated, and database
  writes use at most 256 chunks per batch, all within one final transaction.
- Valid PDFs are claimed as `pending`. Tokenization and inference run outside
  database transactions. Success commits all chunks and `ready` together;
  processing failures become `failed` with no chunks. Failed uploads can retry.
- SHA-256 identifies identical file bytes, including concurrent uploads. The
  original PDF bytes are not retained; metadata, text, and embeddings are stored.
- Cancellation during processing attempts to mark the document `failed`. A hard
  process kill or a database outage during cleanup can leave a `pending` record.
  Once no worker owns that upload, an operator must mark it `failed` before
  retrying. Automatic job recovery is not part of this synchronous upload service.

## Automated checks

Install the locked dependencies, including the default `dev` group:

```powershell
uv sync --locked
uv run python -W error::DeprecationWarning -m unittest discover -s tests -t . -v
```

The default run needs neither PostgreSQL nor model downloads. Database tests are
opt-in and create/drop isolated `ingestion_test_*` schemas in the configured
database; the database user needs permission to create schemas.

```powershell
$env:RUN_DB_TESTS = "1"
uv run python -W error::DeprecationWarning -m unittest tests.test_ingestion -v
```

For the complete suite with real BGE tokenization, inference, and persistence:

```powershell
$env:RUN_DB_TESTS = "1"
$env:RUN_MODEL_TESTS = "1"
uv run python -W error::DeprecationWarning -m unittest discover -s tests -t . -v
```

The model check may download assets on its first run. Tests cover multipage
uploads, duplicates and concurrent claims, failed retries, cancellation, invalid
PDFs, vector validation, and rollback after a later chunk-write batch fails.

## Next milestone

Implement vector similarity retrieval over `ready` documents: embed a question,
find the closest chunks, and return text with document and page references.
