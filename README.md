# AI Chatbot

A local document question-answering application with a FastAPI backend and a
React frontend for chat, document management, and backend status.

The Analytics tab shows persisted model usage, request outcomes, latency, cost
estimates when configured, and current load. See [model analytics](docs/model-analytics-2026-10-12.md).

The Models tab manages Groq and Gemini connections and model discovery/tests.
Assistants configures models and assigned documents, with confirmed lifecycle
deletion. Chat selects an assistant with its own document scope and conversation
history. Workspace default retains the existing environment-configured model.
See [assistant configuration](docs/assistant-configuration.md).
The **Website widget** page configures assistant chat for approved websites and
generates script/iframe snippets. See [widget setup and HTTPS hosting](docs/website-widget.md).
Assistant snapshots now use a bounded process cache with database revision checks.
Analytics can filter assistants/providers and compare saved configuration revisions.
See [Stage 2 setup and behavior](docs/assistant-caching-analytics.md).

Chat handles greetings directly and supports document follow-ups with optional,
bounded PostgreSQL conversation memory. Document answers still use fresh retrieval
and the existing grounding checks. See the [conversation upgrade and validation](docs/conversational-upgrade-2026-10-12.md).

```text
ai-chatbot/
|-- Backend/
|   |-- app/                 # API, services, providers, schemas, storage
|   |-- scripts/             # Ingestion, tracing, backups, verification
|   |-- tests/
|   |-- migrations/
|   |-- evaluation/
|   |-- infra/               # PostgreSQL initialization
|   |-- run.py
|   |-- pyproject.toml
|   |-- uv.lock
|   |-- alembic.ini
|   |-- compose.yaml
|   |-- Dockerfile
|   |-- .env.example
|   |-- README.md
|-- frontend/                # Connected React UI and tests
|-- docs/                    # Shared guides, architecture and audits
|-- .github/                 # Repository CI
|-- .gitignore
|-- README.md
```

Local generated files such as `.venv`, `.cache`, `data`, `output`, and `tmp`
remain at the repository root. Backend settings load `Backend/.env`; cached
models, traces and backups continue using the existing root `.cache`. The
Compose project remains `ai-chatbot` to retain the existing database volume.

From the repository root on Windows:

```powershell
$env:UV_PROJECT_ENVIRONMENT = (Join-Path (Get-Location) ".venv")
cd Backend
# For a fresh checkout only: Copy-Item .env.example .env
uv sync --locked
docker compose up -d db
uv run alembic upgrade head
uv run python run.py
```

In a second terminal, from `frontend`, run `npm ci` and `npm run dev`, then open
<http://127.0.0.1:3000>. Its local proxy connects to the API on port 8000.
See [frontend setup and checks](frontend/README.md). Advanced admin and embedding
prototypes are preserved for later; the active UI uses live APIs.

The API is available at <http://127.0.0.1:8000/docs>. To run backend tests from
`Backend`, use `uv run pytest tests -q`. The environment setting above reuses
an existing root virtual environment. Without it, uv creates `Backend/.venv`.

See [backend setup and usage](Backend/README.md),
[frontend API contract](docs/frontend-api.md),
[operations](docs/operations.md), and the
[endpoint/architecture audit](docs/endpoint-architecture-audit-2026-10-12.md).

Local development uses the loopback workspace and Vite proxy. For a hosted private
preview, the repository-root Dockerfile serves React and FastAPI together behind
a workspace password. See [Render deployment](docs/render-deployment.md) for the
existing-service settings, optional Blueprint, secrets and verification steps.
All signed-in operators share administrator rights and documents; separate
customer accounts and document authorization are not implemented.
