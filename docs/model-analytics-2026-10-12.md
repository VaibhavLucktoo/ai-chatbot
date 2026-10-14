# Real model analytics — 12 October 2026

Step 1 adds actual administrator analytics to the existing local application.
Open `http://127.0.0.1:3000` and select **Analytics**. Chat, Documents and Status
continue to use their existing services. Original prototype files are retained;
the active analytics page does not use simulated metrics.

## What is measured

| Area | Measurements |
| --- | --- |
| Chat outcomes | Requests, HTTP success rate, cancellations, validation/access failures, capacity rejection, provider rate limits, timeouts, insufficient context, clarification and conversation replies |
| Request latency | Average, median and p95 HTTP lifecycle time; average graph time |
| Workflow | Average entered-node timings, intent counts, retrieval performed, result counts and returned source counts |
| Model calls | Separate answer/follow-up/review attempts, provider requests, transport success/failure, queue wait, provider time and complete-call duration |
| Tokens | Provider-reported input/output/total counts and coverage; missing or malformed values remain null |
| Cost | Estimates at collection time using configured input/output rates; sums of known costs and explicit coverage |
| Current load | Active chats/model calls, model-slot waiters, queued plus in-flight metric writes, writer health, dropped events and recent persisted request activity |
| History | Time/model filters, request-activity chart, model and purpose breakdowns, paginated request inspection with metadata only |

Operational success is not factual accuracy. Accuracy, citation support and
completeness are explicitly **not evaluated**, pending labeled evaluation data.
Provider quota remaining is not inferred from observed traffic. Non-streaming
provider time includes the complete HTTP operation; it is not time to first token
or isolated decoding throughput. No CPU/RAM or infrastructure measurements are
claimed by the model metrics page.

Request success means a 2xx response excluding cancellation. It can include a
valid insufficient-context or clarification response. Individual call success
means the transport accepted a complete text completion; subsequent RAG JSON or
citation validation can still fail the request. Outcomes and drilldown distinguish
these cases. Cost per answer divides known, completely priced model spend by
successful document answers in the selected period; it includes the cost of other
calls in that period and is not an invoice price for a single answer.

## Collection and privacy

`LocalWorkspaceMiddleware` creates a measurement only for canonical POST
`/v1/chat` and `/v1/admin/chat`, including early rejections and invalid payloads.
The request UUID corresponds to the middleware's `X-Request-ID`. Health checks,
analytics reads, uploads and CLI traces do not inflate the chat metrics.

Context variables isolate each request and its call stage across asynchronous
graph execution. Each real generation attempt records usage directly from the
validated HTTP transport, so resolver, draft and review calls are counted once
each. Prompt budgets, provider choices, retries, RAG prompts and response schemas
are not changed by collection.

Only explicit metadata allowlists are stored. There are no questions, answers,
passages, filenames, credentials, conversation IDs or visitor identifiers in the
metrics tables. Provider metadata stores only its hostname, not full URLs or
authentication headers. Errors are class categories, not exception messages.
Existing private admin diagnostics and CLI traces remain separate.

Finished records enter a bounded in-memory queue without waiting for SQL. A
background writer commits request and call rows atomically in batches of up to
100, with a configured write deadline. Metrics-storage failures do not change
chat responses. Queue overflow or failed writes discard events and increase the
collector's dropped-event count; the dashboard warns that totals can undercount.
Graceful shutdown waits up to five seconds for pending writes. Abrupt process
termination can lose uncommitted metrics without a dropped-event record.

Persisted history survives a restart and aggregates data from shared storage.
Live gauges and collection-health counters describe the responding process;
they are not distributed totals and reset on restart. Request counts describe
persisted, finished requests; the last-minute counter filters those requests by
their start timestamp. Active requests are represented by the separate live gauge.
All SQL totals/charts/page rows use one repeatable-read snapshot. Records arriving
after that snapshot appear on the next refresh.

## API and local access

- `GET /v1/admin/session`: returns the existing ephemeral local admin token.
  The route explicitly requires a loopback client and local Host. The middleware
  also enforces same-origin access and `Cache-Control: no-store`. This matches the
  existing `/admin` page, which already embeds the same token.
- `GET /v1/admin/metrics`: requires `X-Admin-Token`. Parameters: `hours` 1–720
  (default 24), optional exact `model` name, `offset` >= 0 and `limit` 1–50
  (default 25). Returns window, request totals, outcomes/intents, call totals,
  model/purpose breakdowns, workflow timings, timeline, recent requests, runtime,
  pricing status and evaluation availability. Invalid query: 422; denied: 403;
  unavailable storage: 503. Reads have a ten-second deadline.

The frontend fetches the token only for analytics, stores it only in module
memory, sends it in a header, and refreshes it once after a 403 caused by an API
restart. It does not store tokens in local/session storage or query strings.
Malformed non-ASCII admin tokens now return 403 rather than causing a 500.

Model filters include requests involving that model and restrict call aggregates
to that model. Request drilldown displays all calls belonging to the selected
request. Current load remains process-wide regardless of the historical filter.
Time/model filters and pagination cannot expose private conversational content.

This is still the existing trusted local administrator boundary. Public admin
accounts, tenant authorization, chatbot IDs and visitor sign-in belong to later
steps. `APP_ENV=production` remains fail-closed. No Langflow service was installed
or connected in this step.

## Migration and settings

Apply `uv run alembic upgrade head` from `Backend`, then restart the API.
Revision `e74b53fcc6ae`, following `d63a42fbb5fd`, adds `chat_metrics`,
`model_call_metrics` and their timestamp/request indexes. It does not modify
documents, chunks or conversation history. Startup/readiness verifies both new
tables. The migration is applied locally and `alembic check` reports no new
operations.

| Setting | Default | Meaning |
| --- | --- | --- |
| `METRICS_QUEUE_CAPACITY` | 1000 | Maximum pending records; allowed 10–10000 |
| `METRICS_WRITE_TIMEOUT_SECONDS` | 2 | Per-batch SQL deadline; allowed >0 and <=10 |
| `METRICS_MODEL_PRICES` | `{}` | Exact model name to input/output USD per million tokens |

Illustrative configuration only; replace names/rates with verified provider values:

```dotenv
METRICS_MODEL_PRICES={"your-model":{"input_usd_per_million":0.10,"output_usd_per_million":0.20}}
```

No actual provider rate or `.env` secret was changed. Without a rate or reported
input/output usage, a call's cost stays null. Partially observed sums are flagged
as partial; a period containing no calls has no reported usage rather than a
fabricated measurement. Rates exclude cached-token discounts, other billing
tiers, hosting, embeddings and other fees. Estimated call cost is stored with
the measurement, so later rate changes do not retroactively recalculate it.

Historical metrics are not backfilled from old chat history or logs. There is
currently no automatic deletion/retention worker for these tables; they are
included in database backups. Set a retention policy before public-scale use.

## Main implementation files

| File | Purpose |
| --- | --- |
| `Backend/app/services/metrics.py` | Request/call scopes, gauges, allowlists, pricing, bounded writer |
| `Backend/app/services/llm.py` | Direct transport timing and provider usage |
| `Backend/app/services/rag.py` | Graph metadata, prompt fingerprint, resolver/review stage tagging |
| `Backend/app/core/middleware.py` | HTTP lifecycle, early rejection and correlation |
| `Backend/app/storage/metrics.py` | Atomic writes, SQL percentiles and aggregation |
| `Backend/app/storage/models.py` | Metric table models |
| `Backend/app/api/v1/metrics.py` | Protected analytics and local session bootstrap |
| `Backend/app/main.py`, `Backend/app/storage/db.py` | Writer lifecycle and schema readiness |
| `Backend/app/core/config.py`, `Backend/.env.example` | Queue, write deadline and optional prices |
| `Backend/app/core/local_access.py` | Safe malformed-token rejection |
| `Backend/migrations/versions/e74b53fcc6ae_add_model_analytics.py` | Additive schema migration |
| `frontend/src/components/admin/ModelAnalytics.tsx` | Connected dashboard, filters, chart and inspection |
| `frontend/src/types/analytics.ts`, `frontend/src/services/backend.ts` | Typed live API and memory-only admin token |
| `frontend/src/App.tsx`, `frontend/src/context/ChatbotContext.tsx` | Active Analytics navigation |

## Verification

- Full backend regression suite with local PostgreSQL and cached embeddings:
  **212 passed, 1 skipped, 342 subtests passed**. The skipped test is the optional
  live-policy suite, not analytics. No new provider call is required by these tests.
- New tests exercise sanitized usage, configured cost math, missing/malformed
  usage, resolver/answer/review counting, concurrent request isolation, rate limits,
  cancellation while queued, bounded buffers, writer failure, admin protection,
  malformed tokens, request correlation, percentiles, partial totals, model/time
  filters, pagination, API serialization and history across database instances.
- Frontend: **28 passed**, TypeScript check passed and Vite production build passed.
  New cases cover real response rendering, unavailable pricing/quality, partial
  usage, filters, request inspection, metrics outages, loss warnings and token rotation.
- Live smoke through port 3000: unauthorized analytics returned 403; a greeting,
  invalid request and document question returned 200/422/200 and appeared in
  persisted analytics. Provider input/output usage was captured and the collector
  reported no dropped events. Pricing and accuracy correctly remained unavailable.
  Evidence: `.cache/analytics-evaluation-2026-10-12.json`, containing sanitized
  aggregate data only. Totals can include other legitimate concurrent workspace activity.
- Rendered visual QA is unverified: the browser skill found no available browser
  surface. DOM tests, production build and live API checks provide the checks above.
- Existing imported files are preserved. No files were deleted or new dependencies added.

Analytics is complete for the current local workspace. It measures behavior and
resource use; it does not certify answer quality or replace distributed admission
control, provider budget enforcement or future per-chatbot authorization.
