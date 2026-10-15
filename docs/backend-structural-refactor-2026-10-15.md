# Backend structural refactor ? 15 October 2026

All four phases are implemented. Public and local endpoint paths, methods, parameters, request schemas, operation IDs and documented status codes match the saved pre-refactor contract. Existing typed schema definitions are unchanged. The planned OpenAPI changes are lowercasing the health tag and adding schemas to previously untyped JSON success responses.

## Final structure

- `app/api/dependencies.py`: the original request-scoped `get_db_session`, with unchanged function-scope cleanup and error mapping.
- `app/services/chat_service.py`: the original `run_chat` orchestration, cancellation behavior and error mapping. Existing diagnostic logger names are retained.
- `app/api/common/routes.py`: shared sanitized route errors, with assistant/widget subclasses selecting compatible storage-error messages. The widget's existing wording is intentionally retained.
- `app/services/configuration_errors.py`: shared configuration exceptions. Existing assistant-module imports remain aliases to the same exception classes.
- `app/services/provider_service.py`: connection lifecycle, credential loading, model discovery and connection tests using the existing app-owned HTTP client and semaphore.
- `app/api/v1/widget_admin.py`, `widget_visitor.py`, `widget_assets.py`: focused HTTP surfaces. The aggregator, local app and public gateway mount their existing router objects at the same prefixes. `widgets.py` is a compatibility re-export module.
- `app/storage/document_catalog.py`, `document_jobs.py`, `document_lifecycle.py`, `admin.py`: SQL moved out of routes without rewriting query expressions or changing transaction boundaries.
- `app/api/common/uploads.py`: shared bounded upload reads and envelope checks. Original helper imports are re-exported by the document endpoint module.
- `app/schemas/admin.py`, `providers.py`, `metrics.py`: response contracts. Existing job/activation schemas now live under document schemas, with compatibility re-exports.

No database-engine, pooling, concurrency, ingestion, retrieval or provider-transport settings were changed. No migration was required. Ruff is a locked development-only dependency; runtime package versions were not changed. Existing test assertions were retained, with mock lookup paths updated for relocated callables and small mechanical lint cleanup.

## Compatibility details

`app.api.v1.chat.get_db_session` and `app.api.v1.chat.run_chat` are direct aliases to the new functions, preserving dependency-override identity. Provider connection functions and the catalog query helper likewise retain deprecated aliases. Old widget routers and handler imports refer to the same objects as the focused modules. The previous Request-based `assistants.discover_models` signature is retained through a deprecated adapter to the client-based service.

Response regression tests verify the original `+00:00` timestamp representation, explicit null fields and exact passage whitespace. These tests compare encoded response bytes. The public gateway exposes exactly the same five method/path combinations and no administration routes. JavaScript/CSS assets remain raw responses; their existing documentation was preserved.

## Phase gates

| Phase | Exact pytest result |
|---|---|
| 1 | `248 passed, 1 skipped, 375 subtests passed in 125.33s (0:02:05)` |
| 2 | `248 passed, 1 skipped, 375 subtests passed in 196.83s (0:03:16)` |
| 3 | `248 passed, 1 skipped, 375 subtests passed in 124.42s (0:02:04)` |
| 4 | `255 passed, 1 skipped, 375 subtests passed in 111.55s (0:01:51)` |

The full suites enabled PostgreSQL integration and actual cached embedding tests using `RUN_DB_TESTS=1`, `RUN_MODEL_TESTS=1`, and `HF_HUB_OFFLINE=1`. Every phase passed before the next began. The single skip is the optional live-provider policy suite; hosted-provider answer quality is outside this structural verification.

## Final commands and exact output

Run these from `Backend`, using the shared root virtual environment or `uv run` after syncing the lockfile.

### OpenAPI and application imports

```powershell
..\.venv\Scripts\python.exe -B -m scripts.check_api_contract --output ../output/backend-refactor/openapi-after.json
```

```text
OpenAPI operations: 39
Unique operation IDs: 39
Duplicate operation IDs: 0
Paths, methods, parameters, request schemas, status codes and existing response schemas: unchanged
Tags: consistent
Application modules imported successfully: 80
```

The checker uses `tests/fixtures/api_contract_before_refactor.json` and verifies operation count/IDs, paths, methods, parameters, request bodies, statuses and existing component schemas. `--strict` additionally rejects the planned documentation changes; that mode passed in phases 1?3.

### Complete suite

```powershell
$env:RUN_DB_TESTS = "1"
$env:RUN_MODEL_TESTS = "1"
$env:HF_HUB_OFFLINE = "1"
..\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests -q
```

```text
255 passed, 1 skipped, 375 subtests passed in 111.55s (0:01:51)
```

### Requested focused checks

```powershell
..\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/test_widgets.py tests/test_production_controls.py -q
```

```text
16 passed, 22 subtests passed in 6.21s
```

These are 16 individual tests, rather than 16 suites.

### Lint

```powershell
..\.venv\Scripts\ruff.exe check .
```

```text
All checks passed!
```

The project explicitly enables Ruff correctness/import rules `E4`, `E7`, `E9`, and `F`, independent of user-wide style settings. No blanket unused-import suppression was added. Application import checks successfully load all 80 modules, and the complete suite covers their integration.

### Live startup and data

```text
Startup, embedding warmup, health, readiness, and admin checks passed.
No new upgrade operations detected.
Application table counts and content fingerprints: unchanged (10/10 tables)
Temporary test schemas remaining: 0
Migration revision: b07e75bee9d1
```

Startup verification uses the real application lifecycle, cached embedding warmup, database and HTTP handlers in process; it does not leave a server listening. `alembic check` detects no schema drift. The existing three documents, 137 vectors, settings, credentials, histories and metrics remained unchanged. PostgreSQL remains running.

## Evidence files

Exact phase logs, OpenAPI before/after JSON, lint/runtime/schema results, a read-only post-refactor database snapshot and `verification-summary.json` are under `output/backend-refactor/`. The database snapshot exports aggregate evidence, schema metadata and fingerprints, not document text or credentials.
