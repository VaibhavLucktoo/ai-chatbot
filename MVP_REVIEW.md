# MVP review

## Scope and evidence

Reviewed the application modules, tests, configuration, scripts, database schema,
migrations, and project documentation. Existing edits to the LLM timeout and setup
documentation were preserved. Generated caches, third-party dependencies, and
private credentials are outside the source review. The lockfile's root dependency
metadata matches the project's 13 declared dependencies and Python requirement.

The supplied report correctly separates retrieval, generation, and deployment
concerns. The exact failed question and its original API output were not supplied
in this session. Tests below use the representative question **“Can I take leave
during probation?”** and the existing policy upload, `pdf24_merged.pdf`.

## Verified and fixed

| Issue | Evidence | Result |
| --- | --- | --- |
| Chat held a database connection during generation | Retrieval executes on an `AsyncSession`; the old path neither committed nor rolled back before awaiting the LLM | Chat now owns a short read transaction. A PostgreSQL integration test checks that the pool has zero checked-out connections when generation begins. The lower-level search helper still respects caller-owned transactions. |
| A model fallback could carry unrelated sources | The old RAG service returned every retrieved source regardless of answer text | Canonical insufficient-context answers now return an empty source list, including when retrieval is nonempty. |
| Fabricated or missing citation references were accepted | The old code validated source metadata but never parsed citations in the answer | Answers with missing, malformed, or out-of-range numeric references fail with HTTP 502. Only cited passages are returned, with numbering updated to match the response list. |
| Users could not select a particular upload | Search and chat had no document filter | Both accept optional `document_ids` containing 1–20 UUIDs. The filter is applied in SQL before ordering and limiting. Unknown IDs produce no matches; they never broaden the search. |
| Trusted rules and document text shared one user message | The old LLM request contained only a user message | Grounding rules now use the system role. The user message contains the question and passages. This separation is not a guarantee against prompt injection or hallucination. |
| Some unusable provider messages could be accepted | A text field could coexist with refusal or tool-call fields | Refusals, tool requests, incorrect roles, and incomplete generation are rejected. Generation has a 1,024-token output cap and temperature zero. |
| The LLM default differed from the documented local model | The default was `llama3.1`; setup downloads `llama3.2:1b-instruct-q4_K_M` | Defaults now agree with the local setup. Existing environment overrides still apply. |
| Valid PDF text containing NUL could never be stored | A generated PDF reproduced extraction of U+0000, which PostgreSQL text rejects | Extraction replaces null padding with spaces. Tests cover preservation of word boundaries and rejection of pages containing only null padding. |
| Failed answers lacked a reproducible trace | There was no way to collect exact inputs and provider output through the actual chat pipeline | `scripts/trace_rag.py` saves ranked text, distances, messages, model settings, raw provider response when available, raw answer, and final response or failure type. Tracing is explicitly invoked and local. |
| CLI help imported the ingestion/model stack | Under concurrent CPU inference, both ingestion `--help` checks exceeded their 30-second deadline | Database, tokenizer, and ingestion dependencies now load after argument parsing, only when ingestion is requested. |

Citation validation checks references. It does **not** establish that a cited
passage supports every claim, or that the answer covers all relevant clauses.

## Live policy diagnosis

The database contains relevant text in these passages:

- Pages 9 and 11: the leave policy states that employees on probation have no
  leave entitlement.
- Page 47: a separate clause states that manager-approved leave extends probation
  and describes consequences for unapproved or unplanned leave.

For the representative question, exact vector search returned pages
**11, 47, 9, 47, 49**. The first two chunks contain the relevant clauses in full.
This run therefore establishes that relevant evidence reached generation.

The original request format produced an uncited answer claiming a probation
period was “usually 90 days,” which was unsupported by the supplied passages.
The raw request and provider response are saved in
`.cache/mvp-audit/baseline.json`.

Initial checks of the revised flow exposed two further limits:

- One request exceeded its configured deadline. Ollama's log showed CPU prompt
  processing had reached 1,536 of 1,930 tokens; generation had not started.
  The loaded context capacity was 4,096 tokens and the log reported no truncation.
- With the model loaded, it produced an uncited fallback plus an explanation that
  overlooked the supplied restriction. A two-passage test returned a bare “no.”
  Both uncited outputs were rejected by the new validation.

These results identify generation reliability and CPU latency as demonstrated
problems. They do not establish the cause of the original, differently worded
request. The optional policy evaluation records expected pages, fallback behavior,
and the known invented duration; human review is still needed for grounding.

The final three-case live evaluation had **two failing cases and one passing
case**: the probation question returned an uncited false fallback; the
approved-leave question timed out; the unrelated question returned the correct
fallback with no sources. The trace records an effective generation timeout of
**60 seconds**, despite the example configuration using 120. Local `.env` values
were not changed. Traces are in `.cache/policy-evaluation/`.

Simpler prompt experiments did not establish a fix: one returned a false fallback
and another attached valid citation numbers to incorrectly attributed clauses.
Those formats were not adopted. The policy answer-quality issue remains open.

## Report claims that need care

- **Vector indexes:** search remains exact. An approximate index trades recall
  for speed; it is not a correction for a model ignoring relevant passages.
  [pgvector documentation](https://github.com/pgvector/pgvector/blob/master/README.md#indexing)
- **Sessions and connections:** the connection issue above was confirmed for this
  transaction path. Keeping a session object alive does not by itself prove a
  pooled connection is still checked out.
  [SQLAlchemy session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- **Stored PDFs:** stored chunk text supports re-embedding. Original files are
  needed for fresh extraction, faithful re-chunking, page inspection, or downloads.
- **Relevance thresholds:** no arbitrary distance cutoff was added. Select a
  threshold only after measuring both relevant retrieval and false fallbacks.
- **Architecture:** Core/ORM use, storage module placement, empty planned modules,
  and refusing startup without a required database are not automatic defects.

## Remaining boundaries

- The installed 1B model has not demonstrated reliable grounded policy answers.
  A passing code suite cannot establish model quality. Inspect the saved live
  traces and run the policy evaluation when changing models or prompts.
- The original failed question is still needed for an exact reproduction.
- The API is a local, single-user MVP. Authentication and document ownership
  checks are required before shared deployment. Document filtering is not an
  authorization boundary.
- Hard process termination or failed cleanup can leave an ingestion claim pending.
  Automatic job recovery, background workers, and multi-user admission controls
  remain deployment work. Existing retry and ordinary cancellation behavior is
  covered by integration tests.
- Larger `top_k` values can exceed a model server's context capacity. Prompt size,
  inference latency, and answer quality must be measured together; the embedding
  tokenizer is not the generation model's tokenizer.
- `Dockerfile` is an empty scaffold. Compose runs the database; application
  containerization remains unimplemented.

## Verification

Final automated run: **114 passed, 1 skipped, 216 subtests passed** in 40.58 seconds.
This includes PostgreSQL integration tests and actual cached FastEmbed inference;
database tests create and remove their own isolated schemas. The skipped test is
the separately invoked live policy evaluation.

```powershell
$env:RUN_DB_TESTS = "1"
$env:RUN_MODEL_TESTS = "1"
$env:HF_HUB_OFFLINE = "1"
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -W error::DeprecationWarning tests -q
```

The separate live policy evaluation had **2 failing cases out of 3** as described
above. It is not included in the passing code-test count. Private traces remain
under Git-ignored `.cache/` directories. `git diff --check` passed.

## Source inventory

| Area | Files reviewed |
| --- | --- |
| Startup/configuration | `app/main.py`, `app/core/config.py`, `run.py`, `.python-version`, `.env.example`, `.gitignore`, `compose.yaml`, `Dockerfile`, `pyproject.toml`, `uv.lock` root metadata |
| API | `app/api/v1/chat.py`, `documents.py`, `health.py`, `readiness.py`, `router.py` |
| Schemas | `app/schemas/chat.py`, `documents.py`, `health.py`, `readiness.py` |
| Retrieval/generation | `app/services/rag.py`, `retrieval.py`, `llm.py`, `app/prompts/rag.py` |
| Ingestion | `app/services/ingestion.py`, `chunking.py`, `document_hash.py`, `scripts/ingest.py` |
| Providers | `app/providers/base.py`, `documents.py`, `embeddings.py`, `fastembed_provider.py` |
| Persistence | `app/storage/db.py`, `documents.py`, `models.py`, `infra/postgres/init/001-vector.sql` |
| Migrations | `alembic.ini`, `migrations/env.py`, `script.py.mako`, `README`, `versions/7f7483ec3680_create_documents_and_document_chunks.py` |
| Existing tests | `tests/helpers.py`, `test_documents.py`, `test_ingestion.py`, `test_retrieval.py`, `test_llm.py`, `test_rag_service.py`, `test_rag.py`, `test_chat_api.py` |
| Documentation/evaluation | `README.md`, historical `NOTES.md`, `evaluation/questions.json` |
| New diagnostics/tests | `scripts/trace_rag.py`, `tests/test_trace_rag.py`, `tests/test_policy_live.py` |
| Empty scaffolds | Package `__init__.py` files; `app/providers/chat_model.py`, `models.py`; `app/services/chat.py`; `app/storage/vector_store.py` |

The local Q-Tickets PDF is an input fixture, not application source. Policy
diagnosis used the existing database passages; the original policy PDF was not
present under `data/documents`.
