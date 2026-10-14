# Local backend contract for frontend development

Run backend commands from the repository's `Backend` directory. Shared caches and backups remain under the repository-root `.cache`.

The supported backend runs at `http://127.0.0.1:8000` using `uv run python run.py`.
Serve the frontend from this same origin, or use a development server that proxies
API requests and rewrites Host/Origin to the backend origin. Cross-origin requests
and remote clients are rejected. Document selection is a search filter; the
workspace supports one trusted local operator.

OpenAPI is available at `/openapi.json`, with interactive documentation at `/docs`.
JSON request schemas reject undeclared fields.

| Action | Endpoint | Successful response |
| --- | --- | --- |
| Check liveness | `GET /v1/health` | 200 |
| Check DB/schema/embedding readiness | `GET /v1/ready` | 200; 503 when unavailable |
| List documents | `GET /v1/documents?limit=25&offset=0` | `items`, `total`, `limit`, `offset` |
| Filter documents | Add `status=ready` and/or `active=true` | Filters apply to both items and total |
| Inspect a document | `GET /v1/documents/{id}` | Metadata, active flag, chunk count, source availability |
| Download original PDF | `GET /v1/documents/{id}/source` | PDF attachment; 409 for legacy missing source |
| Inspect a chat citation | `GET /v1/documents/{id}/chunks/{chunk_id}` | Original passage and page metadata; 404 for mismatched IDs |
| Upload synchronously | `POST /v1/documents/upload` | Multipart `file`; 201 new, 200 duplicate/retry |
| Submit durable ingestion | `POST /v1/documents/jobs` | Multipart `file`; 202 pending, 200 already ready; `Location` header |
| Poll ingestion | `GET /v1/documents/jobs/{id}` | `document_id`, `filename`, `status` |
| Search passages | `POST /v1/documents/search` | `query`, `top_k`, `matches`, `results` |
| Ask a question | `POST /v1/chat` | Answer/sources or document clarification |
| Retire/reactivate | `PATCH /v1/documents/{id}/activation` | JSON `{"active": false}` or true; 204 |
| Delete document and chunks | `DELETE /v1/documents/{id}` | 204; ask for confirmation in the frontend |

Document lists include pending, failed, and retired documents by default. Use
`status=ready&active=true` for the chat picker. Pagination limit is 1–50; offset
is nonnegative. Metadata contains `id`, `filename`, `page_count`, `status`,
`created_at`, `active`, `chunk_count`, and `source_available`. Pending metadata
is provisional until ingestion completes. No retained bytes or embeddings are
included in metadata responses.

Chat requests use `question`, optional `top_k` (1–20, default 5), optional
`document_ids` (1–20 UUIDs), and optional `conversation_id` (UUID). Search uses
`query` instead of `question`. Document questions without IDs search all active
ready documents. Follow-ups without IDs inherit the previous answer's document
scope. Explicit IDs always take precedence. Unknown IDs do not broaden the search.

Chat returns `answer` and `sources`. Each source contains `document_id`,
`chunk_id`, `filename`, and one-based `page_number`. Citation numbers index the
returned source array. An insufficient-context answer has no sources. The
source passage can be fetched using its document and chunk IDs even when the
original PDF has not been retained. A clarification response contains
`status: clarification_required`, `question`,
`original_question`, `top_k`, and `documents`. Resend `original_question` and
`top_k` with the selected document IDs and the same conversation credentials.

Memory is opt-in: generate a random conversation UUID and a private 64-character
hexadecimal key, send the UUID in the body and the key in `X-Conversation-Key` on
every turn. Never display or log the key. Missing/wrong keys return 403; overlapping
turns return 409 with `Retry-After: 2`. Omitting the ID keeps requests stateless.
The connected UI retains credentials and a bounded transcript in session storage;
Clear chat generates fresh credentials. Memory expires after 24 hours of inactivity
by default. See [conversation implementation](conversational-upgrade-2026-10-12.md).

Use durable jobs for the upload progress flow. Poll until `ready` or `failed`;
pending means processing or recovery, not a percentage. Retry a failed job by
resubmitting the original PDF. A 202 response only acknowledges durable storage;
PDF extraction can still fail later.

Errors use `detail`. Display errors and permit retry without discarding the
question or selected IDs. Honor `Retry-After` for 429 or pending duplicate 409.
Compound questions make a second model call to review the draft. Allow the full
configured chat deadline in the frontend; a review failure returns an error.
422 means invalid input, 502 means invalid model output, 503 means dependency
unavailability, and 504 means generation exceeded its deadline. Never render
answers, filenames, or passages as raw HTML. Reference validation does not prove
factual accuracy; present sources so the user can inspect them.

The `/v1/admin/*` diagnostics require the session token embedded in `/admin`.
Use the document catalog and normal chat endpoints for chat/documents; do not
depend on private diagnostic fields or a saved admin token. The local Analytics
tab obtains the same ephemeral token through `GET /v1/admin/session`, keeps it
in memory and sends it in `X-Admin-Token` to `GET /v1/admin/metrics`. Parameters:
`hours` (1–720, default 24), optional exact `model`, `offset` (default 0), `limit`
(1–50, default 25). Session bootstrap is loopback/same-origin only; this is not
public administrator authentication. Analytics errors use 403/422/503.
See [the metrics contract](model-analytics-2026-10-12.md).
