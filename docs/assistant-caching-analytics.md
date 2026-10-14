# Stage 2: configuration caching and assistant analytics

Assistant chat now uses a bounded cache owned by each backend Database instance.
It holds immutable model settings, decrypted SecretStr credentials and document
assignment IDs. It never stores questions or responses. Defaults are a five-minute
TTL and 128 entries, configured by ASSISTANT_CACHE_TTL_SECONDS and
ASSISTANT_CACHE_MAX_ENTRIES. Set the TTL to zero to disable caching. No Redis or
additional dependency is required.

Cache hits perform one indexed PostgreSQL query for active assistant/connection
revisions. They skip the full configuration query, assignment query and credential
decryption. Database unavailability fails closed. Saves and deletes invalidate
cache entries after commit; connection changes invalidate this process's entire
cache. Other processes detect revision changes on their next hit. Changes made
through direct SQL must increment the relevant revision. An already running turn
uses its captured configuration; edits apply to subsequent turns.

Concurrent misses share a loader. Invalidation prevents an older loader from
repopulating the cache, cancellation of one waiting request does not cancel other
waiters, and failures are not cached. Expired entries are pruned on access; memory
is bounded by the entry limit. Shutdown cancels pending loaders and clears entries.
Decrypted keys remain only in process memory and are never sent to Analytics.
Changing the encryption master key requires the existing credential migration
procedure and a backend restart.

Telemetry continues through the existing bounded background queue and batch writer;
chat responses never await metric inserts. Request rows now snapshot assistant ID,
name, configuration revision, connection ID/revision, configured provider and model.
Model-call rows remain attached through request_id, including answer, follow-up and
review calls. No conversation identifier, prompt, answer, document text or key is
included. Configuration snapshots have no cascading foreign keys, preserving
historical comparisons after assistant deletion or renaming.

Analytics supports assistant, provider host, model and period filters. Workspace
history has its own filter; rows written before this migration have unknown assistant
metadata and cannot be reliably backfilled. Filter choices are drawn from historical
activity in the period, so an assistant appears after it has a recorded request.
Provider filtering uses the adapter's recorded host, such as api.groq.com.

The comparison table groups requests by assistant and configuration/connection
revision. It reports request counts, HTTP success rate, median/p95 response latency,
provider calls/failures, reported tokens and estimated cost. Calls are aggregated
before joining requests, avoiding double-counting requests with multiple calls.
Model/provider filters restrict matching requests and call aggregates; recent
request drilldowns deliberately show all calls for that request for context.
Live load and cache counters describe the current process, independent of filters.
Requests in the last minute follow the historical filters.

Missing usage and pricing remain unknown or explicitly partial. Costs use existing
METRICS_MODEL_PRICES rates keyed by exact model name; administrators must supply
appropriate rates. These are operational comparisons, not answer-quality scores or
controlled benchmarks. Different prompts and document sets affect latency.

Run the additive Alembic migration a96c75bee8c0 before restarting the backend.
It adds nullable snapshots and an (assistant_id, started_at) index on chat_metrics.
Then refresh the frontend, chat with an assistant, and open Analytics. Use the
Assistant filter and expand Recent requests to inspect captured revisions. Save a
configuration change, send another turn and compare the separate configuration rows.
Deleting an assistant retains these measurements; historical names remain visible.

Verified on 13 October 2026:

- Full backend suite: 233 passed, 1 skipped, 353 subtests passed. PostgreSQL checks
  used isolated schemas and embedding checks used cached assets. Providers were
  mocked; the optional live-provider policy suite remained disabled.
- Full frontend suite: 36 passed. The final analytics client/filter checks also
  passed all 7 targeted tests. TypeScript and production build passed.
- Local migration applied to a96c75bee8c0; Alembic reports no schema drift.
- Read-only checks against the real migrated database returned 200 for protected
  Analytics, 403 for anonymous Analytics, and confirmed all Stage 2 fields. Schema
  readiness and the existing assistant administration endpoints also passed.
- No operator documents, credentials or assistant configurations were changed by
  tests. Rendered browser review remains unavailable in this session.
