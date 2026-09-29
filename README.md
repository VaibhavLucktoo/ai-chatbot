# AI Chatbot

A FastAPI backend for answering questions from documents. PDF ingestion includes
page-aware extraction, token-aware chunking, FastEmbed embeddings, PostgreSQL
persistence, duplicate detection, and retries. Vector retrieval and the RAG chat
endpoint return answers with document and page references.

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

### Configure the language model

The example configuration runs Llama locally through Ollama, with no paid API
account or API key. Questions and retrieved passages are sent to the local
Ollama server using the existing HTTPX client.

Install [Ollama for Windows](https://docs.ollama.com/windows), or use:

```powershell
winget install --id Ollama.Ollama --exact --source winget
```

Start Ollama and open a new terminal so the `ollama` command is on PATH. Download
the model:

```powershell
ollama pull llama3.2:1b-instruct-q4_K_M
ollama list
```

In `.env`, use:

```dotenv
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=llama3.2:1b-instruct-q4_K_M
LLM_API_KEY=
```

Leave `LLM_API_KEY` empty for local Ollama. The quantized
[Llama 3.2 1B model](https://ollama.com/library/llama3.2:1b-instruct-q4_K_M)
is about 808 MB to download; inference needs additional memory. It is a small
starting model for testing the RAG workflow. Evaluate answer quality on your
documents before relying on it. Close unused applications on machines with
limited RAM. With more available memory, pull `llama3.2:3b` and update `LLM_MODEL`.

Keep Ollama running while using chat. If its background application is not
running, start `ollama serve` in a separate terminal. The API has a 30-second
generation deadline; model loading and longer CPU-only answers can exceed it.
After downloading, you can load the model before testing chat:

```powershell
ollama run llama3.2:1b-instruct-q4_K_M "Reply with one word: Ready"
```

Restart the API after changing configuration. Shell environment variables override
`.env`. Health/readiness checks verify the API and database, not LLM credentials.

For hosted Llama, Together supports `LLM_BASE_URL=https://api.together.ai/v1`
and `LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo`, with a Together key in
`LLM_API_KEY` and account credits. Check its current
[model availability and pricing](https://docs.together.ai/docs/serverless/models).
Hosted generation sends the question and retrieved document passages to that
provider. Embeddings and document storage remain local.
For Groq, check [its deprecation notices](https://console.groq.com/docs/deprecations):
Llama 3.1 8B and Llama 3.3 70B were retired for free/developer accounts on
August 16, 2026, and remain available only under qualifying enterprise contracts.

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
uv run pytest -W error::DeprecationWarning tests -v
```

The default run needs neither PostgreSQL nor model downloads. Database tests are
opt-in and create/drop isolated `ingestion_test_*` schemas in the configured
database; the database user needs permission to create schemas.

To run only the RAG chat endpoint integration tests:

```powershell
uv run pytest tests/test_rag.py -v
```

These three tests use the real API route and RAG service with mocked retrieval,
embedding initialization, and LLM responses. They cover answers and source
metadata, empty-context fallback, and HTTP 504 on an LLM timeout. Prompt and
service unit tests are in `tests/test_rag_service.py`.

```powershell
$env:RUN_DB_TESTS = "1"
uv run python -W error::DeprecationWarning -m unittest tests.test_ingestion -v
```

For the complete suite with real BGE tokenization, inference, and persistence:

```powershell
$env:RUN_DB_TESTS = "1"
$env:RUN_MODEL_TESTS = "1"
uv run pytest -W error::DeprecationWarning tests -v
```

The model check may download assets on its first run. Tests cover multipage
uploads, duplicates and concurrent claims, failed retries, cancellation, invalid
PDFs, vector validation, and rollback after a later chunk-write batch fails.

## Try document chat

After configuring the LLM and uploading a PDF, use `POST /v1/chat` in the API docs
with a question about the document and a `top_k` value between 1 and 20. The
response contains `answer` and `sources`; each source includes the document ID,
chunk ID, filename, and page number. Empty retrieval returns an insufficient-context
answer with an empty source list without calling the LLM.
