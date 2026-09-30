"""Opt-in evaluation against an existing policy upload and the real LLM.

Page/citation checks are regression signals, not proof of factual grounding.
Review every answer against evaluation/questions.json and its saved trace.
"""

import json
import os
import unittest
from uuid import UUID

from app.core.config import PROJECT_ROOT
from app.schemas.chat import ChatRequest
from app.services.rag import INSUFFICIENT_CONTEXT_ANSWER
from scripts.trace_rag import trace_question
from tests.helpers import AsyncTestCase, async_test


@unittest.skipUnless(
    os.environ.get("RUN_POLICY_TESTS") == "1",
    "Set RUN_POLICY_TESTS=1 and POLICY_DOCUMENT_ID for real policy/LLM evaluation",
)
class PolicyLiveTests(AsyncTestCase):
    @async_test
    async def test_policy_questions(self):
        document_id = UUID(os.environ["POLICY_DOCUMENT_ID"])
        cases = json.loads((PROJECT_ROOT / "evaluation/questions.json").read_text(encoding="utf-8"))
        directory = PROJECT_ROOT / ".cache/policy-evaluation"
        directory.mkdir(parents=True, exist_ok=True)
        for case in cases:
            with self.subTest(case=case["id"]):
                trace = await trace_question(ChatRequest(
                    question=case["question"], top_k=case["top_k"], document_ids=[document_id],
                ))
                path = directory / f"{case['id']}.json"
                path.write_text(json.dumps(trace, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
                self.assertIsNone(trace.get("error_type"), f"Inspect {path}")
                response = trace["response"]
                if case["expect_fallback"]:
                    self.assertEqual(response, {"answer": INSUFFICIENT_CONTEXT_ANSWER, "sources": []})
                else:
                    self.assertNotEqual(response["answer"], INSUFFICIENT_CONTEXT_ANSWER)
                    pages = {source["page_number"] for source in response["sources"]}
                    for alternatives in case["expected_page_groups"]:
                        self.assertTrue(pages.intersection(alternatives), f"Missing cited policy pages; inspect {path}")
                    for phrase in case["forbidden_answer_phrases"]:
                        self.assertNotIn(phrase, response["answer"].casefold())
