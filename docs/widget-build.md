# Website widget build — 14 October 2026

Goal: configure an assistant once, then embed its document chat on approved websites.

- [x] Persist per-assistant widget settings: enabled state, exact website origins, title, greeting, color, position and request budgets.
- [x] Provide an isolated chat page and a dependency-free script that launches it in an iframe.
- [x] Issue private visitor sessions; reuse bounded conversation memory and assistant-scoped retrieval.
- [x] Expose only widget routes to visitors through a separate gateway; preserve local administration and document-management access.
- [x] Support citations, clarification, refresh, clear chat, timeouts, errors and responsive keyboard-accessible controls.
- [x] Add widget configuration, preview and copyable script/iframe snippets to the active app.
- [x] Record widget chat in existing assistant Analytics; verify origin restrictions, session isolation, budgets and revocation.
- [x] Document HTTPS hosting and provide an independent website demo for port 3001.
- [ ] Verify rendered desktop/mobile behavior, actual cross-site framing and browser privacy-mode storage in a connected browser.
- [ ] Deploy the dedicated gateway at the operator's chosen HTTPS domain and verify a live website using actual provider credentials.

Implementation stays in the existing FastAPI/React repository. Hosting requires a reachable HTTPS service; Sites static hosting cannot run this PostgreSQL/Python backend. No existing documents or assistant credentials will be changed by tests.

Migration `b07e75bee9d1` was applied to the local database. Alembic check reports no schema drift. Docker Desktop and the existing PostgreSQL service were started for verification; existing document and assistant records were preserved.

Frontend verification: full suite **45 passed**; final preview-close, transcript-refresh and capability-rotation changes also passed all **9 targeted widget checks**. TypeScript and the final production build passed.

Backend verification with PostgreSQL and cached embeddings enabled: **248 passed, 1 skipped, 375 subtests passed**. The skip is the optional live-provider policy suite. Source whitespace checks passed.

PostgreSQL widget checks cover durable capabilities, concurrent budgets, expiry/revision revocation, cited-passage access, and the complete HTTP visitor flow with bounded conversation history and assistant Analytics. All use disposable schemas and mocked generation.

Browser discovery returned no available surfaces, so DOM/HTTP checks are not a claim of rendered browser QA. Live provider generation and public deployment were not performed. See [setup and deployment](website-widget.md).
