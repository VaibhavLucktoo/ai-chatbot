# Backend readiness — 12 October 2026

The backend is ready for the next stage of local frontend development. The
supported deployment remains one trusted operator on loopback. Public users,
tenant ownership, remote hosting, OCR, and conversation memory are outside this
release's scope.

## Changes

- Fixed the chat schema import failure and restored `top_k` in document
  clarification responses.
- Added paginated, filtered document catalog and detail endpoints, original PDF
  downloads, and citation passage inspection. Metadata queries do not return
  PDF bytes or embeddings. Downloads handle legacy missing sources explicitly;
  citation inspection checks both document and chunk IDs.
- Improved instructions for restrictions, approval clauses, and combined
  questions. Added a single bounded draft-review call for compound questions.
  Review errors propagate instead of returning an unchecked draft. Both calls
  use the existing generation controls and total chat deadline.
- Expanded live policy checks for the demonstrated incorrect entitlement and
  omitted approved-leave consequence. Live evaluations can be paced using
  `POLICY_EVALUATION_INTERVAL_SECONDS` to respect provider quotas.
- Documented the frontend contract in [frontend-api.md](frontend-api.md), and
  corrected outdated container documentation.

## Verification

- Full PostgreSQL and real cached embedding suite, with deprecation warnings
  treated as errors: **184 passed, 1 skipped, 337 subtests passed**. The skip is
  the separately enabled live policy suite.
- Separate live policy evaluation: **1 passed, 4 subtests passed**. Checked
  probation restrictions, approved-leave consequences, the combined question,
  and canonical unsupported-question fallback with no sources.
- Startup, pinned embedding warmup, health, readiness, and admin checks passed.
- Migration revision `c52f31faa4ec` is current; Alembic reports no pending schema
  differences. This change requires no new migration.
- HTTP checks verified health, readiness, catalog/detail, and citation access.
- Source-scoped whitespace checks passed.

The local API runs at `http://127.0.0.1:8000`. Restart it with
`uv run python run.py` after modifying source or configuration. Docker must be
running for the existing PostgreSQL service.

## Practical limits

Live checks use the configured `openai/gpt-oss-120b` provider. These four cases
are regression evidence, not a broad answer-accuracy benchmark. Earlier runs
exposed model omissions even with valid citations. Review reduces this failure
mode but remains probabilistic and makes a second model call for compound
questions. Provider quotas can produce 429 errors and must be handled by the
frontend. No model or provider configuration was replaced.

The existing 51-page policy has no retained original PDF. Re-uploading its exact
original bytes backfills the source without reindexing. Its stored passages are
already available through citation inspection, and metadata reports
`source_available: false` until backfilled.

Repository changes are uncommitted. Existing temporary PDF vendor changes were
left untouched. No public deployment or new production load benchmark is claimed.
