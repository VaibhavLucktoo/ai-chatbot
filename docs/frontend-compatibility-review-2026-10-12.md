# Frontend compatibility review — 12 October 2026

**Verdict:** The supplied frontend is a reusable React/TypeScript UI prototype,
but it is not integrated with this backend. It can be customized into the
initial local project without replacing its visual layout. Its central API
adapter and backend data types need substantial correction; several dashboard
features are simulations rather than missing requirements for our backend.

## Scope and verification

- Inspected all **33 files** under `frontend`, including configuration, public
  widget script, state/context, API adapter, simulator, and every component.
- Compared requests, responses, and workflows with the backend's live
  `/openapi.json`, current source, and frontend contract documentation.
- Live probes reproduced **404** for the frontend health paths, **422** for its
  chat payload, and **403** for the frontend's port-3000 origin. A correctly
  shaped filtered chat request returned 200 with the backend fallback response.
- An npm dependency-resolution dry run failed with **ERESOLVE**: the frontend's
  direct `esbuild ^0.25.0` dependency resolved to 0.25.12, while the resolved
  Vite 8.3.4 requires optional peer esbuild `^0.27.0 || ^0.28.0`.
- No frontend packages were installed, no scripts were executed by npm, and no
  frontend or backend source was changed. The dry run used an ignored local
  npm cache. A build, TypeScript check, and rendered browser QA remain unverified
  because dependency resolution is blocked.
- Evidence: `.cache/frontend-npm-audit/_logs/2026-10-12T10_09_26_946Z-eresolve-report.txt`
  and `.cache/frontend-backend-openapi.json`.

## What is reusable

The component boundaries, document table, chat layout, loading/error presentation,
source panel, theme controls, and navigation provide a practical starting point.
Normal React message rendering uses text interpolation, so it does not share the
public widget's raw-HTML rendering problem. The main chat UI correctly describes
the backend's stateless conversation behavior. Document IDs can be passed as
filters after replacing the mock records with real UUIDs.

The current program flow is:

```text
React components -> AppContext -> ApiClient
                                -> MockBackend by default
                                -> Remote fetch for chat/search/upload/health only
                                   (search/upload may silently fall back to mocks)
```

There is no server-side proxy implementation in this export. Naming MockBackend
a proxy does not make it a connection to PostgreSQL or FastAPI.

## Contract mismatches

| Feature | Frontend currently expects | Actual backend | Required adaptation |
| --- | --- | --- | --- |
| Chat request | `query`, optional `temperature_override` | `question`, `top_k`, optional `document_ids`; extra fields forbidden | Change the wire type and every chat sender |
| Chat answer | `citations`, `context_status`, latency, token usage | `answer`, `sources` | Map sources explicitly; treat extra metadata as unavailable |
| Source fields | `document_name`, `snippet`, score | `filename`, `document_id`, `chunk_id`, `page_number` | Fetch passage text from the citation endpoint; remove fabricated relevance percentages |
| Clarification | Boolean plus suggested topic strings | `status: clarification_required`, `question`, `original_question`, `top_k`, document UUID/name choices | Retain the original request; resend it with selected IDs |
| Liveness | `/health/live` and timestamp/uptime | `/v1/health`, status/message | Change URL and type |
| Readiness | `/health/ready` plus database/embedding/LLM checks | `/v1/ready`, ready/not_ready status | Change URL; do not invent LLM readiness |
| Document list | Always a mock array of DocumentRecord | `GET /v1/documents`: `items`, `total`, `limit`, `offset` | Unwrap items, paginate, use backend fields |
| Document metadata | `document_id`, uploaded_by, size, uploaded_at, model/dimensions | `id`, `created_at`, status, active, page/chunk counts, source availability | Separate actual metadata from optional presentation fields |
| Upload | Synchronous request, mock fallback, ready record | Durable `/v1/documents/jobs`, followed by polling; synchronous alternative exists | Use submission/status and explicit failure handling |
| Upload limit/status | 25 MB, processing status, timed percentage/stage simulation | 10 MiB; pending/ready/failed; no stage/progress percentage | Validate both picker/drop; display real state without invented stages |
| Search | `document_name`, `text`, dense/sparse/hybrid scores, total_found, latency | `filename`, `content`, `cosine_distance`; top_k/matches/results | Change type and displayed fields; distance is not a confidence percentage |
| Delete | Mock deletion; proposed admin DELETE route | `DELETE /v1/documents/{id}`, success 204 | Call actual route; don't parse an empty response as JSON |
| Retirement | Not implemented | PATCH `/v1/documents/{id}/activation` | Add optional retire/reactivate controls and active-only chat picker |
| Downloads | No adapter operation | GET `/v1/documents/{id}/source`, PDF or legacy 409 | Respect source_available; support existing missing-source records |
| Authentication | Browser role selector and bearer token | Trusted local scope; diagnostics use X-Admin-Token | Remove security claims about simulated roles; no provider secrets in browser |
| Metrics/config | Mock telemetry, alerts, configuration updates and provider probes | Those runtime-write/metrics APIs are not implemented | Hide/defer or make clearly read-only/unavailable |

The static Contract Inspector incorrectly labels `/v1/admin/documents` as missing.
It exists, but is token protected and returns a pagination envelope. The normal
catalog and lifecycle APIs already cover frontend document management.

## Integration blockers and defects

1. **Installation is blocked.** Resolve the Vite/esbuild peer conflict rather
   than using force flags to bypass it. The direct esbuild dependency is not
   imported by application code, so removing it may be sufficient after checking
   the actual resolved build. Add a lockfile after successful installation.
2. **Remote mode can pretend success.** Search and upload catch every remote
   error and return MockBackend results. Document listing/deletion and all
   telemetry/config/probes always use mocks even in remote mode. A failed upload
   can appear indexed; simulated deletion leaves the actual backend unchanged.
   Live mode must surface errors and never switch to demo data implicitly.
3. **Origin handling is absent.** Vite has no API proxy, and the default API URL
   differs from the browser origin. The backend rejects that Origin with 403.
   Use same-origin serving or a narrowly configured local development proxy;
   account for both Host and Origin validation. Bind development serving to
   loopback instead of the current `--host=0.0.0.0` when it can proxy backend APIs.
   Vite supports configurable development proxies, but this project defines none.
   [Vite server options](https://vite.dev/config/server-options#server-proxy).
4. **Chat and clarification cannot work against the current schema.** The
   supplied request received 422. Even after renaming query, a normal response
   has sources rather than citations, and a clarification response has no answer.
   The current handler would show an empty message instead of document choices.
5. **Timeouts are too short for the existing workflow.** Chat defaults to 15
   seconds; uploads use 30. The backend permits a 180-second full chat deadline
   and longer ingestion. Compound questions may make a review call. Separate
   health, chat, upload acknowledgement, and polling timeouts; retain retry data.
6. **The public widget has an HTML injection sink.** It writes model answer and
   source names into innerHTML. Render untrusted text with textContent/DOM nodes
   or a deliberately sanitized renderer before activating it. It also sends
   query, reads citations, lacks timeout/cancellation/clarification support, and
   can issue overlapping Enter-key requests despite disabling its send button.
7. **Public embedding is outside the supported deployment.** A remote website
   cannot use another user's loopback-only backend. Direct cross-origin script
   calls are denied; iframe origin behavior depends on where it is hosted. The
   backend admin has frame-ancestor restrictions, and no public authentication
   or sharing contract exists. The promise to embed on any website is premature.
8. **Settings tests unexpectedly persist changes.** BackendSettingsModal calls
   ApiClient.saveSettings before probing. Cancel does not restore the old values;
   context state may then disagree with the API client's actual mode/URL.
9. **Mode changes leave stale data.** Context refreshes health after changing
   settings, but not documents, selected IDs, telemetry, model data, or messages.
   Mock document IDs are not UUIDs and cause backend validation errors.
10. **Manual theme configuration is incomplete.** Context toggles a dark class,
    while the CSS does not override Tailwind's default media-query dark variant.
    Add the class-based variant if manual toggling is retained.
    [Tailwind dark-mode documentation](https://tailwindcss.com/docs/dark-mode).
11. **Retries lose their original request.** ChatInterface keeps one lastQuery
    for the whole conversation. Retrying an older failed message sends the newest
    query and current scope. Store question, top_k and selected IDs per message.
12. **Simulator behavior is not a faithful contract test.** It invents indexed
    PDF content from a filename and file size. Deletion removes a document record
    without purging the shared knowledge chunks. It can return sufficient-context
    boilerplate even when the selected document produced no evidence. Keep it
    isolated as explicit demo mode, or update it to the exact live schema.

Additional usability gaps: no live document pagination/polling, no failed-job
retry flow, no source download, no retire/reactivate controls, no 500-character
question guard, minimal delete error/loading handling, no global error boundary,
no component tests, and incomplete narrow-screen behavior for the sidebar/widget.
Clipboard operations and modal focus management also need browser QA.

## File-by-file assessment

Paths below are relative to `frontend`.

| File | Implementation and assessment | Initial-phase action |
| --- | --- | --- |
| `.env.example` | Gemini key/AI Studio URL placeholders, not RAG API configuration; no Gemini SDK call exists in application source | Replace with relevant non-secret frontend settings; keep provider keys server-side |
| `.gitignore` | Ignores generated dependencies/builds and local environment files | Keep |
| `.gitkeep` | Empty placeholder from folder creation | Optional cleanup once source is committed |
| `README.md` | AI Studio instructions require a Gemini key unrelated to our backend | Rewrite local full-stack instructions |
| `package.json` | React/Vite/Tailwind stack; dependency peer conflict; no lockfile; unused GenAI/Express/dotenv/motion imports; Unix cleanup command | Resolve dependencies, remove unnecessary packages, use loopback dev host, portable scripts |
| `tsconfig.json` | Bundler-oriented TS config, no strict mode; allows JS | Retain baseline, enable strict checking after aligning contracts |
| `vite.config.ts` | React/Tailwind plugins and alias; no API proxy | Configure local integration; preserve HMR unless intentionally disabled |
| `metadata.json` | AI Studio metadata advertises server-side Gemini capability that this export does not implement | Update descriptions or leave as export metadata outside product promises |
| `index.html` | Entry, branding, external Google fonts | Rebrand; ensure deployment CSP/font loading matches actual hosting |
| `src/main.tsx` | Standard React root and stylesheet entry | Keep; optionally wrap with an error boundary |
| `src/index.css` | Tailwind import, fonts and scrollbar; missing class-driven dark variant | Small theme fix; visual browser QA |
| `src/App.tsx` | Context, tab-based shell, global modals/widget, embed query mode | Keep shell; narrow tabs; defer embed route; ensure retained modals work in chosen modes |
| `src/types/rag.ts` | Detailed types, but incorrectly described as actual backend contracts | Replace wire types from OpenAPI; keep UI view models distinct |
| `src/services/apiClient.ts` | Central fetch adapter with wrong paths/types, short timeouts and pervasive mock fallbacks | Main rewrite target; real catalog/jobs/lifecycle/sources and consistent errors |
| `src/services/mockBackend.ts` | In-memory demo data, hard-coded answers, simulated uploads/metrics/config | Explicit demo only; never automatic live fallback |
| `src/context/AppContext.tsx` | Central theme/navigation/chat/document/config state; mock welcome/telemetry and self-selected roles | Keep core state; remove mock boot claims; refresh/reset on mode changes; real job state |
| `src/components/layout/Header.tsx` | Theme/settings/upload/embed controls and role dropdown | Keep basic controls; replace role simulation with local-operator presentation |
| `src/components/layout/Sidebar.tsx` | Navigation and health/telemetry display | Keep Chat/Documents/Status; simplify and make mobile navigation usable |
| `src/components/chat/ChatInterface.tsx` | Stateless messages, selected-document dropdown, retry and feedback | Correct question/sources/clarification; active-ready picker, per-message retries, input limit |
| `src/components/chat/ChatMessageItem.tsx` | Safe React text, citations/clarification/error actions; feedback only client state | Reuse; accurate fallback language and original-request retry data |
| `src/components/chat/CitationViewer.tsx` | Inline mock snippets and invented match percentages | Reuse layout; map filenames; fetch chunk text; remove unsupported scores |
| `src/components/chat/ClarificationPicker.tsx` | Topic-string buttons | Replace options with document IDs/names; preserve original question and top_k |
| `src/components/chat/ChatWidget.tsx` | Separate floating chat state using old contract; no selected scope/clarification | Defer or make it use the same corrected chat hook; avoid duplicate initial surfaces |
| `src/components/chat/WidgetEmbedModal.tsx` | Script/iframe snippets and unshipped React package reference; data-primary-color differs from script's data-color | Defer; correct snippets only after a supported embedding design exists |
| `src/components/documents/DocumentManagement.tsx` | Mock table/filter, focus chat, delete confirmation | Reuse; real paginated catalog, statuses, sources, activation and delete errors |
| `src/components/documents/DocumentUploadModal.tsx` | Picker/drop, simulated progress, 25 MB limit; drop lacks size validation | Reuse shell; shared 10 MiB checks, durable jobs/polling, truthful state display |
| `src/components/documents/VectorSearchSandbox.tsx` | Search form/result list expecting unavailable score fields; initial top_k=4 absent from select options | Optional tools tab; actual result fields and explicit errors |
| `src/components/admin/AdminOverview.tsx` | Attractive dashboard for simulated usage, cost, percentiles, queues and alerts | Replace with actual liveness/readiness/document counts; hide unavailable metrics |
| `src/components/admin/BackendSettingsModal.tsx` | Mode/URL/token/timeout editor; probing persists settings | Simplify local connection settings; non-persistent probe; proper timeouts/errors |
| `src/components/admin/LlmConfiguration.tsx` | Large form, provider presets, YAML export, simulated save/probes; form initializes once before async config load | Defer write/probe controls; optional read-only actual model status; no unsupported provider/capability promises |
| `src/components/admin/ContractInspector.tsx` | Static contracts and placeholder Python remediation code with fake metrics/no-op deletion | Developer-only or replace with real OpenAPI; do not copy those routes into production |
| `src/components/embed/WebsiteEmbedDemo.tsx` | Configurator and live-looking simulated external-site preview | Defer; prototype is not evidence of cross-site backend compatibility |
| `public/rag-widget.js` | Standalone DOM widget; wrong chat schema, raw HTML output, weak request/lifecycle controls | Defer; fix security/contract before any use |

## Recommended initial-phase product

Keep three surfaces:

1. **Chat:** actual ready/active document selection, ask a question, loading/error
   state, correct insufficient-context behavior, document clarification, sources
   and passage inspection. Conversation display may stay client-side; explain
   that the backend has no conversation memory.
2. **Documents:** paginated catalog, durable PDF submission, status polling,
   retry by original PDF, download where available, retire/reactivate, and delete
   confirmation. Show actual 10 MiB/text-PDF scope and backend validation errors.
3. **Status/settings:** real API liveness and DB/embedding readiness, connection
   errors and optional read-only model configuration. Model availability and
   quotas are separate from readiness.

Raw passage search can be an optional developer tool. Runtime model changes,
enterprise roles, metrics/cost dashboards, public widgets, and external sharing
should not block the initial local product.

## Implementation sequence and acceptance

1. Repair dependency resolution and establish a reproducible lockfile. Run
   TypeScript and production-build checks without bypassing peer constraints.
2. Set up same-origin/local-proxy serving while preserving the backend trust
   boundary. Make actual backend mode the normal path; demo mode must be explicit.
3. Align wire types and the API client with OpenAPI, including JSON error detail,
   Retry-After, empty 204 responses, binary PDFs, 409 legacy-source handling, and
   per-operation timeouts. Do not request fictitious metrics or config routes.
4. Connect catalog/upload jobs and chat/source/clarification flows. Remove mock
   security claims and manufactured success/progress/telemetry.
5. Verify with generated disposable PDFs: submit/poll/list/chat/inspect/download,
   duplicate submission, failed jobs, validation, retirement, unknown IDs,
   storage/model outage, quota/timeout and deletion. Use isolated data for
   destructive checks. Finish desktop/mobile/keyboard browser QA.

No new backend endpoint is required for the core local chat/document phase.
Existing backend defects listed in the endpoint audit still need their own fixes;
changing frontend contracts does not resolve factual grounding or recovery bugs.
The reusable UI is a starting point, not a completed end-to-end application.
