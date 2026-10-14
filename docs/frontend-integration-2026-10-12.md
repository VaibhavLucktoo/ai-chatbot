# Initial frontend integration — 12 October 2026

The active application at `http://127.0.0.1:3000` connects to the local FastAPI
backend at port 8000. It contains Chat, Documents, and Status screens. Advanced
admin, configuration, mock, and embedding source files remain present for later
work; they are not mounted in this initial flow. All 33 original frontend files
were checked and remain present. No existing source file or stored PDF was deleted.

## Implemented flow

- Chat uses the actual question/top_k/document_ids schema. The picker loads all
  active ready documents across catalog pages and permits up to 20 selected IDs.
  Questions are limited to 500 characters. Each failed message retains its own
  complete request for retry, even after later questions change scope.
- Clarification shows the backend's document choices and resends the original
  question/top_k with the selected ID. Answers use the backend's source array,
  and references load original passages on demand. Model and passage text are
  rendered as text. No confidence scores or token/usage metrics are fabricated.
- Documents supports paginated listing, page filtering, durable upload jobs,
  automatic polling, failed-job guidance, downloads, retirement/reactivation,
  and explicit confirmation for permanent document deletion. Both picker and
  drag/drop enforce the 10 MiB limit. Processing is displayed as a state rather
  than a fictional percentage. Legacy missing-source records disable downloads
  while retaining citation inspection.
- Status shows actual liveness and schema/embedding readiness, refreshed every
  20 seconds. Provider usability is not incorrectly claimed by readiness.
  Connection and operation errors are visible; there is no live-to-mock fallback.
- Vite serves only on loopback and proxies `/v1` and `/openapi.json`. Only the
  accepted local UI origins are translated to the backend's origin. Foreign
  origins remain rejected. Preview uses the same local proxy.
- Dependency resolution was repaired by aligning esbuild with Vite 8. The
  package lockfile is present. The manual Tailwind dark theme is wired correctly.

## Verification

- `npm run lint`: passed (TypeScript with no emit).
- `npm test`: **18 passed** across UI interaction and API adapter checks.
- `npm run build`: passed.
- Live proxied `/v1/health`, `/v1/ready`, catalog, fallback chat and a real policy
  question succeeded. Its returned citations were fetched through the UI proxy.
- An existing original PDF returned HTTP 200, application/pdf, and valid PDF
  header bytes through the proxy. The three original document IDs remained intact.
- A request with the local UI Origin was accepted; a foreign Origin was rejected
  with 403. Tests never changed or deleted the user's stored documents: uploads,
  polling, activation and deletion interactions used contract fixtures.
- All original frontend files remain. There were no backend source changes.

The browser connector returned no available browser surface. Visual rendering,
real-browser keyboard behavior, and physical mobile layout were not inspected.
DOM interaction checks are evidence for wiring and state transitions, not a
replacement for manual visual review. Open the UI to complete that review.

## Running and future work

See [frontend/README.md](../frontend/README.md) for local commands. From `frontend`,
use `npm ci` then `npm run dev`; start the backend separately using the repository
README. No Gemini key or provider key belongs in frontend configuration.

The preserved prototypes should not be mistaken for implemented admin or public
embedding functionality. The public widget is still a legacy prototype and is
not used by this application. External hosting, public access, runtime model
changes and telemetry dashboards require separate contracts and implementation.
Backend factual-quality and recovery findings in the earlier audit remain
separate work; this integration does not claim to resolve those issues.
