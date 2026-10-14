# Local workspace operations

Run backend commands from the repository's `Backend` directory. Shared caches and backups remain under the repository-root `.cache`.

This release supports one trusted local operator, English text PDFs, and
document questions and optional bounded conversational memory. Keep the API on
loopback with proxy headers disabled.
`APP_ENV=production` fails closed because user identity and per-document
authorization are not implemented. A reverse proxy on loopback does not supply
authorization and must not expose the service publicly.

## Start and migrate

Run `uv sync --locked`, `docker compose up -d db`, then
`uv run alembic upgrade head` before `uv run python run.py`.
The current schema revision is `e74b53fcc6ae`.
Startup checks the schema and warms the pinned embedding model. Readiness does
not contact the LLM. `EMBEDDING_WARMUP_ON_STARTUP=false` allows startup without
warmup, but readiness stays false. Set `RAG_CONTEXT_WINDOW_TOKENS` to the actual
served model's window, and reserve output with `RAG_OUTPUT_RESERVE_TOKENS`.
The byte-based token bound applies to byte-level tokenizers; validate another
provider's tokenizer before changing models.
Body reception stops after 60 seconds total or 15 seconds without a chunk.

Memory-enabled chat sends a conversation UUID and private `X-Conversation-Key`.
Only its hash is stored with the bounded history. Default retention is six complete
turns, 12,000 UTF-8 bytes, and 24 hours of inactivity. Requests prune up to 100 expired
sessions plus the requested expired session; expired rows can remain on disk until
another memory request performs cleanup. Backups also contain histories until their
own retention expires. Clear chat rotates browser credentials; it does not immediately
erase the old server history. This remains a trusted local workspace, without user
accounts or document authorization. See the [conversation report](conversational-upgrade-2026-10-12.md).

## Durable uploads and recovery

Submit multipart `file` to `POST /v1/documents/jobs`; a 202 response contains
`document_id` and a Location header. Poll `GET /v1/documents/jobs/{id}` until
`ready` or `failed`. The worker processes one retained source at a time. Invalid
PDFs become failed jobs. Resubmit a failed PDF or use
`uv run python -m scripts.recover_ingestion DOCUMENT_ID`.
`POST /v1/documents/upload` retains its synchronous response contract.

Original PDF bytes commit with queued work. Expired pending attempts recover
after a restart. Ownership tokens fence publication and cleanup. Sources from
before this migration remain NULL; re-upload those originals for recovery.
Failed dependency attempts require explicit retry rather than an infinite loop.
Automatic recovery stops after three interrupted attempts, and rejects sources
whose bytes no longer match the retained SHA-256 identity.
Admin document metadata records pages without searchable text so missing OCR
coverage is visible; blank pages and scanned pages are not distinguished.
Retire an obsolete ready document with
`PATCH /v1/documents/{id}/activation` and `{"active": false}`; retrieval and
clarification then exclude it. Reactivation uses `true`. `DELETE /v1/documents/{id}`
erases its retained source, metadata, and chunks. Backups retain deleted data
until their own expiration.

PDF parsing runs in a separate process with a deadline and memory ceiling
(Windows Job limit or POSIX resource limit). It cannot read arbitrary files
through the extraction API, but this is resource isolation, not an OS security
sandbox. Embedding inference uses a bounded single-thread executor and cannot
be forcibly interrupted once native inference has started.

## Backups and restore verification

`uv run python -m scripts.database_backup backup` creates a PostgreSQL custom
archive in `.cache/backups`, including sources and index metadata.
Copy successful backups to private encrypted storage outside this machine.
Run daily and retain 7 daily plus 4 weekly successful backups; monitor failed
runs. The script never overwrites an existing archive.

Restore with:

```text
uv run python -m scripts.database_backup restore .cache/backups/FILE.dump --database restore_drill
```

The target must be a new database named `restore_*`; existing databases are
never overwritten. Set `POSTGRES_DB` to the restored database in a separate
shell, check migration head, counts, retained SHA-256 hashes, ready-document
retrieval and a known answer before switching. Restore drills and recovery
objectives still require measured deployment evidence. Preserve the previous
application image and DB backup for rollback. Do not downgrade source-retention
columns without exporting their data.
`uv run python -m scripts.verify_local --restore-database restore_drill` checks
startup/readiness, restored schema, source identities and document/chunk counts
without calling the LLM.

## Containers and release checks

`docker build -t ai-chatbot:local .` builds from the lockfile as a non-root user.
On Linux, run with `--network host` so loopback access checks and the local DB
remain valid. Publish no container port through a proxy. Mount a private cache
at `/app/.cache` and provide environment variables with `--env-file .env`.
Docker Desktop's default bridge/port forwarding is not supported by this
loopback-only container configuration; use the native Windows launcher.
The Docker image does not run migrations automatically.

CI runs isolated PostgreSQL integration tests, migration checks, unit tests,
and an image build. Real-model and live-policy tests remain separate opt-in
release gates. Require corpus-specific answer support review, negative and
injection cases, citation precision, retrieval recall, and upload/chat load
measurements before relying on answers. A unit pass does not certify those gates.
Keep exact vector search until measured recall justifies an approximate index.

## Diagnostics and data handling

Requests log ID, method, status and duration without question or passage text.
The local admin shows private passages and raw answers to its local operator;
it does not persist traces. CLI traces contain private data. Their default
directory is `.cache/rag-traces`; files are created with owner-only POSIX mode.
On Windows, protect the workspace with the operator's filesystem ACL.
Run `uv run python -m scripts.clean_traces --days 7` daily. Explicit trace output
paths and evaluation traces need equivalent retention managed by their owner.
Hosted generation sends questions and selected passages to the configured
provider. Use a local provider for documents that must stay on this machine.

OCR, full-document summaries, multilingual retrieval and conversation memory
interrupt/resume are outside the supported scope. Bounded conversation memory is
supported as described above. Top-k answers must not be presented as complete
document summaries. Citation validation verifies references, not factual entailment.

## Model analytics

The launcher starts a bounded metrics writer and flushes on graceful shutdown.
Only metadata is stored in `chat_metrics` and `model_call_metrics`, never prompts,
responses, passages, credentials or visitor/session IDs. The Analytics tab uses
`/v1/admin/metrics` with the existing local admin token. Metrics survive restarts
after commit; queue overflow, storage failures or abrupt termination can lose
uncommitted events. The process-local collector reports dropped events and writer
health. Historical metrics currently have no automatic retention deletion and
are included in backups; plan retention before public-scale deployment.

`METRICS_QUEUE_CAPACITY=1000`, `METRICS_WRITE_TIMEOUT_SECONDS=2` and optional
`METRICS_MODEL_PRICES` configure collection. Cost estimates require verified model
input/output rates in USD per million tokens; leave the map empty when unknown.
Runtime gauges describe the responding process, while stored aggregates span
shared storage. The metrics endpoint has a ten-second read deadline. See
[implementation and verification](model-analytics-2026-10-12.md).
