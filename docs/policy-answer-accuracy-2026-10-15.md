# Policy assistant answer accuracy — 2026-10-15

The reported question, **“who is the owner of this policy”**, now returns:

> The organization responsible for the policies is 360 Bytes. [1][2]

The final live answer cites policy pages 18 and 7. The NDA's full legal
Disclosing Party name remains unspecified: its first-page name field is blank.
The original PDF visibly carries 360 Bytes branding. This does not fill in a
blank contracting-party field.

## Cause and changes

- The saved Policy assistant had no assigned documents after document restoration.
  Per the user's selection, its assignment is now **pdf24_merged.pdf only**.
  Its provider, model, and generation settings were retained.
- Even after assignment, the live Gemini baseline returned the insufficient-context
  answer. Retrieval selected pages 23, 18, 26, 7, and 24 and missed page 1.
- For recognized document identity questions with one selected/authorized document,
  retrieval now includes its first compatible passage in the existing top-k budget.
  This happens in the same SQL query and retains ready/active, embedding-space,
  selected-document, and assistant-authorization filters. The opening passage can
  be included even when it falls outside both hybrid candidate pools.
- Ordinary clause searches retain their existing hybrid ranking. Identity retrieval
  adds no embedding or language-model calls and leaves the original cosine distance
  and citation provenance intact. The identity branch adds a bounded SQL lookup;
  expanded grounding instructions consume additional prompt bytes within existing limits.
- Grounding instructions distinguish supported company identity, inferred branding,
  and explicitly named legal parties. They preserve useful partial answers while
  requiring missing fields to be acknowledged.
- Manual review of live results also caught an unsupported “exception” interpretation
  of the manager-approved probation leave clause. Instructions and the multipart
  regression now require acknowledging unclear precedence between that clause and
  the probation leave restriction.
- The trace tool now accepts `--assistant-id`; `POLICY_ASSISTANT_ID` selects the
  same saved assistant for live tests. Previously, tracing ignored the selected
  assistant and could evaluate the workspace model instead. Assistant authorization,
  model context, and stateless-turn lease behavior are preserved in diagnostics.

No migration, document re-ingestion, embedding replacement, or API contract change
was required. Deployment hardening remains separate from this accuracy work.
The final database check confirmed three ready PDFs with matching original-file
SHA-256 hashes, 137 normalized 384-dimensional vectors, no orphan chunks, and no
leftover test schemas. The Policy assistant still has only the approved PDF assigned.

## Verification

Commands run from `Backend/` using the workspace virtual environment. Database and
cached-model integration tests were enabled with `RUN_DB_TESTS=1`,
`RUN_MODEL_TESTS=1`, and `HF_HUB_OFFLINE=1`.

```text
python -B -u -m pytest -p no:cacheprovider tests -q
260 passed, 1 skipped, 395 subtests passed in 122.11s (0:02:02)
```

The optional policy suite was then run separately with `RUN_POLICY_TESTS=1`, the
real policy/assistant IDs, and a five-second interval between cases:

```text
python -B -u -m pytest -p no:cacheprovider tests/test_policy_live.py -q
1 passed, 8 subtests passed in 89.55s (0:01:29)
```

All eight live cases used `models/gemini-3.1-flash-lite`: policy owner, blank legal
Disclosing Party name, header website/email, post-probation leave entitlements,
probation leave restriction, approved-leave consequence, multipart ambiguity, and
unsupported Mars-budget question. Answers were reviewed against their cited passages.
Raw document passages and provider traces remain local under the ignored
`.cache/policy-evaluation/` directory.

```text
ruff check .
All checks passed!

python -B -m scripts.check_api_contract
OpenAPI operations: 39
Unique operation IDs: 39
Duplicate operation IDs: 0
Paths, methods, parameters, request schemas, status codes and existing response schemas: unchanged
Tags: consistent
Application modules imported successfully: 81
```

The regression cases measure these specific behaviors, rather than establishing
universal factual accuracy. Identity detection uses conservative English hints.
OCR is still unavailable for image-only evidence; the successful owner answer is
supported by indexed body text as well as retained header/footer contact details.
