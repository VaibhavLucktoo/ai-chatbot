from pathlib import Path
import json
import subprocess
import sys
import tomllib
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Flowable, KeepTogether,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/pdf'
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / 'ai_chatbot_project_analysis.pdf'
NAVY = colors.HexColor('#122C43')
TEAL = colors.HexColor('#007E87')
INK = colors.HexColor('#263B49')
MUTED = colors.HexColor('#596E7D')
PALE = colors.HexColor('#EDF5F7')
LINE = colors.HexColor('#D4E0E5')
AMBER = colors.HexColor('#996013')
for name, file in [('Body', 'calibri.ttf'), ('Bold', 'calibrib.ttf'), ('Italic', 'calibrii.ttf')]:
    pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + file))
pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Italic', boldItalic='Bold')

styles = {
    'body': ParagraphStyle('body', fontName='Body', fontSize=10.3, leading=14.2, textColor=INK, spaceAfter=7),
    'small': ParagraphStyle('small', fontName='Body', fontSize=8.8, leading=11.6, textColor=MUTED, spaceAfter=5),
    'cell': ParagraphStyle('cell', fontName='Body', fontSize=9.2, leading=12.1, textColor=INK),
    'headcell': ParagraphStyle('headcell', fontName='Bold', fontSize=9.3, leading=12, textColor=colors.white),
    'h1': ParagraphStyle('h1', fontName='Bold', fontSize=25, leading=29, textColor=NAVY, spaceAfter=13),
    'h2': ParagraphStyle('h2', fontName='Bold', fontSize=13.5, leading=17, textColor=TEAL, spaceBefore=10, spaceAfter=6),
    'kicker': ParagraphStyle('kicker', fontName='Bold', fontSize=9, leading=12, textColor=TEAL, spaceAfter=8),
    'cover': ParagraphStyle('cover', fontName='Bold', fontSize=37, leading=41, textColor=NAVY, spaceAfter=17),
    'deck': ParagraphStyle('deck', fontName='Body', fontSize=16, leading=22, textColor=MUTED, spaceAfter=16),
}
story = []
markdown = []
page_sections = []

def P(text, kind='body'):
    return Paragraph(text, styles[kind])

def para(text, kind='body'):
    story.append(P(text, kind))
    markdown.append(text.replace('<b>', '**').replace('</b>', '**').replace('<br/>', '\n'))

def head(text):
    story.append(P(text, 'h2'))
    markdown.append('\n## ' + text)

def page(number, title, subtitle=None):
    if story:
        story.append(PageBreak())
    page_sections.append((number, title))
    para(f'PROJECT REVIEW / {number:02d}', 'kicker')
    para(title, 'h1')
    if subtitle:
        para(subtitle)
    markdown.append('\n')

def table(headers, rows, widths):
    content = [[P(escape(str(h)), 'headcell') for h in headers]]
    content.extend([[P(str(c), 'cell') for c in row] for row in rows])
    t = Table(content, colWidths=widths, hAlign='LEFT', repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PALE]),
        ('LINEBELOW', (0, -1), (-1, -1), .6, LINE),
    ]))
    story.extend([t, Spacer(1, 9)])
    markdown.append('| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(['---'] * len(headers)) + ' |')
    markdown.extend('| ' + ' | '.join(str(c).replace('<br/>', '; ').replace('<b>', '').replace('</b>', '') for c in row) + ' |' for row in rows)

def note(label, text):
    t = Table([[P(f'<b>{label}</b><br/>{text}')]], colWidths=[499])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PALE),
        ('LINEBEFORE', (0, 0), (0, 0), 3, TEAL),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([t, Spacer(1, 10)])
    markdown.append(f'\n**{label}** {text}')

def sources(text):
    para('Evidence: ' + text, 'small')

class Diagram(Flowable):
    def __init__(self, mode):
        Flowable.__init__(self)
        self.mode = mode
        self.width = 499
        self.height = {'architecture': 265, 'ingestion': 197, 'chat': 202}[mode]

    def box(self, x, y, w, h, title, detail, fill=PALE):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(LINE)
        c.roundRect(x, y, w, h, 7, fill=1, stroke=1)
        a = Paragraph(title, ParagraphStyle('db', fontName='Bold', fontSize=11, leading=13, textColor=NAVY))
        a.wrap(w - 18, h)
        a.drawOn(c, x + 9, y + h - 24)
        b = Paragraph(detail, ParagraphStyle('dt', fontName='Body', fontSize=9, leading=11, textColor=INK))
        _, bh = b.wrap(w - 18, h)
        b.drawOn(c, x + 9, y + h - 29 - bh)

    def arrow(self, x1, y1, x2, y2):
        import math
        c = self.canv
        c.setStrokeColor(TEAL)
        c.setFillColor(TEAL)
        c.setLineWidth(1.4)
        c.line(x1, y1, x2, y2)
        angle = math.atan2(y2 - y1, x2 - x1)
        p = c.beginPath()
        p.moveTo(x2, y2)
        p.lineTo(x2 - 6 * math.cos(angle - .45), y2 - 6 * math.sin(angle - .45))
        p.lineTo(x2 - 6 * math.cos(angle + .45), y2 - 6 * math.sin(angle + .45))
        p.close()
        c.drawPath(p, stroke=0, fill=1)

    def draw(self):
        if self.mode == 'architecture':
            self.canv.scale(1, .88)
            self.box(123, 239, 253, 58, 'Client / Swagger UI / CLI', 'Upload PDF, search passages, ask a question')
            self.box(123, 150, 253, 63, 'FastAPI backend on the host', 'Routes + schemas + ingestion / retrieval / RAG')
            self.arrow(249, 239, 249, 214)
            self.box(0, 32, 155, 80, 'FastEmbed', 'Local BGE model<br/>384D vectors<br/>Worker thread + lock')
            self.box(172, 32, 155, 80, 'PostgreSQL + pgvector', 'Docker database<br/>Metadata, text, vectors<br/>Host port 5433')
            self.box(344, 32, 155, 80, 'Ollama / Llama', 'Separate local service<br/>HTTP chat completions<br/>Port 11434')
            self.arrow(168, 150, 78, 113)
            self.arrow(249, 150, 249, 113)
            self.arrow(330, 150, 421, 113)
        elif self.mode == 'ingestion':
            self.box(0, 131, 151, 62, '1. Accept &amp; identify', 'Validate PDF + SHA-256<br/>Look up duplicate')
            self.box(174, 131, 151, 62, '2. Extract &amp; claim', 'Page-aware text<br/>Reserve pending row')
            self.box(348, 131, 151, 62, '3. Chunk', '350-token windows<br/>40-token overlap')
            self.box(348, 22, 151, 62, '4. Embed', 'BGE, batches of 32<br/>Normalized 384D vectors')
            self.box(174, 22, 151, 62, '5. Persist atomically', 'All chunks + ready status<br/>One final transaction')
            self.box(0, 22, 151, 62, '6. Return metadata', 'ID, filename, counts<br/>Duplicate / retry flag')
            self.arrow(152, 162, 173, 162)
            self.arrow(326, 162, 347, 162)
            self.arrow(423, 130, 423, 85)
            self.arrow(347, 53, 326, 53)
            self.arrow(173, 53, 152, 53)
        elif self.mode == 'chat':
            for x, title, detail in [
                (0, '1. Question', 'Validate question<br/>Embed query with BGE'),
                (174, '2. Retrieve', 'Exact cosine ranking<br/>Ready + selected docs'),
                (348, '3. Build prompt', 'Release DB connection<br/>Rules + JSON passages')]:
                self.box(x, 135, 151, 63, title, detail)
            for x, title, detail in [
                (348, '4. Generate', 'Llama via HTTPX<br/>Non-streaming request'),
                (174, '5. Validate', 'Parse citation numbers<br/>Reject unusable output'),
                (0, '6. Answer + sources', 'Only cited passages<br/>Filename + page + IDs')]:
                self.box(x, 22, 151, 63, title, detail)
            self.arrow(152, 166, 173, 166)
            self.arrow(326, 166, 347, 166)
            self.arrow(423, 134, 423, 86)
            self.arrow(347, 53, 326, 53)
            self.arrow(173, 53, 152, 53)

# 1: cover
page_sections.append((1, 'Project snapshot'))
para('AI CHATBOT / ENGINEERING REVIEW / 01 OCTOBER 2026', 'kicker')
story.append(Spacer(1, 30))
para('Project architecture<br/>&amp; progress report', 'cover')
para('What is built, how it works,<br/>and what comes next.', 'deck')
story.append(Spacer(1, 15))
note('Current stage: local backend MVP', 'The full PDF-to-answer pipeline is implemented. Automated code checks pass in the default test mode. Reliable grounded answers and deployment readiness remain unfinished.')
table(['69 tracked files', '5 application endpoints', '97 tests passed'], [
    ['54 Python files reviewed', 'Upload, search, chat, health, ready', '216 subtests passed; 18 tests skipped'],
], [166, 167, 166])
head('The project in one paragraph')
para('AI Chatbot is a Python service that turns searchable PDFs into a knowledge base. It extracts text by page, splits text into smaller passages, stores their numerical representations in PostgreSQL, and retrieves relevant passages for a language model to answer questions with document and page references.')
head('Snapshot and review boundary')
para('Reviewed the working tree at commit <b>c916486</b> (30 September 2026), including the existing uncommitted edit to <b>.env.example</b>. The application version is <b>0.1.0</b>. This report was prepared on <b>1 October 2026</b>, Asia/Kolkata.')
para('All tracked project files were reviewed, including empty scaffolds, tests, migrations, and dependency metadata. Generated folders were classified; third-party packages and Git object storage were not audited line by line. Secret values from .env are omitted.', 'small')
sources('Source inspection; git ls-files and git log; current pytest run. Full inventory: pages 14-17.')

page(2, 'How far is it complete?', 'The core backend workflow is built. Its current acceptance gap is dependable answers on real documents, followed by the work required to make the service usable beyond a local developer setup.')
table(['Area', 'Current state', 'Meaning'], [
    ['Foundation &amp; database', 'Implemented', 'Startup lifecycle, async storage, migration, health and readiness.'],
    ['PDF ingestion', 'Implemented', 'Validation, extraction, chunking, embeddings, deduplication and retry.'],
    ['Vector retrieval', 'Implemented', 'Exact cosine search with optional document selection.'],
    ['RAG chat &amp; citations', 'Implemented', 'Generation, source references, fallback and provider-error mapping.'],
    ['Tests &amp; diagnostics', 'Implemented; partial live verification', 'Default suite passes today. Saved real-model evaluation has unresolved failures.'],
    ['Reliable policy answers', 'Open', 'Two of three saved live evaluation cases failed.'],
    ['Product interface', 'Absent', 'API docs and CLI exist; no dedicated chat frontend or conversation history.'],
    ['Shared deployment', 'Unfinished', 'No auth/ownership checks, app container, job recovery or CI pipeline.'],
], [124, 125, 250])
note('Why there is no completion percentage', 'The repository has no agreed full-product scope or weighted acceptance checklist. A single percentage would hide the difference between implemented code, model quality, and production readiness.')
head('Reading guide')
table(['Pages', 'What you will learn'], [
    ['3-6', 'Architecture, ingestion, chat flow and database design'],
    ['7-9', 'Technology versions, configuration and API specifications'],
    ['10-13', 'Verification, limitations, milestones and local operation'],
    ['14-17', 'File-by-file inventory and generated/local folder classification'],
], [62, 437])
sources('app/; tests/; Dockerfile; compose.yaml; MVP_REVIEW.md; saved policy-evaluation traces.')

page(3, 'System architecture', 'A layered Python application runs on the host machine. PostgreSQL runs in Docker, and Ollama is a separate service. FastEmbed loads inside the application process.')
story.append(Diagram('architecture'))
head('Responsibilities by layer')
table(['Layer', 'Responsibility'], [
    ['API + schemas', 'FastAPI routes validate input/output with Pydantic and translate failures into HTTP responses.'],
    ['Services', 'Coordinate extraction, chunking, retrieval, prompt construction, generation and citation validation.'],
    ['Providers', 'Parse PDFs and provide an embedding interface. The factory currently supports FastEmbed with one fixed BGE model.'],
    ['Storage', 'Own SQLAlchemy engines, sessions, document claims, atomic writes and pgvector search.'],
], [112, 387])
head('Important design choices')
para('<b>Short database work:</b> ingestion performs expensive parsing and inference outside database transactions. Chat ends its retrieval transaction before awaiting model generation.')
para('<b>Explicit integration:</b> the code coordinates RAG directly; no LangChain or LlamaIndex orchestration dependency is declared. The embedding abstraction is replaceable in design, but the database and adapter currently enforce one embedding space.')
para('<b>Local topology:</b> run.py binds the API to 127.0.0.1:8000. Compose publishes only PostgreSQL on localhost:5433. An alternate configured LLM URL sends questions and retrieved text to that provider.', 'small')
sources('run.py; app/main.py; app/api/v1/router.py; app/providers/base.py; app/storage/db.py; compose.yaml.')

page(4, 'PDF ingestion flow', 'Ingestion means converting an uploaded file into searchable text and vectors. The HTTP endpoint and the ingestion CLI share the same service.')
story.append(Diagram('ingestion'))
table(['Specification', 'Current implementation'], [
    ['Accepted input', 'application/pdf with a safe .pdf filename; maximum 255 filename characters.'],
    ['File / content limits', '10 MiB; 100 pages; 2,000,000 extracted characters; 1,000 chunks per document.'],
    ['Text extraction', 'pypdf strict parsing; one-based page numbers; blank pages skipped without renumbering. NUL characters become spaces.'],
    ['Chunking', '350 tokens with 40-token overlap inside each page. Original text slices are preserved; encoded chunks must fit a 480-token safety limit.'],
    ['Embedding / writing', 'Batches of 32 for inference; at most 256 rows per write batch. All final writes are committed together.'],
], [121, 378])
head('Document state and repeated uploads')
para('<b>New valid PDF:</b> pending -> ready on success, or pending -> failed on ordinary processing failure. Invalid extraction is rejected before reserving a database row.')
para('<b>Same bytes:</b> SHA-256 uniqueness prevents duplicate claims. Ready duplicates return the original ID and filename. Failed documents can retry with that same identity. A pending duplicate returns HTTP 409 and Retry-After: 5.')
note('Boundaries', 'Scanned/textless and encrypted PDFs are rejected; OCR is absent. Original PDF bytes are not retained by ingestion. A hard process kill can leave a pending claim requiring operator recovery.')
sources('app/providers/documents.py; app/services/{ingestion,chunking,document_hash}.py; app/storage/documents.py.')

page(5, 'Search and answer flow', 'Retrieval-augmented generation (RAG) gives the language model relevant document passages alongside the question. Embeddings find passages; the Llama model writes the answer.')
story.append(Diagram('chat'))
head('What search does')
para('The question becomes a normalized 384-dimensional BGE vector. SQL joins chunks to documents, selects only ready documents and the supported embedding space, and ranks by ascending cosine distance. Equal distances use chunk UUID order as a stable tie-breaker.')
para('The default <b>top_k is 5</b>; allowed values are 1-20. Optional <b>document_ids</b> selects 1-20 UUIDs before ranking and limiting. An unknown ID returns no matches. Search uses exact vector ranking; no approximate vector index, keyword hybrid search, reranker or relevance cutoff is implemented.')
head('How generation is controlled')
para('Trusted grounding rules are sent in a system message. A user message carries JSON-encoded passages and the question. HTTPX sends a non-streaming chat completion request with temperature 0 and a 1,024-token output limit. There is no automatic LLM retry.')
para('Empty retrieval returns the canonical insufficient-context answer without calling the model. A recognized model fallback also returns no sources. Otherwise the service checks citation syntax and range, keeps only cited sources, and renumbers citations to match the response list.')
note('References are checked; factual support still needs evaluation', 'A valid citation number does not prove that its passage supports a claim. The code does not score entailment or enforce a generation-token budget for the full prompt. Prompt instructions also do not guarantee resistance to instructions embedded in documents.')
sources('app/services/{retrieval,rag,llm}.py; app/prompts/rag.py; app/storage/documents.py.')

page(6, 'Database and persistence', 'PostgreSQL stores both relational metadata and vector embeddings. One document has many chunks. Alembic owns schema changes.')
table(['documents', 'Type / rule'], [
    ['id', 'UUID primary key'],
    ['filename', 'String(255), required'],
    ['content_sha256', 'String(64), required and unique; digest computed from exact file bytes'],
    ['page_count', 'Integer greater than zero'],
    ['status', 'pending, ready or failed; server default pending'],
    ['created_at', 'Timezone-aware timestamp; server default now()'],
], [140, 359])
table(['document_chunks', 'Type / rule'], [
    ['id / document_id', 'UUID primary key / foreign key to documents.id with cascading deletion'],
    ['chunk_index / page_number', 'Zero-based index / one-based page; both constrained to valid lower bounds'],
    ['content', 'Required nonblank text'],
    ['embedding_space', 'Fixed value: fastembed:bge-small-en-v1.5:384:l2:v1'],
    ['embedding', 'Required pgvector VECTOR(384)'],
    ['Unique position', '(document_id, chunk_index) must be unique'],
], [140, 359])
head('Integrity and transaction boundaries')
para('The database enforces types, foreign keys, uniqueness and basic checks. The ingestion service additionally validates finite, normalized vectors; Pydantic checks duplicate chunk indexes and page bounds within a batch. These application checks are separate from SQL constraints.')
para('The initial migration is <b>7f7483ec3680</b>. The Docker initialization SQL enables the vector extension on a fresh database volume. Startup checks connectivity and the extension, but does not apply migrations or confirm the deployed revision.')
note('What is retained', 'Metadata, extracted chunk text and vectors are stored. Original PDFs, chat sessions and message history have no storage model here. Stored text can be embedded again; fresh extraction and faithful re-chunking require the original file.')
sources('app/storage/{models,documents,db}.py; migrations/versions/7f7483ec3680_create_documents_and_document_chunks.py; infra/postgres/init/001-vector.sql.')

page(7, 'Technology and versions', 'Versions below are the installed project environment observed during this review, not claims about the latest available releases. pyproject.toml declares ranges; uv.lock records the dependency graph.')
table(['Technology', 'Observed version', 'Role'], [
    ['Python', '3.12.14', 'Runtime; project requires >=3.12; .python-version selects 3.12.'],
    ['FastAPI / Uvicorn', '0.141.1 / 0.53.0', 'HTTP API, OpenAPI documentation and ASGI serving.'],
    ['Pydantic / pydantic-settings', '2.13.5 / 2.15.0', 'Typed contracts and environment configuration.'],
    ['SQLAlchemy / Psycopg', '2.0.54 / 3.3.6', 'Async database layer and PostgreSQL driver.'],
    ['Alembic', '1.20.0', 'Database migration management.'],
    ['pgvector Python package', '0.5.0', 'Vector SQLAlchemy type and cosine-distance expressions.'],
    ['FastEmbed / ONNX Runtime', '0.8.1 / 1.30.0', 'Local embedding inference; ONNX Runtime is transitive.'],
    ['Hugging Face Hub / tokenizers', '1.33.0 / 0.23.2', 'Tokenizer assets and token-aware text windows.'],
    ['pypdf / python-multipart', '6.19.0 / 0.0.32', 'PDF text extraction and multipart upload parsing.'],
    ['HTTPX', '0.28.1', 'Async LLM HTTP client and test transports.'],
    ['pytest', '9.1.1', 'Test runner; tests also use unittest, mocks and AnyIO support.'],
], [166, 104, 229])
head('Models and infrastructure')
para('<b>Embedding model:</b> BAAI/bge-small-en-v1.5; 384 dimensions, L2 normalization, separate query and passage embedding methods. Model loading is lazy and cached; inference is serialized with a threading lock.')
para('<b>Generation model:</b> the code and example select llama3.2:1b-instruct-q4_K_M through an Ollama-compatible endpoint. This review did not verify a running model server or its installed version.')
para('<b>Database image:</b> compose.yaml pins pgvector/pgvector:0.8.6-pg16-trixie, representing PostgreSQL 16 with pgvector. Docker was not running during this review, so the actual running database version was not checked.')
para('Dependency footprint: 13 direct runtime dependencies, one declared development dependency, and 56 lockfile package records including the root project. No frontend package manifest is present.', 'small')
sources('pyproject.toml; uv.lock; .python-version; installed distribution metadata; compose.yaml; app/services/llm.py.')

page(8, 'Configuration and runtime limits', 'The application uses validated environment settings. Process environment variables take precedence over .env. Application/database settings are cached; LLM settings are loaded when preparing each request.')
table(['Setting group', 'Defaults / example values', 'Operational meaning'], [
    ['Application', 'APP_NAME=AI Chatbot<br/>APP_ENV=development', 'Environment is validated as development/test/production. No separate deployment profile is implemented.'],
    ['Database address', '127.0.0.1:5433', 'Required database name, username and password come from configuration; secret values are not reproduced here.'],
    ['Database pool', '5 connections; 0 overflow<br/>5-second pool wait', 'Limits simultaneous checked-out connections per application process.'],
    ['Database timeouts', '5-second connect<br/>5,000 ms statements<br/>8-second health deadline', 'Bounds connection setup, SQL execution and readiness checks.'],
    ['Embeddings', 'fastembed; BGE-small<br/>384 dimensions; 2 threads', 'Provider/model/dimensions must match the fixed schema. Threads can be configured from 1 to 32.'],
    ['Model endpoint', 'http://127.0.0.1:11434/v1', 'The client appends /chat/completions. Local example has an empty API key.'],
    ['Generation', 'Temperature 0<br/>1,024 output tokens<br/>5-second connect', 'Non-streaming request; no automatic retry; partial output is rejected.'],
], [114, 153, 232])
head('Timeout values currently differ')
table(['Location', 'LLM_TIMEOUT_SECONDS'], [
    ['app/services/llm.py fallback', '30 seconds when unset'],
    ['Current .env.example', '60 seconds (existing user edit preserved)'],
    ['README.md setup example', '120 seconds'],
    ['Saved 30 September policy traces', '60 seconds effective at the time of those runs'],
], [290, 209])
para('Allowed generation deadlines are greater than zero and at most 600 seconds. The report does not treat the example file as proof of the current private configuration. Increasing a deadline can allow slow inference to finish, but does not establish answer accuracy.', 'small')
sources('app/core/config.py; app/services/llm.py; .env.example; README.md; saved trace generation settings.')

page(9, 'API specification', 'Five application endpoints are mounted under /v1. FastAPI also supplies interactive documentation and an OpenAPI schema. There is no authentication on the application routes.')
table(['Endpoint', 'Input', 'Successful output'], [
    ['GET /v1/health', 'None', 'status=ok and a health message. Checks that the handler can respond.'],
    ['GET /v1/ready', 'None', 'status=ready when database access and vector extension check pass; otherwise 503.'],
    ['POST /v1/documents/upload', 'Multipart field: file', 'document_id, filename, page_count, chunk_count, status=ready, already_existed. New: 201; duplicate/retry: 200.'],
    ['POST /v1/documents/search', 'query; optional top_k and document_ids', 'query, top_k, matches, results. Results contain text, cosine_distance and document/page/chunk metadata.'],
    ['POST /v1/chat', 'question; optional top_k and document_ids', 'answer and sources. Each source has document_id, chunk_id, filename and page_number.'],
], [154, 122, 223])
head('Request contract')
para('Chat questions are trimmed, nonblank strings of at most <b>500 characters</b>. Search queries are trimmed and nonblank but have <b>no explicit maximum length</b>. top_k must be a strict integer from 1 to 20, default 5. document_ids accepts 1-20 UUIDs or may be omitted. Undeclared fields are rejected.')
head('Failure behavior')
table(['Operation', 'Important HTTP statuses'], [
    ['Upload', '409 pending duplicate; 413 oversized; 415 wrong media type; 422 invalid PDF/metadata/limits; 503 dependency failure; 500 unexpected error.'],
    ['Search', '422 schema failure; 400 service parameter failure; 503 storage unavailable; 500 embedding or internal failure.'],
    ['Chat', '422 invalid request; 429 provider rate limit; 502 unusable provider output/citations; 503 LLM unavailable; 504 timeout; 500 retrieval/storage/internal failure.'],
], [80, 419])
para('Readiness does not check migrations, document tables, embedding model availability or LLM response quality. The HTTP error handling generally avoids returning provider details, database credentials or private prompts.', 'small')
sources('app/api/v1/*.py; app/schemas/{chat,documents,health,readiness}.py.')

page(10, 'What was actually verified?', 'Code behavior and language-model quality need separate evidence. This page distinguishes this review\'s checks from older results stored in the repository.')
table(['Evidence', 'Result', 'Scope'], [
    ['Current default suite<br/>1 October 2026', '<b>97 passed</b><br/>18 skipped<br/>216 subtests passed', 'pytest with deprecation warnings treated as errors; completed in 20.71 seconds after permission-related rerun.'],
    ['Current static/config checks', 'Passed', 'Tracked source and dependency metadata inspected; docker compose config --quiet and git diff --check passed.'],
    ['Current runtime availability', 'Docker unavailable', 'Docker engine pipe was absent. Live PostgreSQL and real-model integration checks were not rerun.'],
    ['Prior integration result<br/>MVP_REVIEW.md', '114 passed<br/>1 skipped<br/>216 subtests passed', 'Recorded earlier with database and cached embedding inference enabled; historical evidence, not a new run today.'],
], [163, 112, 224])
head('Saved live policy evaluation: 30 September 2026')
table(['Case', 'Saved evidence', 'Outcome'], [
    ['Probation leave', 'Retrieved pages 11, 47, 9, 47, 49; LLMResponseError.', 'Failed answer validation. Existing review records an uncited false fallback.'],
    ['Manager-approved leave', 'Retrieved pages 47, 47, 10, 13, 11; LLMTimeoutError.', 'Generation exceeded the saved 60-second deadline.'],
    ['Unsupported question', 'Final response retained with zero sources.', 'Passed fallback case according to the existing review.'],
], [128, 194, 177])
para('The default run deliberately disables RUN_DB_TESTS, RUN_MODEL_TESTS and RUN_POLICY_TESTS. Its 18 skipped tests comprise 10 ingestion database tests, 7 retrieval database tests and 1 live-policy test; two database tests additionally require the real embedding model flag.')
note('Interpretation', 'The wiring, validation and failure paths have substantial automated coverage. Today\'s passing test count does not prove live database health, retrieval quality across a broad corpus, model grounding, load capacity or production availability.')
sources('tests/; current pytest output; MVP_REVIEW.md; .cache/policy-evaluation/*.json (metadata inspected without reproducing private passages).')

page(11, 'Current gaps and constraints', 'These findings follow from the source and the saved evaluation evidence. They define the present boundary of the project; no application changes were made for this report.')
table(['Priority / area', 'Finding and impact', 'Next acceptance check'], [
    ['High: answer quality', 'Saved real-policy cases show missed evidence and a timeout. Citation validity alone cannot confirm factual support.', 'Repeat representative questions with human-reviewed expected claims, citations and fallback behavior.'],
    ['High: shared access', 'No authentication, document ownership or tenant isolation. Any caller reaching the API can search ready documents.', 'Before shared use, verify that one user cannot read or select another user\'s documents.'],
    ['High: operations', 'Dockerfile is empty. Compose runs only the database. No CI workflow or deployment configuration is present.', 'Build and run the complete service from a clean checkout with a documented release check.'],
    ['Medium: ingestion recovery', 'Synchronous requests have no persistent job owner/lease or automatic stale-pending recovery.', 'Simulate a worker interruption and verify safe retry without partial ready documents.'],
    ['Medium: prompt capacity', 'top_k can reach 20; no generation-token budgeting or context-window enforcement exists.', 'Measure prompt tokens and latency with the actual generation tokenizer and server settings.'],
    ['Medium: search scale', 'Exact cosine search has no ANN index, hybrid retrieval or reranking. No search benchmark is included.', 'Measure corpus size, latency and retrieval recall before choosing an indexing change.'],
    ['Medium: observability', 'Error logs and opt-in local traces exist; no metrics, request correlation or broad evaluation dashboard.', 'Track upload/search/generation latency and failure rates without logging private passages by default.'],
    ['Product scope', 'No frontend, conversation memory, document list/delete/download APIs or OCR.', 'Agree which of these are required for the next user-facing milestone.'],
], [112, 207, 180])
para('Smaller cleanup items: reconcile the README/example timeout values; label historical NOTES.md sections clearly; decide whether unused scaffold modules should remain; align query-size limits across search and chat. These do not change the fact that the core pipeline is implemented.', 'small')
sources('Application routes and models; Dockerfile; repository inventory; app/services/rag.py; MVP_REVIEW.md.')

page(12, 'Milestones and next steps', 'Repository history shows a progression from infrastructure to ingestion, retrieval and chat. Remaining work should be accepted against observable behavior.')
table(['Date / commit', 'Milestone', 'Current reading'], [
    ['23 Sep / 31f2855', 'Initial FastAPI setup', 'Foundation scaffold established.'],
    ['24 Sep / 5f1d71b', 'Async database + embeddings', 'Configuration, schema and provider foundation implemented.'],
    ['28 Sep / f73fad2', 'PDF ingestion + vector search', 'Document indexing and retrieval implemented.'],
    ['29 Sep / 36b0b11', 'RAG API wiring', 'End-to-end application path implemented; live model checking remained.'],
    ['30 Sep / c916486', 'Chat/model fixes', 'Citation checks, transaction handling and diagnostic/evaluation work reflected in current source.'],
], [127, 150, 222])
head('Proposed order for the next milestones')
table(['Step', 'Work', 'Exit condition'], [
    ['1. Reliable local demo', 'Run services, align timeout guidance, evaluate real questions, inspect traces and tune the chosen model/prompt.', 'Reviewed answers capture relevant rules and exceptions, cite supporting pages and meet an agreed latency target.'],
    ['2. User workflow', 'Define the required frontend, document management and conversation behavior.', 'A user can upload, choose documents, ask questions and inspect sources without manual API assembly.'],
    ['3. Repeatable delivery', 'Complete app packaging, clean-checkout setup, CI checks and runtime dependency checks.', 'A documented installation/release procedure passes on a fresh environment.'],
    ['4. Shared service', 'Add identity/ownership, capacity controls, job recovery, backup/restore and monitoring.', 'Access-isolation, recovery and load tests pass for an agreed supported workload.'],
], [96, 207, 196])
note('Measure before scaling', 'Record retrieval recall, grounded-answer quality, fallback correctness, and upload/search/generation latency separately. No throughput target, latency SLA, coverage percentage or broad quality score is established by the current repository.')
sources('git log; README.md; NOTES.md; MVP_REVIEW.md. Next milestones are proposals based on observed gaps.')

page(13, 'Local operation and key terms', 'This is the operating sequence described by the repository. It was reviewed against source; the complete live stack was not started during this report task.')
table(['Order', 'Action', 'Expected result'], [
    ['1', 'Configure .env from the example for a new checkout; keep existing secrets. Run uv sync --locked.', 'Locked Python environment is available.'],
    ['2', 'Start Docker Desktop, then docker compose up -d db.', 'PostgreSQL becomes healthy on localhost:5433.'],
    ['3', 'Run uv run alembic upgrade head, then uv run alembic current.', 'Schema revision 7f7483ec3680 is installed.'],
    ['4', 'Run the configured Ollama server and ensure the exact LLM_MODEL is available.', 'The chat completion endpoint can serve the selected model.'],
    ['5', 'Start uv run python run.py.', 'API listens on localhost:8000 with a Windows-compatible event loop.'],
    ['6', 'Open /docs; check /v1/health and /v1/ready; upload a PDF and ask a question.', 'API, ingestion, retrieval and generation are checked in sequence.'],
], [42, 280, 177])
head('Useful developer entry points')
para('<b>Ingest:</b> uv run python -m scripts.ingest path/to/file.pdf<br/><b>Trace:</b> uv run python -m scripts.trace_rag "Your question" --document-id UUID<br/><b>Tests:</b> uv run pytest -W error::DeprecationWarning tests -v')
para('A trace records ranked chunks, messages, model settings, raw response when available, and the final result or failure type. Trace files contain document text. Normal API calls do not automatically write traces.')
head('Plain-language glossary')
table(['Term', 'Meaning in this project'], [
    ['Chunk / embedding', 'A small page passage / a 384-number representation used to compare meaning.'],
    ['Cosine distance / top_k', 'The retrieval ranking measure (lower is closer) / maximum number of passages returned.'],
    ['RAG / grounding', 'Retrieval followed by generation / answering from the supplied evidence.'],
    ['Migration / transaction', 'A versioned schema change / database changes that commit or roll back together.'],
    ['MVP / readiness', 'An initial working product scope / the current database-dependency health check.'],
], [145, 354])
sources('README.md; run.py; scripts/ingest.py; scripts/trace_rag.py; migrations/env.py.')

# Full tracked inventory: each of the 69 paths is explicitly mapped.
inventory = {}
def inv(path, role):
    assert path not in inventory, path
    inventory[path] = role
    return [path, role]

page(14, 'File inventory: root and infrastructure', 'Every tracked file is accounted for in pages 14-17. Empty package markers are listed separately from unfinished feature scaffolds.')
rows = [
    inv('.env.example', 'Sample database, embedding and LLM settings; current timeout is 60 seconds.'),
    inv('.gitignore', 'Excludes secrets, virtual environment, caches, compiled files and local PDFs.'),
    inv('.python-version', 'Pins the selected Python minor version to 3.12.'),
    inv('pyproject.toml', 'Project v0.1.0, Python requirement, 13 runtime dependencies and pytest dev group.'),
    inv('uv.lock', 'Resolved dependency graph with 56 package records; root metadata matches the manifest.'),
    inv('README.md', 'Current setup, API usage, limits, tests, tracing and MVP boundary documentation.'),
    inv('NOTES.md', 'Historical development log; early unfinished-state descriptions are superseded by later code.'),
    inv('MVP_REVIEW.md', 'Prior audit, implemented fixes, recorded integration results and open live-model failures.'),
    inv('run.py', 'Local Uvicorn launcher and explicit Windows selector event loop.'),
    inv('compose.yaml', 'PostgreSQL/pgvector service, localhost binding, persistent volume and health check.'),
    inv('Dockerfile', '<b>Empty scaffold.</b> Application container image is not implemented.'),
    inv('alembic.ini', 'Migration location, path handling and logging; actual DB URL is built in env.py.'),
    inv('infra/postgres/init/001-vector.sql', 'Creates vector extension when a fresh database volume initializes.'),
    inv('migrations/README', 'Generic single-database migration note.'),
    inv('migrations/env.py', 'Online/offline migrations, settings-based URL and explicit pgvector type rendering.'),
    inv('migrations/script.py.mako', 'Template for new migration scripts.'),
    inv('migrations/versions/7f7483ec3680_create_documents_and_document_chunks.py', 'Initial reversible migration creating document/chunk tables and constraints.'),
]
table(['File', 'Role / status'], rows, [227, 272])

page(15, 'File inventory: API and contracts', 'The app directory contains the executable backend. Routes use schemas to make accepted requests and returned responses explicit.')
table(['File', 'Role / status'], [
    inv('app/main.py', 'FastAPI factory, /v1 registration, startup database check and shutdown cleanup.'),
    inv('app/core/config.py', 'Cached application/database/embedding settings, secret handling and limits.'),
    inv('app/api/v1/router.py', 'Combines health, readiness, document and chat routers.'),
    inv('app/api/v1/health.py', 'GET liveness response.'),
    inv('app/api/v1/readiness.py', 'GET readiness response with HTTP 503 on failed database check.'),
    inv('app/api/v1/documents.py', 'Bounded upload reading, input validation, ingestion and search HTTP handlers.'),
    inv('app/api/v1/chat.py', 'Chat endpoint, request-scoped session dependency and LLM/storage error mapping.'),
    inv('app/schemas/health.py', 'Typed ok health response and message.'),
    inv('app/schemas/readiness.py', 'Typed ready/not_ready response.'),
    inv('app/schemas/documents.py', 'Filename rules, upload/search responses, document filters and ingestion batch contracts.'),
    inv('app/schemas/chat.py', 'Strict question, top_k, source metadata and chat response contracts.'),
    inv('app/prompts/rag.py', 'Grounding system prompt and canonical insufficient-context answer.'),
], [207, 292])
head('Empty Python package markers')
markers = ['app/__init__.py', 'app/api/__init__.py', 'app/api/v1/__init__.py', 'app/core/__init__.py', 'app/prompts/__init__.py', 'app/providers/__init__.py', 'app/schemas/__init__.py', 'app/services/__init__.py', 'app/storage/__init__.py']
for path in markers:
    inv(path, 'Empty package marker; no runtime behavior.')
para('<br/>'.join(markers), 'small')
para('These nine empty __init__.py files define package boundaries. Their emptiness does not indicate missing feature implementation.', 'small')

page(16, 'File inventory: processing and storage', 'Feature behavior lives in these implementations. Some originally planned module names remain empty; their working equivalents are identified below.')
table(['File', 'Role / status'], [
    inv('app/providers/base.py', 'Abstract embedding interface: query, documents, dimensions and space identifier.'),
    inv('app/providers/documents.py', 'PDF envelope checks, strict extraction, limits and page-aware text structures.'),
    inv('app/providers/embeddings.py', 'Cached provider factory; enforces supported model and dimensions.'),
    inv('app/providers/fastembed_provider.py', 'Lazy local inference, thread offloading/lock and normalized vector validation.'),
    inv('app/providers/chat_model.py', '<b>Empty scaffold.</b> Actual LLM client is app/services/llm.py.'),
    inv('app/providers/models.py', '<b>Empty scaffold.</b> Database models live in app/storage/models.py.'),
    inv('app/services/document_hash.py', 'SHA-256 fingerprint for exact uploaded bytes.'),
    inv('app/services/chunking.py', 'BGE tokenizer loading and page-based overlapping text windows.'),
    inv('app/services/ingestion.py', 'Deduplication flow, extraction, claims, embeddings, publish and failure cleanup.'),
    inv('app/services/retrieval.py', 'Query normalization, provider/vector checks and storage search orchestration.'),
    inv('app/services/llm.py', 'Independent LLM settings, HTTPX request, deadline, completion parsing and errors.'),
    inv('app/services/rag.py', 'Short retrieval transaction, JSON prompt, generation, traces and citation validation.'),
    inv('app/services/chat.py', '<b>Empty scaffold.</b> Working chat coordination is in app/services/rag.py.'),
    inv('app/storage/db.py', 'Async engine, pool/timeouts, session/transaction contexts and readiness.'),
    inv('app/storage/models.py', 'Typed documents/chunks tables, fixed embedding contract and constraints.'),
    inv('app/storage/documents.py', 'Deduplication claims, retry, atomic completion, failure cleanup and exact search SQL.'),
    inv('app/storage/vector_store.py', '<b>Empty scaffold.</b> Vector query implementation is in app/storage/documents.py.'),
], [222, 277])

page(17, 'File inventory: tests and local artifacts', 'Tests cover parsing, contracts, storage integration, provider handling and RAG behavior. The live quality evaluation is separately enabled.')
table(['File', 'Role / status'], [
    inv('scripts/ingest.py', 'Bounded-file ingestion CLI; supports module and direct-file invocation.'),
    inv('scripts/trace_rag.py', 'Explicit local trace command using the actual RAG pipeline.'),
    inv('evaluation/questions.json', 'Three policy/fallback cases with expected pages and human review criteria.'),
    inv('tests/__init__.py', 'Test package marker with a short module docstring.'),
    inv('tests/helpers.py', 'Generated PDF fixtures, stub embeddings, small tokenizer and Windows async runner.'),
    inv('tests/test_documents.py', '19 tests: extraction, limits, chunking, filenames, CLI and upload statuses.'),
    inv('tests/test_ingestion.py', '10 tests: DB claims, retries, cancellation, rollback and optional real inference.'),
    inv('tests/test_retrieval.py', '27 tests: filters, vector checks, exact ranking, transactions and optional real retrieval.'),
    inv('tests/test_llm.py', '20 tests: configuration, request format, response parsing, deadlines and cancellation.'),
    inv('tests/test_rag_service.py', '18 tests: prompts, citation checks, fallback, traces and retrieval/generation wiring.'),
    inv('tests/test_chat_api.py', '15 tests: API contract, error mapping, session cleanup and OpenAPI.'),
    inv('tests/test_rag.py', '3 API/service integration tests with mocked retrieval and model responses.'),
    inv('tests/test_trace_rag.py', '2 tests: retained failure evidence and redacted exception details.'),
    inv('tests/test_policy_live.py', '1 opt-in test method covering all 3 real policy evaluation cases.'),
], [204, 295])
head('Local and generated folders')
para('<b>.env:</b> local configuration; key names checked, values omitted. <b>data/documents/:</b> ignored 28-page Q-Tickets manual (1,911,119 bytes), an input fixture. <b>.cache/:</b> FastEmbed assets, prior audit traces and policy evaluation traces; metadata reviewed selectively.', 'small')
para('<b>.venv/:</b> installed third-party runtime, inspected through package metadata. <b>.git/:</b> version history and tracking metadata. <b>.pytest_cache/ and __pycache__/:</b> generated test/bytecode artifacts. <b>pytest-cache-files-r3kf4dgu/:</b> inaccessible temporary cache directory; contents not reviewed.', 'small')
para('<b>output/pdf/ and tmp/pdfs/:</b> created by this task for the final report, editable companion, generation script, rendering dependency and visual verification files. They are documentation tooling, not application architecture.', 'small')

tracked = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()
assert set(inventory) == set(tracked), {'missing': sorted(set(tracked)-set(inventory)), 'extra': sorted(set(inventory)-set(tracked))}

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(48, 43, A4[0]-48, 43)
    canvas.setFont('Body', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(48, 29, 'AI CHATBOT  |  SOURCE-BASED REVIEW  |  01 OCT 2026')
    canvas.drawRightString(A4[0]-48, 29, f'{doc.page:02d}')
    if doc.page <= len(page_sections):
        label = page_sections[doc.page-1][1]
        key = 'page' + str(doc.page)
        canvas.bookmarkPage(key)
        canvas.addOutlineEntry(label, key, 0, False)
    canvas.restoreState()

doc = SimpleDocTemplate(str(PDF), pagesize=A4, rightMargin=48, leftMargin=48,
                        topMargin=43, bottomMargin=59, title='AI Chatbot - Architecture and Progress Report',
                        author='Project Engineering Review', subject='Source analysis, architecture, specifications and completion status')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
(OUT / 'ai_chatbot_project_analysis.md').write_text('\n\n'.join(markdown) + '\n', encoding='utf-8')
(ROOT / 'tmp/pdfs/inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
print(PDF)
print('Inventory verified:', len(inventory), 'tracked files')
