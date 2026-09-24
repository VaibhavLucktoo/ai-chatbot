# End-of-Day Developer Build Log

**Date:** 2026-09-24 (Asia/Kolkata)

**Project:** AI Chatbot — document ingestion and retrieval foundation

This log describes the working tree relative to the initial scaffold commit, `31f2855` (2026-09-23). Created/Modified statuses below come from that comparison, including untracked source files. Implementation was reviewed for this log; running containers, applied database revisions, and successful model inference were not verified during this documentation pass.

## 1. Executive Summary

Today's work established the infrastructure and contracts for a document-backed chatbot:

- **Docker database setup:** Configured PostgreSQL 16 with pgvector through Docker Compose, persistent storage, a database health check, and an initialization script enabling the `vector` extension. PostgreSQL is exposed locally on port `5433`.
- **Async SQLAlchemy 2.0 layer:** Added a Psycopg 3 async engine with bounded connection pooling, transaction handling, timeouts, readiness checks, and shutdown cleanup. FastAPI owns the database lifecycle and refuses startup if database connectivity or the vector extension is unavailable.
- **FastEmbed strategy layer:** Defined an embedding abstraction and a cached provider factory. The initial implementation uses `BAAI/bge-small-en-v1.5`, returns normalized 384-dimensional vectors, and runs model loading and inference outside the API event loop.
- **Database schema:** Defined documents and document chunks using typed SQLAlchemy mappings, UUID identifiers, content-hash uniqueness, page and position validation, cascading deletion, and an explicit embedding-space contract.
- **Alembic migrations:** Added migration configuration and the initial reversible schema migration, including explicit rendering of pgvector types during autogeneration.
- **API foundation:** Implemented `/v1/health` and `/v1/ready`, strict document schemas, and a Windows-compatible server entry point.

The project now has the foundation for ingestion. PDF extraction, token-aware chunking, upload orchestration, vector persistence services, retrieval, and chat remain unfinished. Docker Compose currently runs the database; the existing `Dockerfile` is empty, so application containerization is not complete.

## 2. Files Created & Modified

This inventory includes every changed or new non-ignored file at review time, plus this log. Unchanged scaffold files and ignored local configuration/cache files are excluded.

| File path | Status | Specific role |
| --- | --- | --- |
| `.env.example` | Modified | Documents application and FastEmbed environment settings; database variables still need to be added to the example. |
| `.gitignore` | Modified | Excludes `.cache/`, including downloaded embedding model assets. |
| `compose.yaml` | Modified | Defines the pgvector/PostgreSQL service, localhost port mapping, persistent volume, initialization mount, and health check. |
| `pyproject.toml` | Modified | Adds Alembic, FastEmbed, pgvector, Psycopg binary support, and SQLAlchemy asyncio dependencies. |
| `uv.lock` | Modified | Records the resolved dependency graph for reproducible environments. |
| `run.py` | Created | Starts Uvicorn with an explicitly owned event loop and Windows selector-loop handling. |
| `app/core/config.py` | Modified | Defines cached, validated settings for application identity, database credentials/pooling/timeouts, and embeddings. |
| `app/main.py` | Modified | Creates FastAPI, mounts `/v1` routes, checks database readiness at startup, and disposes the engine at shutdown. |
| `app/api/v1/router.py` | Modified | Registers health and readiness routers. |
| `app/api/v1/health.py` | Modified | Implements the lightweight liveness endpoint. |
| `app/api/v1/readiness.py` | Created | Checks database readiness and returns HTTP 503 when unavailable. |
| `app/schemas/health.py` | Modified | Defines the typed health response. |
| `app/schemas/readiness.py` | Created | Defines `ready` / `not_ready` response states. |
| `app/schemas/documents.py` | Created | Defines strict upload metadata, document/chunk responses, and validated internal ingestion batches. |
| `app/providers/base.py` | Created | Defines the abstract embedding interface, vector alias, dimensions, and embedding-space identity. |
| `app/providers/embeddings.py` | Modified | Selects and caches the provider; validates configured model and dimensions. |
| `app/providers/fastembed_provider.py` | Created | Implements lazy FastEmbed loading, threaded inference, locking, vector validation, and L2 normalization. |
| `app/providers/documents.py` | Created | Empty placeholder for future document-provider work. |
| `app/providers/models.py` | Created | Empty placeholder; no model-provider behavior is implemented here yet. |
| `app/storage/db.py` | Created | Encapsulates the async engine, pooled connections, transaction context, readiness query, and disposal. |
| `app/storage/models.py` | Created | Defines declarative metadata, document/chunk tables, and storage constraints. |
| `infra/postgres/init/001-vector.sql` | Created | Enables the PostgreSQL `vector` extension during initial database creation. |
| `alembic.ini` | Created | Configures migration paths and logging; the runtime database URL is supplied by `migrations/env.py`. |
| `migrations/README` | Created | Contains the generated single-database migration-environment description. |
| `migrations/env.py` | Created | Uses application settings and ORM metadata for online/offline migrations and custom vector-type rendering. |
| `migrations/script.py.mako` | Created | Provides the template for future migration revisions. |
| `migrations/versions/7f7483ec3680_create_documents_and_document_chunks.py` | Created | Creates both tables and their constraints; downgrade drops chunks before documents. |
| `NOTES.md` | Created | Records the day's implementation, design decisions, current boundaries, and next milestone. |

## 3. Key Technical Decisions & Concepts

### Windows SelectorEventLoop for Psycopg 3

`run.py` selects `asyncio.SelectorEventLoop()` on Windows and supplies it to `asyncio.Runner` through a loop factory. This addresses Psycopg 3 async compatibility with Windows event loops: the application explicitly uses a selector loop instead of relying on the Windows default proactor loop. Other platforms use `asyncio.new_event_loop()`.

The launcher calls `server.serve()` inside that runner, retaining control of loop creation. Use `uv run python run.py` for local startup so this setup is applied.

### Async database ownership and transactions

FastAPI's lifespan creates one `Database` instance per application process and stores it on `app.state`. SQLAlchemy manages the async connection pool; the implementation uses `AsyncConnection`, not an ORM `AsyncSession` layer.

Defaults allow five pooled connections with no overflow, a five-second pool wait, a five-second connection timeout, and a five-second statement timeout. `pool_pre_ping` checks connections before reuse. `Database.transaction()` commits on success and rolls back on failure through `engine.begin()`.

Credentials use `SecretStr`, URLs are constructed with `URL.create`, and SQL parameters are hidden from engine logging. Readiness failures log exception types without connection strings or query inputs.

### Strategy Pattern for embeddings

`BaseEmbeddingProvider` separates callers from a particular embedding implementation through `embed_documents()`, `embed_query()`, `dimensions`, and `space_id`. `get_embedding_provider()` chooses the strategy from settings and caches the resulting instance. Only FastEmbed is currently supported; unsupported providers, models, or dimensions fail explicitly.

The FastEmbed adapter lazily loads the model into `.cache/fastembed`, offloads work with `asyncio.to_thread`, and serializes model initialization and inference with a threading lock. It uses separate passage/query embedding methods, rejects blank input, validates vector count and dimensions, rejects non-finite and zero-magnitude vectors, and applies L2 normalization. Thread offloading keeps inference from blocking FastAPI's event loop; it does not imply unlimited parallel inference.

### `vector(384)` and database check constraints

The schema fixes embeddings at `VECTOR(384)`. The pgvector column type enforces dimensionality; it is not a separate SQL `CHECK` constraint. A dedicated check constrains `embedding_space` to `fastembed:bge-small-en-v1.5:384:l2:v1`, preventing differently labeled embedding spaces from being mixed in the same table. The label records the intended model and preprocessing contract; it does not independently prove how a vector was generated.

Additional checks require positive document page counts, valid document statuses (`pending`, `ready`, `failed`), nonnegative chunk indexes, positive page numbers, and nonblank chunk content. A unique `(document_id, chunk_index)` constraint prevents duplicate positions. A foreign key with `ON DELETE CASCADE` removes chunks when their parent document is deleted.

The internal Pydantic ingestion schema additionally limits each batch to 1–256 chunks, rejects repeated chunk indexes within a batch, and checks page numbers against the supplied document page count. These cross-field validations are application contracts, not equivalent database checks. Changing embedding dimensions or space requires a deliberate schema/data migration rather than an environment-variable-only change.

### SHA-256 deduplication

`documents.content_sha256` is a required, unique 64-character field intended to store the hexadecimal SHA-256 digest of uploaded file bytes. This provides the database boundary for identifying identical files even when their filenames differ, including concurrent attempts to store the same hash.

Hash calculation and duplicate-upload behavior are still to be implemented. The upload service must calculate the digest, check for an existing document, and handle uniqueness races. The schema does not validate hexadecimal formatting, and byte-level deduplication does not identify semantically equivalent PDFs with different binary contents.

### Alembic owns schema evolution

Revision `7f7483ec3680` is the initial migration and has no parent. Alembic compares `Base.metadata` with the database using `compare_type=True`; a rendering hook emits explicit `VECTOR` imports for generated revisions.

Online migrations use a synchronous Psycopg engine with `NullPool`, a connection timeout, a five-second lock timeout, and guaranteed engine disposal. This migration process is separate from the async request path. Offline mode can emit SQL without opening a database connection.

The vector extension is provisioned by the Docker initialization script, not this migration. That script runs when PostgreSQL initializes a fresh data directory; an existing volume must already have the extension or have it enabled separately. Application startup does not automatically apply migrations.

## 4. System Architecture State

```text
Local launcher: run.py -> asyncio.Runner -> Uvicorn -> FastAPI
                                                       |
                                      lifespan / app.state.database
                                                       |
                                      SQLAlchemy 2.0 async pool
                                                       |
                                           Psycopg 3 async driver
                                                       |
                                 localhost:5433 -> PostgreSQL + pgvector

Embedding component (implemented; ingestion wiring pending):
get_embedding_provider() -> BaseEmbeddingProvider -> FastEmbedProvider
                         -> worker thread -> normalized 384D vectors

Schema management (separate process):
Alembic -> synchronous Psycopg connection -> PostgreSQL tables
```

- `GET /v1/health` reports that the service is alive.
- `GET /v1/ready` checks database connectivity and the presence of the vector extension, returning 200 or 503. It does not verify migration revision, table availability, or embedding-model readiness.
- Docker Compose uses `pgvector/pgvector:0.8.6-pg16-trixie`, a named `postgres_data` volume, and a read-only initialization-script mount.
- Document and chunk tables are defined in source and migration code. Applying the migration is a separate operational step, not confirmed by this log.
- The provider and schema contracts exist, but no upload route currently connects parsing, chunking, embedding, and persistence. Ingestion and vector-store service files remain empty scaffolds, as do the existing retrieval/chat test files. No vector similarity index is defined yet.

## 5. Starting Point for Tomorrow

**Next milestone:** Accept a PDF through `POST /v1/documents/upload`, extract page-aware text, generate token-aware chunks and embeddings, persist the result, and return document metadata.

- [ ] Complete `.env.example` with required database settings (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) and the local host/port configuration. Ensure local settings match Compose.
- [ ] Start PostgreSQL with `docker compose up -d db`, confirm the vector extension exists, apply `uv run alembic upgrade head`, and inspect `uv run alembic current`.
- [ ] Start the API using `uv run python run.py`; verify `/v1/health` and `/v1/ready`.
- [ ] Select and add PDF parsing and multipart-upload dependencies. Implement extraction that preserves one-based page numbers and determines page count. Define handling for malformed, encrypted, empty, and scanned/image-only PDFs.
- [ ] Implement token-aware chunking using the embedding model's tokenizer and supported input budget. Choose chunk size and overlap, preserve source pages, skip blank text, and assign stable zero-based indexes across the document. Respect the internal 256-chunk batch limit without silently truncating documents.
- [ ] Compute SHA-256 from uploaded bytes and define repeat-upload behavior, including retries of failed documents and concurrent duplicate requests.
- [ ] Implement ingestion orchestration and database writes using the existing provider and transaction abstraction. Keep parsing/inference outside long-held database transactions. Persist the provider's `space_id` with every embedding and define `pending` -> `ready` / `failed` behavior.
- [ ] Add and register `/v1/documents/upload`, enforce file limits and PDF validation, and return the existing `DocumentResponse` contract with documented response/error statuses. Filename and content-type metadata validation alone is insufficient to validate uploaded bytes.
- [ ] Verify a small multipage PDF end to end: page attribution, chunk ordering, nonempty content, 384-dimensional embeddings, persisted rows, and final document status. Cover duplicate uploads, invalid PDFs, and failures without leaving a partially completed document marked `ready`.

**Milestone acceptance:** A valid PDF can be uploaded and stored with traceable chunks and compatible embeddings; repeat uploads follow a defined deduplication policy; failures produce consistent responses and database state. Retrieval and chat integration follow this ingestion milestone.
