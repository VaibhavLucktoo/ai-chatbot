# Database verification ? 15 October 2026

PostgreSQL was started and left running healthy at `127.0.0.1:5433` in the existing `postgres_db` container. No application schema migration or repair was needed. No application source files were changed.

## Live architecture and schema

- PostgreSQL 16.15; pgvector 0.8.6.
- All 10 application tables exist.
- Alembic current revision: `b07e75bee9d1 (head)`.
- `alembic check`: no new upgrade operations; no detected model/schema drift.
- Live column types, indexes, foreign keys, checks and relation sizes are captured in the audit JSON.
- An English full-text GIN index exists. No approximate vector index is defined.
- Application table and index storage totaled 1,507,328 bytes at the initial snapshot; this excludes PostgreSQL cluster overhead and other databases.

## Stored records

| Table | Rows |
|---|---:|
| documents | 3 |
| document_chunks | 137 |
| provider_connections | 1 |
| assistants | 1 |
| assistant_documents | 1 |
| chat_conversations | 5 |
| website_widgets | 1 |
| widget_sessions | 0 |
| chat_metrics | 44 |
| model_call_metrics | 39 |

All three documents are ready and active. All 137 vectors belong to `fastembed:bge-small-en-v1.5:384:l2:v1`, have 384 dimensions and are normalized within 0.00001. The observed vector norms range from 0.9999999702307723 to 1.0000000299410114.

The actual cached embedding model regenerated every vector from its stored chunk text. All 137 reproduced successfully; maximum cosine distance was 8.881784197001252e-16. This verifies text/vector consistency, not factual answer quality or original extraction fidelity for missing PDFs.

Integrity checks found zero orphan chunks, ready documents without chunks, chunks attached to unfinished documents, invalid page references, non-contiguous chunk positions, duplicate document hashes, malformed session-key hashes or dangling assistant conversations. At the snapshot there were no expired conversation/session rows awaiting cleanup. Maximum saved conversation history was six turns and 4,275 bytes of PostgreSQL JSON text.

## Confirmed data gaps

Only one of the three documents retains its original PDF and processing metadata. Its 224,968-byte PDF matches the stored SHA-256 hash. The other two retain searchable text and vectors, but their original PDF bytes and processing provenance are absent. Their PDF download, source-byte integrity and extraction provenance cannot be verified until the original files are supplied again. No originals were reconstructed or fabricated.

## Runtime and integration checks

- The saved provider credential decrypts with the existing master key; no credential values were exported.
- Local ASGI checks returned HTTP 200 for health, readiness, admin page, admin status, admin documents, admin metrics and document search. These exercise the actual application lifecycle and database; they do not leave an HTTP server listening.
- Actual stored-content retrieval returned five results with finite distances.
- Full backend test suite with `RUN_DB_TESTS=1`, `RUN_MODEL_TESTS=1` and offline cached model assets: **248 passed, 1 skipped, 375 subtests passed**, in 194.64 seconds.
- The skipped suite is the optional live-provider policy evaluation. Hosted generation and factual answer quality were not tested.
- All integration-test schemas were removed from the main database.

## Backup and preservation

A local custom-format backup was saved at `.cache/backups/database-audit-20261015-638b4c0a.dump` and restored into the separate database `restore_audit_20261015_638b4c0a`. All 10 public application table counts and content fingerprints match. Index definitions match and all restored constraints are validated. Two restored check expressions have equivalent PostgreSQL cast formatting rather than byte-identical SQL text.

The backup was taken while isolated integration tests were running, so the verification archive and restore database additionally contain one temporary fixture schema. They are retained as verification artifacts. No main application configuration was switched to the restored database. This is a local restore check, not an off-machine recovery drill. The external encryption master key is not included in the database dump and still needs its separate backup.

Before-and-after content fingerprints match for all 10 tables in the main database, including conversations, settings, credentials and metrics. Existing application rows were unchanged.

## Evidence

- `database-audit-2026-10-15-before.json`
- `database-audit-2026-10-15-after.json`
- `database-audit-2026-10-15-restored.json`
- `database-runtime-verification-2026-10-15.json`
- `database-verification-summary-2026-10-15.json`

Audit helpers are under `tmp/database_architecture_audit.py` and `tmp/database_runtime_verification.py`. They export aggregate evidence and hashes, not document text, questions, answers or credentials.
