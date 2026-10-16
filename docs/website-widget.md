# Assistant widgets on other websites

Use **Website widget** in the active app. Select an existing assistant, customize the
title, greeting, color and button position, and list each approved website origin.
Enable and save the widget, then copy either **Chat button** or **Inline iframe**.
The selected assistant supplies the model and document assignments. An empty
assignment never becomes access to the workspace's documents.

The administration preview shows a sample website with a floating chat icon in
the selected corner. Clicking it opens the live chat; the icon changes to a close
button. Closing hides the panel while retaining the conversation for reopening.
Preview opens even before saving, when the website widget is disabled, or when
the current origin is not in its allowed list. Appearance edits show immediately.
Test questions use the selected assistant's existing local chat API with a separate
private conversation; opening the preview never saves settings or enables public
access. The assistant itself must be active to send questions. The embedded
launcher uses the same chat/close icons; its website restrictions still apply.

The chat-button script has no framework dependency. Paste it before `</body>` or
in a site's custom-code area. The iframe fits in a custom HTML block. React and
Next.js can load the generated script once, for example with a script component.
No published React widget package is required. The old `/rag-widget.js` prototype
is retired; replace old snippets with the newly generated code.

## Local setup

Apply the additive migration from `Backend` before starting the API:

```powershell
$env:UV_PROJECT_ENVIRONMENT = (Resolve-Path ../.venv).Path
uv run alembic upgrade head
uv run python run.py
```

Start the frontend as usual on port 3000. The default widget host is
`http://127.0.0.1:8000`. The administration preview works without adding a website.
An independent sample website is provided at
`frontend/public/widget-demo.html`; serve `frontend/public` on port 3001:

```powershell
python -m http.server 3001 --bind 127.0.0.1 --directory frontend/public
```

Add `http://127.0.0.1:3001` as an allowed website, then visit
`http://127.0.0.1:3001/widget-demo.html?widget=YOUR_WIDGET_ID`. The ID is in the
generated snippet's `data-widget` attribute. The sample loads the real launcher
and iframe from port 8000. It never uses simulated answers. Live chat uses the
assistant's model quota. The demo's optional `host` parameter selects a different
widget host for deployment tests.

Exact origins include scheme, hostname and port. `www.example.com` and
`example.com` must be listed separately. HTTPS is required for live website
origins; HTTP is accepted only for localhost. Wildcards, credentials, page paths,
queries and fragments are rejected. The parent website must permit the widget
host in its own script/frame policies. If its policy disallows inline injected
styles, use the inline iframe rather than the floating launcher.

## Public HTTPS hosting

A visitor cannot reach your computer's localhost. Host the Python application,
PostgreSQL and cached embedding assets on infrastructure that can run them, and
terminate TLS at the widget domain. Static Sites hosting cannot run this backend.
Public publishing is separate from the local build; no site was deployed by this change.

Configure the backend environment:

```dotenv
WIDGET_PUBLIC_ENABLED=true
WIDGET_PUBLIC_ORIGIN=https://chat.example.com
```

For an existing production workspace service, set these variables on that service
and redeploy. Use its exact HTTPS address as `WIDGET_PUBLIC_ORIGIN`, or a widget
domain routed to the same service with its original `Host` preserved. Only widget
pages, static assets and visitor APIs are public on the configured widget host.
The workspace dashboard and admin APIs still require workspace credentials and
send `X-Frame-Options: DENY` with `frame-ancestors 'none'`. Public visitor API
requests originate inside the iframe at the widget origin; the embedding website
is checked separately against the widget's saved allowed origins. Widget iframe
responses omit XFO and preserve that allowlist in CSP; assets use
`frame-ancestors *`. Public access remains disabled unless explicitly enabled.

Alternatively, run the dedicated gateway from `Backend` behind a reverse proxy:

```text
uv run uvicorn app.widget_gateway:create_widget_gateway --factory --host 127.0.0.1 --port 8001 --no-proxy-headers
```

On Windows, use the selector-loop launcher:

```powershell
uv run python run.py --widget-gateway
```

Forward the widget domain to port 8001, preserve its original `Host`, and route
only that gateway. It mounts no admin, workspace chat, catalog, uploads, original
PDF downloads, model discovery or OpenAPI endpoints. The gateway refuses startup
unless public access is explicitly enabled and the configured host uses HTTPS.
The local console remains on loopback port 8000. Operate it locally or through an
authenticated tunnel; this change does not add remote administrator accounts.
Both services must use the same database, model settings, and encryption master
key. Share the existing master key securely; do not generate a different key on a
second host or expose the key directory via HTTP. The gateway does not run
ingestion recovery. Keep the operator service running for ingestion jobs.

After changing the widget host, restart the service and refresh Website widget
before copying code. Re-copy the launcher snippet after changing its button
color/position. The iframe title, greeting and appearance use current saved settings
when loaded. Keep connection/model tests and factual policy evaluation separate
from embedding validation.

## Visitor access and usage

The iframe talks to its own host, so this implementation does not enable broad
CORS on the workspace APIs. Every frame response supplies a `frame-ancestors`
policy listing the widget's approved origins. This browser policy covers every
ancestor, not only the immediate parent. Origin checks also reject foreign-origin
API posts. Public/widget IDs are identifiers, not secret API keys.

Website restrictions control browser embedding. They are **not visitor identity
or protection against automated clients**: non-browser callers can forge origin
headers and the declared parent origin. Only publish an assistant whose assigned
documents may be disclosed to anonymous visitors. For private audiences, add real
visitor authentication before enabling their widget. Provider secrets remain on
the backend. Public request budgets limit anonymous usage; a deployment can add
edge abuse controls without relaxing the application boundary.

Visitor sessions use random 256-bit capabilities stored as SHA-256 digests in
PostgreSQL. The server chooses the conversation and fixes its assistant. Visitors
cannot submit assistant IDs, conversation IDs, provider keys or model settings.
Document selection may narrow only the assigned scope. Passage inspection requires
a citation issued to that session and an active, ready document still assigned to
the assistant. Visitors cannot download full PDFs through this API.

Session credentials and a bounded transcript are retained in the iframe's tab
session storage. Storage failure leaves chat usable in memory. New chat rotates
the capability; previous history expires under the existing conversation TTL.
Cross-site storage/refresh behavior should be checked in target browsers; some
privacy modes disable or partition storage. Session issuance prunes expired rows
in bounded batches. No questions, answers or session tokens are recorded in
Analytics; conversation history retains the existing bounded PostgreSQL contract.

Saving settings increments the widget revision, revoking existing visitor sessions
on their next request. Disabling the widget, assistant or connection also blocks
subsequent requests. Already admitted turns may finish using their captured model
configuration. Assistant deletion cascades widget settings and visitor sessions;
the existing lifecycle rule also removes its conversation rows while retaining PDFs.

Shared PostgreSQL row locks enforce the widget's per-minute and per-day question
budgets across processes. Daily budgets reset at UTC midnight. Failed/admitted
questions count; one question can make multiple model calls, so these are request
limits rather than monetary spending caps. Each session additionally permits six
questions per minute. Issuance has a separate 30-session/minute limit and a bounded
daily budget, preventing unrestricted session creation from bypassing question
limits. Limits return 429 and `Retry-After`. Existing process admission and model
semaphores also apply. Sessions do not hold database connections during generation.

Widget chat is measured as `/v1/widget/chat` and attributed to its assistant in
existing Analytics. Provider calls, tokens, latency and configured costs retain
the existing measurement limits. No synthetic accuracy or quota data is added.

## Verification

See [build checklist](widget-build.md) for the recorded checks and remaining
deployment/browser verification. Backend tests use isolated PostgreSQL schemas;
UI and widget-script tests use DOM fixtures. Provider calls are mocked in these
checks. They do not establish factual model quality or real-browser framing.
