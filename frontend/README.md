# Document Assistant frontend

The active application provides live chat, document management, backend status,
and local administrator model analytics and assistant configuration.
It calls our FastAPI backend through a local Vite proxy. Provider keys entered in
Assistants are sent to the backend for encryption and are not persisted in browser
storage. Chat never calls providers directly or falls back to simulated data.

## Local development

Start PostgreSQL and the API using the repository README. The API must listen on
`http://127.0.0.1:8000`. In another terminal, from `frontend`:

```powershell
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. Vite binds only to loopback. Its proxy translates
only the local UI origins for the backend; foreign origins remain rejected.
The production build is tested locally with `npm run preview`, which uses the
same local proxy. Remote/public hosting is outside the current supported scope.

## Checks

```powershell
npm run lint
npm test
npm run build
```

Chat submits `question`, `top_k`, and optional document UUIDs. Sources fetch their
original passages on demand. Clarification resends the original question with the
chosen document. Each failed message retains its own complete request for retry.
The UI sends an optional conversation UUID and private `X-Conversation-Key` for
bounded PostgreSQL memory. Credentials, a bounded transcript and document selection
are kept in tab session storage, so refresh retains the current chat. Clear chat
rotates credentials; old server history expires according to its retention setting.
Greetings need no retrieval. Follow-ups use fresh document evidence and inherit the
last grounded turn's document scope unless explicit document IDs are supplied.

The Chat assistant selector retains separate histories and document selections
for each configured assistant. Workspace default keeps the original model and
workspace-wide document picker. Models manages Groq/Gemini connections, key
replacement, model discovery and tests. Assistants configures selected models and
assigned documents. Both pages provide confirmed deletion with backend checks;
assistant deletion preserves PDFs, and referenced connections cannot be deleted.
See [assistant setup](../docs/assistant-configuration.md).
Analytics now includes assistant/provider filters, configuration comparisons and
process cache counters. See [Stage 2](../docs/assistant-caching-analytics.md).

PDF uploads use durable jobs and status polling. The limit is 10 MiB and 100 pages;
image-only PDFs need OCR outside this app. Retired documents stay in the library
but are excluded from chat selection. A missing original PDF disables download
while its stored citations remain accessible. Deletion requires UI confirmation.

Health/readiness reflect the actual backend. Readiness does not test provider
credentials or quotas; generation failures are shown on the affected request.
The UI allows 195 seconds for chat, including the backend's multipart review.

## Preserved future features

The Analytics tab reads protected, persisted measurements: request outcomes,
latency percentiles, model-call stages, reported tokens, configured cost estimates,
and process-local load. It does not use the legacy simulated dashboard. The
ephemeral local admin token is fetched from `/v1/admin/session` and kept only in
memory. Metrics refresh every 15 seconds and can be filtered by period and model.
Historical activity before metrics were enabled is not backfilled. Accuracy and
remaining provider quota are shown as unavailable rather than fabricated.
See [analytics implementation and limits](../docs/model-analytics-2026-10-12.md).

Existing AI Studio admin, mock, configuration, and widget files are retained.
They are not mounted by the active App. Advanced admin and external embedding
will be integrated later, after their backend contracts and security are defined.
The standalone public widget is still a legacy prototype and must not be embedded
on external websites. No existing source file was deleted during integration.
