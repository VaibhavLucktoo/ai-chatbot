# Per-assistant model configuration

Stage 1 extends the existing trusted local workspace with Groq and Google Gemini
connections and assistants. It keeps the current FastAPI, LangGraph, PostgreSQL,
FastEmbed, hybrid retrieval, grounding prompts, validation, and metrics writer.

## Setup and use

From `Backend`, update dependencies and apply the additive migration before
restarting the API:

```powershell
$env:UV_PROJECT_ENVIRONMENT = (Resolve-Path ../.venv).Path
uv sync --locked
uv run alembic upgrade head
uv run python run.py
```

Revision `f85d64add7bf` follows `e74b53fcc6ae`. It creates `provider_connections`,
`assistants`, and `assistant_documents`, and adds a nullable assistant namespace
to conversation rows. Existing documents, vectors, metrics, and legacy histories
are preserved. Startup/readiness checks require the new schema. No provider key
is copied from `.env` into the database.

In the frontend, open **Models** for provider access, then **Assistants** for assignments:

1. In Models, add a named provider connection, choose Groq or Gemini, and enter its API key.
2. In Assistants, create an assistant and select that connection.
3. Use **Load models** to obtain the provider's advertised model IDs. Model
   availability and text-completion compatibility are confirmed by the test,
   not guaranteed by discovery alone.
4. Choose a model, assign documents, and optionally adjust generation settings.
5. **Test selected model**, then **Save assistant**. A test makes a small provider
   generation request and can consume tokens or incur a charge.
6. In Chat, choose the assistant. **Workspace default** uses the existing `.env`
   model and workspace documents. Each choice keeps a separate tab-local transcript,
   private conversation key, and document selection.

Editing a connection supports key replacement and disabling. Blank replacement
keeps the saved key. Provider identity is immutable; add a new connection to change
provider. Editing an assistant changes its model, connection, document assignments,
generation settings, or enabled state. New requests load the committed settings
without restarting the backend. In-flight requests retain their configuration snapshot.

## Models and Assistants lifecycle

Models has its own sidebar page for connection creation, safe metadata, referenced
assistant names, key replacement, disabling, model discovery and connection tests.
Assistants has a separate page for model/document assignments. Changing model or
generation settings requires a UI connection test; name, description, document and
active-status edits can be saved directly without another provider request.

Permanent deletion requires an accessible confirmation dialog. Deleting an
assistant removes its settings, document assignments and server conversation rows.
PDFs, chunks, provider connections and historical metrics are retained. The current
browser tab forgets that assistant's saved transcript and selection; if selected,
Chat returns to workspace default. Other tabs can retain already-displayed text,
and backups remain subject to their existing retention policy.

Deleting a connection removes its encrypted credential row. The database and API
block deletion while any assistant, including a disabled assistant, references it.
Reassign or delete referencing assistants first. This operation does not revoke the
API key at the provider. The shared encryption master key is retained for other keys.

Assistant deletion returns 409 while an unexpired conversation lease is active.
Stateless assistant requests also create a short, empty lease and remove it on
completion; they do not retain conversation turns. Claims take a brief shared lock
on the assistant row, while deletion takes an exclusive lock, so a new turn cannot
recreate history after deletion. All locks/transactions are released before model
generation. Failed stateless cleanup leaves a bounded lease until expiry.

These operations use the existing schema; no additional migration is required.

## Credentials and local access

Connection responses never contain plaintext or encrypted API keys. Admin APIs
require the existing loopback/same-origin boundary and `X-Admin-Token`. Write-schema
validation errors omit raw input. The frontend sends keys only to the backend and
clears the input after saving; it does not persist provider keys in browser storage.
Provider URLs are backend-owned presets, never supplied by the browser.

Fernet authenticated encryption binds credentials to the connection UUID and
provider. The master key is kept outside PostgreSQL. Optionally supply
`ASSISTANT_ENCRYPTION_KEY`; otherwise the first connection save creates
`.cache/assistant-secrets/connection.key` at the repository root. That ignored file
must remain private to the operator. On Windows it inherits directory access controls;
restrict those controls to the operator account. Back up the master key separately
from the database. A missing key during decryption fails explicitly rather than
creating a replacement or selecting another provider. To recover, restore the key
or replace each affected connection's API key.

This is one trusted local administrator, not separate authenticated admin accounts
or public tenant isolation. The existing workspace document endpoints remain
available to that local operator. Assistant scope restricts chat retrieval and
document-choice responses; it does not replace future document authorization.

## Runtime behavior

`ChatRequest.assistant_id` is optional. Requests without it retain the old API
behavior. Selected assistants must be enabled and have an enabled connection.
Missing/disabled assistants return 404, selected unassigned documents return 403,
and unusable stored credentials return 503. Provider failures preserve explicit
quota, timeout, connection, and invalid-response handling. There is no silent
provider, credential, or document-scope fallback.

A short repeatable-read transaction loads the assistant, connection revision,
and document assignments. Credential decryption happens after releasing that
connection. The immutable model snapshot is request-scoped and used by every
follow-up, answer, and review call. The graph receives the assigned-document
snapshot separately from the user's optional <=20-document selection. An empty
assignment never becomes workspace-wide retrieval. Active/ready filtering still
applies in SQL, including after retirement or deletion.

Conversation UUIDs are bound to their assistant namespace. Reusing an existing
conversation/key under another assistant, or as a legacy chat, is rejected. The
frontend disables switching while a turn is in flight and restores each assistant's
own bounded transcript when switching back.

Assistant context/output budgets apply to both transport guards and RAG context
selection. Compound-question context selection reserves additional space for the
review draft and instructions. Guards still reject oversized or incomplete provider
responses; model context settings must match the selected model's actual capacity.

## API

- `GET /v1/assistants`: enabled assistants with enabled connections; safe configuration only.
- `GET /v1/assistants/{id}/documents`: paginated active, ready assigned-document metadata.
- `GET /v1/admin/providers`: supported provider presets.
- `GET/POST /v1/admin/connections`: list safe connection metadata / save encrypted credentials.
- `PUT /v1/admin/connections/{id}`: rename, enable/disable, or replace a key.
- `DELETE /v1/admin/connections/{id}`: remove an unused connection; 204, 404 or 409.
- `GET /v1/admin/connections/{id}/models`: model discovery using saved credentials.
- `POST /v1/admin/connections/models`: model discovery using unsaved credentials.
- `POST /v1/admin/connections/test`: test a saved connection or unsaved provider/key with model settings.
- `GET/POST /v1/admin/assistants`: list / create configuration.
- `PUT /v1/admin/assistants/{id}`: replace configuration and increment revision.
- `DELETE /v1/admin/assistants/{id}`: remove settings, assignments and history; 204, 404 or 409.

Only admin endpoints can configure model connections or document assignments.
Chat callers identify an assistant; they cannot supply model credentials or endpoints.

## Verification and subsequent stages

New tests cover credential binding/tampering, private validation failures, admin
protection, provider error mapping, concurrent model/key isolation, actual filtered
semantic/hybrid retrieval, empty assignments, conversation namespaces, frontend
configuration, connection-test gating, and independent browser histories.
PostgreSQL tests create and remove isolated test schemas. Provider calls are mocked.

Verified on 13 October 2026:

- Backend regression suite: **224 passed, 1 skipped, 353 subtests passed**, with
  `RUN_DB_TESTS=1`, `RUN_MODEL_TESTS=1`, `RUN_POLICY_TESTS=0`, and `HF_HUB_OFFLINE=1`.
  The skipped suite is the optional real-provider policy evaluation. Cached
  real embeddings and isolated PostgreSQL schemas were exercised.
- Frontend: **31 passed** using `npm test -- --maxWorkers=1`; TypeScript check and
  production build passed. The bounded worker count avoids worker-startup timeouts
  observed in this Windows verification environment.
- Dependency lockfile updated; cryptography and its two dependencies installed.
- Local migration applied: **f85d64add7bf (head)**. `alembic check` reports no new
  upgrade operations.
- Read-only ASGI checks against the actual local database returned 200 for health,
  readiness, assistant selection, and authenticated provider/connection/assistant
  reads. Anonymous connection administration returned 403. These checks warmed
  cached embeddings without starting ingestion recovery or making provider calls.
- The browser connection exposed no browser surface. Rendered visual review and
  live provider generation remain unverified; the admin's connection-test button
  verifies actual credentials/model access when used.

Lifecycle follow-up verification on 13 October 2026:

- Full backend suite: **227 passed, 1 skipped, 353 subtests passed**, with isolated
  PostgreSQL and cached embeddings. Live-provider policy tests remained disabled.
- Full frontend suite: **35 passed**. The final keyboard/focus adjustment was
  additionally verified by all **7 assistant-settings tests**, covering Cancel,
  Escape, confirmation, protected connections, separate pages and direct disabling.
- TypeScript and the final production build passed. Alembic reports no pending
  upgrade operations; this follow-up requires no schema change.
- No real operator configuration was deleted during verification. Deletion tests
  use isolated schemas or browser fixtures and verify preservation of documents/chunks.
- Rendered browser review remains unavailable in this session.

Stage 2 implements configuration caching and assistant-level Analytics; see
[cache, migration and Analytics behavior](assistant-caching-analytics.md). Existing
model telemetry continues using the current bounded background writer. Stage 3 covers
measured indexing/concurrency changes and streaming design. This stage does not
introduce Redis, Celery, ANN indexes, raw token streaming, public accounts, or
answer-quality scores.
