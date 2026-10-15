# Render live preview and portable deployment

The repository-root Docker image serves the React build and FastAPI from one
origin. In `APP_ENV=production`, the browser asks for the workspace username and
password before loading the app. All authenticated operators share documents,
models, assistants, analytics and administrator rights. This is suitable for a
private demonstration/shared workspace, not separate customer accounts.

Only `GET /v1/health` and `GET /v1/ready` are available without credentials. Website
widget routes also require workspace credentials on this service. Use the separate
widget gateway described in `website-widget.md` when public embedding is needed.
Interactive API documentation stays available in local development and is disabled
in the hosted workspace.

## Update an existing Render service

1. Push these changes to the GitHub branch linked to Render.
2. In the Render dashboard, open the existing Web Service and its Settings.
3. Use the Docker runtime. If the existing service is a Static Site, create a Web
   Service for the full app; static hosting cannot run FastAPI.
4. Leave **Root Directory** empty. Set **Dockerfile Path** to `./Dockerfile` and
   **Docker Build Context Directory** to `.`. The existing `Backend/Dockerfile`
   is for the backend alone and does not build the React app.
5. Leave **Docker Command** empty to use the image's startup command. It applies
   `alembic upgrade head` before starting one API process on Render's `PORT`.
6. Set **Health Check Path** to `/v1/ready`.
7. Use one instance with at least 2 GB RAM as a starting point for local ONNX
   embedding inference and isolated PDF parsing. Measure usage before resizing.
   Check the displayed service/database costs before creating or resizing them.
8. Create or reuse Render Postgres in the **same region** as the web service.
   The migrations enable `vector`; Render supports this extension. Prefer the
   database's internal connection details for service-to-database traffic.
9. Configure the environment below, then choose **Manual Deploy > Deploy latest
   commit**. If changing environment variables, save and redeploy.

## Environment variables

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `WORKSPACE_USERNAME` | `admin` or your preferred username |
| `WORKSPACE_PASSWORD` | Random password, 32–256 printable ASCII characters |
| `ASSISTANT_ENCRYPTION_KEY` | Stable Fernet key, kept separately from database backups |
| `DB_HOST` | Render Postgres **internal** hostname |
| `DB_PORT` | `5432` |
| `POSTGRES_DB` | Database name from Render |
| `POSTGRES_USER` | Database user from Render |
| `POSTGRES_PASSWORD` | Database password from Render |
| `LLM_BASE_URL` | Reachable OpenAI-compatible provider API base, including its `/v1` prefix |
| `LLM_MODEL` | Exact model name available to your provider account |
| `LLM_API_KEY` | Provider API key |
| `LLM_TIMEOUT_SECONDS` | `120` |
| `EMBEDDING_WARMUP_ON_STARTUP` | `true` |
| `WIDGET_PUBLIC_ENABLED` | `false` for this private preview |

On Render, the allowed HTTPS origin defaults to the automatically provided
`RENDER_EXTERNAL_URL`. For a custom domain or another server, set
`APP_PUBLIC_ORIGIN=https://your-domain.example`. The application allows that exact
host and origin; use its canonical address when opening the app.

Keep secrets in Render's Environment settings, not GitHub or frontend variables.
For an existing service, you can generate the password and encryption key locally
from the repository root (these commands print secrets to your own terminal):

```powershell
./.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
./.venv/Scripts/python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If migrating your existing local database, preserve its current encryption key
instead of generating a replacement. Otherwise saved provider keys cannot be
decrypted. Existing local data does not transfer automatically; for a fresh demo,
create a provider connection in **Models**, configure an assistant and upload a
PDF after signing in. You can also configure model connections in the UI rather
than the environment's workspace-default LLM, then select that assistant in chat.
Local Ollama on your laptop is not reachable as `127.0.0.1` from a remote container.

## Optional Blueprint for a new deployment

`render.yaml` defines a Docker service and a Postgres database, with the internal
database settings linked automatically. It generates a stable random workspace
password and encryption key. Supply the provider settings when prompted.

Use **New > Blueprint**, select the repository/branch, review the resources and
costs, and apply. Find the generated `WORKSPACE_PASSWORD` in the service's
Environment settings and sign in as `admin`. Do not create duplicate resources
if your existing service and database are already configured. Adding this file
alone does not reconfigure an existing service that is not managed by a Blueprint.

The Blueprint uses paid resources and a 1 GB database disk for a small preview.
For temporary experiments, Render also offers free resources with limitations:
free web services sleep when idle and free databases expire after 30 days. A
512 MB web instance may not fit embedding inference and PDF parsing reliably.
Delete temporary resources in the Render dashboard when finished to stop charges.

## Verify the deployed application

1. Wait for the Docker build, migrations and embedding warmup to finish.
2. Open `https://YOUR-SERVICE.onrender.com/v1/ready`; expect `{"status":"ready"}`.
3. Open the service root in a browser. Sign in with `WORKSPACE_USERNAME` and
   `WORKSPACE_PASSWORD`. The full React application should load.
4. In **Models**, create/test a provider connection; configure an assistant with
   an available model in **Assistants**.
5. Upload a small text PDF, assign it to the assistant, select that assistant in
   **Chat**, ask a document question, and open a citation to verify its source.
6. In a private browser window, verify the app, documents and admin endpoints
   require authentication. After redeploying, check documents and provider
   connections still work.

The readiness probe checks PostgreSQL/schema and embedding warmup. It does not
validate model credentials: use the UI's model test and a real chat request.
The image defaults to one embedding thread and inference batches of four to
reduce CPU contention and peak inference memory. `EMBEDDING_THREADS` and
`EMBEDDING_BATCH_SIZE` can override those values; smaller batches do not change
the model or require reindexing. These settings do not guarantee that the full
application fits in a 512 MB service.
Both the pinned embedding model and the separate chunk tokenizer are cached in
the image, so indexing does not need a first-upload tokenizer download. CI runs
the production image with Hugging Face offline mode and verifies a synthetic PDF
can be indexed and deleted while liveness checks continue to succeed.

If an upload stays Processing while requests fail, inspect the exact request
status and Render Events/runtime logs at that time. A successful `200` health
check does not explain a separate failed polling or delete request. Confirm
`Out of memory`, `Killed`/exit 137, or health-check failures before attributing an
outage to resource limits. Deleted queued uploads are fenced against background
recovery, and processing stops between embedding batches after deletion.

HTTP Basic sign-in is browser-managed; close the browser session or rotate the
workspace password to revoke access. This deployment runs one process/instance
because admin tokens, concurrency limits and authentication failure throttling
are process-local. For multi-user production, add individual identities,
document authorization and shared rate limiting before scaling.

## Move the same image to another server

Build with `docker build -t ai-chatbot .`. Set the same environment variables,
`APP_PUBLIC_ORIGIN`, and a reachable PostgreSQL/pgvector instance. Put an HTTPS
reverse proxy in front of the container and expose its application port only to
that proxy/private network: HTTPS terminates at the proxy, and arbitrary forwarded
headers are deliberately not trusted. Preserve the database and encryption key
when moving. Model assets are baked into the image; documents and application
data live in PostgreSQL, so an application disk is not needed for the preview.

Render references: [Docker services](https://render.com/docs/docker),
[Blueprint fields](https://render.com/docs/blueprint-spec),
[Postgres extensions](https://render.com/docs/postgresql-extensions),
[free resource limits](https://render.com/docs/free).
