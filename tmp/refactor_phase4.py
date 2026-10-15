"""Apply the last structural phase while copying SQL blocks verbatim."""
import ast
from pathlib import Path
import textwrap

ROOT = Path("app")


def function(source, name):
    return next(node for node in ast.parse(source).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)


def segment(source, node):
    return "".join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])


def lift_query(source, name, repository_name, parameters, return_expression, call, *, prefix="", substitutions=()):
    node = function(source, name)
    attempt = next(item for item in node.body if isinstance(item, ast.Try)
                   and any(isinstance(child, ast.AsyncWith) for child in item.body))
    block = "".join(source.splitlines(keepends=True)[attempt.body[0].lineno - 1:attempt.body[-1].end_lineno])
    moved = textwrap.indent(textwrap.dedent(block), "    ")
    moved = moved.replace("request.app.state.database", "database")
    for old, new in substitutions:
        moved = moved.replace(old, new)
    repository = f"async def {repository_name}({parameters}):\n" + prefix + moved + f"    return {return_expression}\n\n\n"
    assert source.count(block) == 1
    return source.replace(block, "        " + call + "\n", 1), repository


# Catalog queries retain the original SQL expressions and transaction scopes.
path = ROOT / "api/v1/document_catalog.py"
catalog = path.read_text(encoding="utf-8")
metadata = segment(catalog, function(catalog, "metadata_query"))
catalog = catalog.replace(metadata, "", 1)
repository = '''"""Document catalog and assistant-scope queries with short transactions."""
from sqlalchemy import func, select

from app.services.configuration_errors import AssistantNotFound
from app.storage.models import Assistant, AssistantDocument, Document, DocumentChunk, ProviderConnection


''' + metadata + "\n\n\n"
filters = '''    filters = []
    if status is not None:
        filters.append(Document.status == status)
    if active is not None:
        filters.append(Document.active == active)
'''
catalog, moved = lift_query(catalog, "list_documents", "list_documents", "database, *, limit, offset, status=None, active=None", "total, rows",
    "total, rows = await catalog_storage.list_documents(request.app.state.database, limit=limit, offset=offset, status=status, active=active)", prefix=filters)
catalog = catalog.replace(filters, "", 1)
repository += moved
for name, parameters, arguments in (
    ("get_document", "database, document_id", "document_id"),
    ("download_source", "database, document_id", "document_id"),
    ("get_source_chunk", "database, document_id, chunk_id", "document_id, chunk_id"),
):
    catalog, moved = lift_query(catalog, name, name, parameters, "row",
        f"row = await catalog_storage.{name}(request.app.state.database, {arguments})")
    repository += moved
catalog = catalog.replace("from sqlalchemy import func, select\n", "")
catalog = catalog.replace("from app.storage.models import Document, DocumentChunk", '''from app.storage import document_catalog as catalog_storage
# Deprecated helper location; retain compatibility for downstream imports.
from app.storage.document_catalog import metadata_query as metadata_query''')
path.write_text(catalog, encoding="utf-8")

path = ROOT / "api/v1/assistants.py"
assistants = path.read_text(encoding="utf-8")
node = function(assistants, "assistant_documents")
query = next(item for item in node.body if isinstance(item, ast.AsyncWith))
block = segment(assistants, query)
repository += "async def assistant_documents(database, assistant_id, *, limit, offset):\n" + block.replace("request.app.state.database", "database") + "    return total, rows\n"
assistants = assistants.replace(block, "    total, rows = await catalog_storage.assistant_documents(request.app.state.database, assistant_id, limit=limit, offset=offset)\n", 1)
assistants = assistants.replace("from sqlalchemy import func, select\n", "")
assistants = assistants.replace("from app.api.v1.document_catalog import metadata_query\n", "")
assistants = assistants.replace("from app.storage.models import Assistant, AssistantDocument, Document, ProviderConnection", "from app.storage import document_catalog as catalog_storage")
assistants = assistants.replace("from app.services.assistants import AssistantNotFound, ", "from app.services.assistants import ")
path.write_text(assistants, encoding="utf-8")
(ROOT / "storage/document_catalog.py").write_text(repository, encoding="utf-8")

# Diagnostic document queries continue using the caller-owned AsyncSession.
path = ROOT / "api/v1/admin.py"
admin = path.read_text(encoding="utf-8")
node = function(admin, "admin_documents")
block = segment(admin, next(item for item in node.body if isinstance(item, ast.AsyncWith)))
(ROOT / "storage/admin.py").write_text('''"""Read-only SQL for local operator document diagnostics."""
from sqlalchemy import func, select

from app.storage.models import Document, DocumentChunk


async def read_admin_documents(db, *, limit, offset):
''' + block + "    return total, rows\n", encoding="utf-8")
admin = admin.replace(block, "    total, rows = await read_admin_documents(db, limit=limit, offset=offset)\n", 1)
admin = admin.replace("from sqlalchemy import func, select\n", "")
admin = admin.replace("from app.storage.models import Document, DocumentChunk", "from app.storage.admin import read_admin_documents")
path.write_text(admin, encoding="utf-8")

# Durable job SQL and activation/deletion SQL leave the HTTP layer.
path = ROOT / "api/v1/jobs.py"
jobs = path.read_text(encoding="utf-8")
jobs, enqueue = lift_query(jobs, "submit_job", "enqueue_document", "database, *, filename, digest, data", "row",
    "row = await job_storage.enqueue_document(request.app.state.database, filename=metadata.filename, digest=digest, data=data)",
    substitutions=(("metadata.filename", "filename"),))
jobs, lookup = lift_query(jobs, "job_status", "job_status", "database, document_id", "row",
    "row = await job_storage.job_status(request.app.state.database, document_id)")
(ROOT / "storage/document_jobs.py").write_text('''"""Durable upload claims and status queries."""
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.storage.models import Document


''' + enqueue + lookup, encoding="utf-8")
jobs = jobs.replace("from uuid import UUID, uuid4", "from uuid import UUID")
jobs = jobs.replace("from sqlalchemy import func, select, update\n", "").replace("from sqlalchemy.dialects.postgresql import insert\n", "")
jobs = jobs.replace("from app.storage.models import Document", "from app.storage import document_jobs as job_storage")
path.write_text(jobs, encoding="utf-8")

path = ROOT / "api/v1/document_lifecycle.py"
lifecycle = path.read_text(encoding="utf-8")
lifecycle, activation = lift_query(lifecycle, "activate_document", "set_document_activation", "database, document_id, active", "result.rowcount",
    "rowcount = await lifecycle_storage.set_document_activation(request.app.state.database, document_id, payload.active)", substitutions=(("payload.active", "active"),))
lifecycle, deletion = lift_query(lifecycle, "delete_document", "delete_document", "database, document_id", "result.rowcount",
    "rowcount = await lifecycle_storage.delete_document(request.app.state.database, document_id)")
(ROOT / "storage/document_lifecycle.py").write_text('''"""Document activation and deletion transactions."""
from sqlalchemy import delete, update

from app.storage.models import Document


''' + activation + deletion, encoding="utf-8")
lifecycle = lifecycle.replace("from sqlalchemy import delete, update\n", "")
lifecycle = lifecycle.replace("from app.storage.models import Document", "from app.storage import document_lifecycle as lifecycle_storage")
lifecycle = lifecycle.replace("if result.rowcount != 1:", "if rowcount != 1:")
path.write_text(lifecycle, encoding="utf-8")

# Shared upload helpers prevent jobs importing another endpoint module.
path = ROOT / "api/v1/documents.py"
documents = path.read_text(encoding="utf-8")
start, end = documents.index("READ_SIZE ="), documents.index("@router.post(")
helpers = documents[start:end]
(ROOT / "api/common/uploads.py").write_text('''"""Bounded HTTP upload reads and PDF envelope error mapping."""
from fastapi import HTTPException, UploadFile, status

from app.providers.documents import MAX_PDF_BYTES, PDFExtractionError, PDFTooLargeError, validate_pdf_bytes


''' + helpers, encoding="utf-8")
documents = documents[:start] + documents[end:]
documents = documents.replace("    MAX_PDF_BYTES,\n", "").replace("    validate_pdf_bytes,\n", "")
documents = documents.replace("from app.providers.documents import (", '''# Deprecated helper locations; preserve the original callable identities.
from app.api.common.uploads import (
    READ_SIZE as READ_SIZE,
    read_limited_pdf as read_limited_pdf,
    validate_pdf_envelope as validate_pdf_envelope,
)
from app.providers.documents import (''')
path.write_text(documents, encoding="utf-8")
path = ROOT / "api/v1/jobs.py"
path.write_text(path.read_text(encoding="utf-8").replace("from app.api.v1.documents import read_limited_pdf, validate_pdf_envelope", "from app.api.common.uploads import read_limited_pdf, validate_pdf_envelope"), encoding="utf-8")
path = Path("tests/test_documents.py")
path.write_text(path.read_text(encoding="utf-8").replace("app.api.v1.documents.MAX_PDF_BYTES", "app.api.common.uploads.MAX_PDF_BYTES"), encoding="utf-8")

# Move existing schema classes without changing their definitions or titles.
schema_path = ROOT / "schemas/documents.py"
document_schemas = schema_path.read_text(encoding="utf-8")
for filename, name in (("jobs.py", "DocumentJobResponse"), ("document_lifecycle.py", "DocumentActivation")):
    path = ROOT / "api/v1" / filename
    source = path.read_text(encoding="utf-8")
    node = next(item for item in ast.parse(source).body if isinstance(item, ast.ClassDef) and item.name == name)
    definition = segment(source, node)
    document_schemas += "\n\n" + definition
    source = source.replace(definition, "", 1)
    source = source.replace("from pydantic import BaseModel, ValidationError", "from pydantic import ValidationError")
    source = source.replace("from pydantic import BaseModel, ConfigDict, StrictBool\n", "")
    source = source.replace("from app.storage import", f"# Deprecated schema location; retain compatibility for downstream imports.\nfrom app.schemas.documents import {name} as {name}\nfrom app.storage import", 1)
    path.write_text(source, encoding="utf-8")
document_schemas = document_schemas.replace("    StringConstraints,\n", "    StringConstraints,\n    StrictBool,\n")
schema_path.write_text(document_schemas, encoding="utf-8")

path = ROOT / "api/v1/metrics.py"
metrics = path.read_text(encoding="utf-8")
node = next(item for item in ast.parse(metrics).body if isinstance(item, ast.ClassDef) and item.name == "AnalyticsResponse")
definition = segment(metrics, node)
(ROOT / "schemas/metrics.py").write_text('''"""Persisted analytics response contract."""
from pydantic import BaseModel, Field


''' + definition, encoding="utf-8")
metrics = metrics.replace(definition, "", 1).replace("from pydantic import BaseModel, Field\n", "")
metrics = metrics.replace("from app.storage.metrics import read_metrics", '''# Deprecated schema location; retain compatibility for downstream imports.
from app.schemas.metrics import AnalyticsResponse as AnalyticsResponse
from app.schemas.admin import AdminSessionResponse
from app.storage.metrics import read_metrics''')
metrics = metrics.replace('@router.get("/session", responses=', '@router.get("/session", response_model=AdminSessionResponse, responses=')
path.write_text(metrics, encoding="utf-8")

(ROOT / "schemas/admin.py").write_text('''"""Typed local administrator responses, preserving existing JSON values."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.chat import ChatResponse, ClarificationResponse


class AdminSessionResponse(BaseModel):
    token: str


class AdminStatusResponse(BaseModel):
    database_ready: bool
    model: str
    temperature: float
    max_output_tokens: int
    generation_timeout_seconds: float
    mode: Literal["local"]
    conversation_memory: bool


class AdminDocument(BaseModel):
    id: str
    filename: str
    page_count: int
    status: str
    # The existing encoder emits +00:00, whereas datetime models emit Z.
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    active: bool
    processing_metadata: Any
    chunk_count: int
    lease_active: bool | None
    recoverable: bool


class AdminDocumentListResponse(BaseModel):
    items: list[AdminDocument]
    total: int
    limit: int
    offset: int


class AdminChatResponse(BaseModel):
    status: Literal["clarification_required", "insufficient_context", "answered"]
    response: ChatResponse | ClarificationResponse
    diagnostics: dict[str, Any]
''', encoding="utf-8")
(ROOT / "schemas/providers.py").write_text('''"""Typed provider listing, discovery and connection-test responses."""
from typing import Literal

from pydantic import BaseModel


class ProviderDescriptor(BaseModel):
    id: str
    name: str


class ProviderListResponse(BaseModel):
    items: list[ProviderDescriptor]


class ProviderModelListResponse(BaseModel):
    items: list[str]


class ProviderTestResponse(BaseModel):
    status: Literal["ok"]
    provider: str
    model: str
''', encoding="utf-8")
path = ROOT / "api/v1/admin.py"
admin = path.read_text(encoding="utf-8")
admin = admin.replace("from app.schemas.chat import", "from app.schemas.admin import AdminStatusResponse, AdminDocumentListResponse, AdminChatResponse\nfrom app.schemas.chat import", 1)
for method, endpoint, model in (("get", "/status", "AdminStatusResponse"), ("get", "/documents", "AdminDocumentListResponse"), ("post", "/chat", "AdminChatResponse")):
    admin = admin.replace(f'@router.{method}("{endpoint}")', f'@router.{method}("{endpoint}", response_model={model})')
path.write_text(admin, encoding="utf-8")
path = ROOT / "api/v1/assistants.py"
assistants = path.read_text(encoding="utf-8")
assistants = assistants.replace("from app.schemas.documents import", "from app.schemas.providers import ProviderListResponse, ProviderModelListResponse, ProviderTestResponse\nfrom app.schemas.documents import", 1)
for method, endpoint, model in (("get", "/providers", "ProviderListResponse"), ("post", "/connections/models", "ProviderModelListResponse"), ("get", "/connections/{connection_id}/models", "ProviderModelListResponse"), ("post", "/connections/test", "ProviderTestResponse")):
    assistants = assistants.replace(f'@admin_router.{method}("{endpoint}")', f'@admin_router.{method}("{endpoint}", response_model={model})')
path.write_text(assistants, encoding="utf-8")
path = ROOT / "schemas/widgets.py"
path.write_text(path.read_text(encoding="utf-8") + '''

class WidgetPassageResponse(WidgetSchema):
    id: UUID
    document_id: UUID
    filename: str
    page_number: int
    chunk_index: int
    # Return exactly the stored text; do not strip whitespace during serialization.
    content: str
''', encoding="utf-8")
path = ROOT / "api/v1/widget_visitor.py"
source = path.read_text(encoding="utf-8")
source = source.replace("from app.schemas.widgets import VisitorChat, VisitorSession, VisitorStart", "from app.schemas.widgets import VisitorChat, VisitorSession, VisitorStart, WidgetPassageResponse")
source = source.replace('@router.get("/{widget_id}/sessions/{session_id}/passages/{chunk_id}")', '@router.get("/{widget_id}/sessions/{session_id}/passages/{chunk_id}", response_model=WidgetPassageResponse)')
path.write_text(source, encoding="utf-8")
path = ROOT / "api/v1/health.py"
path.write_text(path.read_text(encoding="utf-8").replace('tags=["Health"]', 'tags=["health"]'), encoding="utf-8")

# Establish project-owned correctness/import lint rules rather than user config.
path = Path("pyproject.toml")
path.write_text(path.read_text(encoding="utf-8") + '''

[tool.ruff]
target-version = "py312"
cache-dir = "../.cache/ruff"
extend-exclude = ["pytest-cache-files-*"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F"]
''', encoding="utf-8")

# Mechanical cleanup of pre-existing lint findings; keep test calls/assertions.
for filename in ("test_conversation.py", "test_widget_storage.py"):
    path = Path("tests") / filename
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        if "; " in line and ("assert_not_awaited(); " in line or "app.state.database = self.database; " in line):
            indentation = line[:len(line) - len(line.lstrip())]
            lines.append(("\n" + indentation).join(line.rstrip("\n").split("; ")) + "\n")
        else:
            lines.append(line)
    path.write_text("".join(lines), encoding="utf-8")
path = Path("tests/test_ingestion.py")
path.write_text(path.read_text(encoding="utf-8").replace("            job = await client.post(", "            await client.post("), encoding="utf-8")
path = Path("tests/test_retrieval.py")
source = path.read_text(encoding="utf-8")
node = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.AsyncFunctionDef) and node.name == "test_storage_rejects_bad_vectors_without_a_connection")
block = segment(source, node)
source = source.replace(block, block.replace("for values, top_k", "for bad_values, top_k").replace("object(), values, top_k", "object(), bad_values, top_k"), 1)
path.write_text(source, encoding="utf-8")
print("Phase 4: SQL extracted without rewriting queries; response models, tags and project lint configuration added.")
