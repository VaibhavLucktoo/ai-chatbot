"""Identity evidence is scoped and budgeted; it never supplies legal facts."""

from dataclasses import asdict
import os
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from sqlalchemy import delete, insert

from app.core.config import get_settings
from app.services.document_questions import is_document_identity_question
from app.services.rag import needs_document_selection
from app.services.retrieval import retrieve_chunks
from app.storage.documents import search_similar_chunks
from app.storage.db import Database
from app.storage.models import Document, DocumentChunk, EMBEDDING_SPACE
from tests.helpers import AsyncTestCase, StubEmbeddings, async_test
from tests import test_retrieval as retrieval_tests
from tests.test_retrieval import vector


class IdentityQuestionTests(unittest.TestCase):
    def test_identity_questions_and_clause_questions_remain_distinct(self):
        for question in (
            'who is the owner of this policy', 'Who published this document?',
            'What is the full legal name of the Disclosing Party in this agreement?',
            'What company website and email appear in the header of this policy?',
            'Which company owns this PDF?',
        ):
            with self.subTest(question=question):
                self.assertTrue(is_document_identity_question(question))
                self.assertTrue(needs_document_selection(question))
        for question in (
            'Who owns the work product?', 'Can I take leave during probation?',
            'What obligations does the Disclosing Party have?',
        ):
            with self.subTest(question=question):
                self.assertFalse(is_document_identity_question(question))


class IdentityScopeTests(AsyncTestCase):
    @async_test
    async def test_only_a_single_effective_document_enables_identity_evidence(self):
        first, second = uuid4(), uuid4()
        cases = (
            ([first], None, True), (None, (first,), True),
            ([first], (second,), True),  # SQL must still intersect both filters.
            (None, (), False), (None, None, False),
            ([first, second], (first, second), False),
        )
        for selected, allowed, expected in cases:
            with self.subTest(selected=selected, allowed=allowed):
                with patch('app.services.retrieval.search_similar_chunks', new_callable=AsyncMock, return_value=[]) as search:
                    await retrieve_chunks(object(), StubEmbeddings(),
                                          'who is the owner of this policy',
                                          document_ids=selected, allowed_document_ids=allowed)
                self.assertEqual(search.await_args.kwargs.get('include_document_identity', False), expected)


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'Set RUN_DB_TESTS=1 for PostgreSQL checks')
class IdentityDatabaseTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.database = Database(get_settings())
        self.schema = 'retrieval_test_' + uuid4().hex
        self.created = False
        self.addCleanup(lambda: self.runner.run(self.cleanup_database()))
        self.runner.run(retrieval_tests.RetrievalDatabaseTests.prepare_database(self))

    cleanup_database = retrieval_tests.RetrievalDatabaseTests.cleanup_database

    @async_test
    async def test_opening_evidence_outside_both_candidate_pools_is_retrieved(self):
        doc_id = uuid4()
        async with self.database.transaction() as connection:
            await connection.execute(delete(Document))
            await connection.execute(insert(Document).values(
                id=doc_id, filename='policy.pdf', content_sha256=uuid4().hex * 2,
                page_count=60, status='ready',
            ))
            await connection.execute(insert(DocumentChunk), [
                dict(id=UUID(int=n), document_id=doc_id,
                     page_number=1 if n == 60 else n+1, chunk_index=n-1,
                     content=('website: https://example.test; e-mail: team@example.test; '
                              'Disclosing Party: __________' if n == 60 else 'The policy owner manages policies.'),
                     embedding_space=EMBEDDING_SPACE,
                     embedding=vector(0, 1) if n == 60 else vector())
                for n in range(1, 61)
            ])
        baseline = await search_similar_chunks(self.database, vector(), top_k=20, query='who is the owner of this policy')
        self.assertNotIn(UUID(int=60), [c.chunk_id for c in baseline])
        for top_k in (1, 5, 20):
            with self.subTest(top_k=top_k):
                result = await search_similar_chunks(
                    self.database, vector(), top_k=top_k, document_ids=[doc_id],
                    query='who is the owner of this policy', include_document_identity=True,
                )
                self.assertEqual(result[0].chunk_id, UUID(int=60))
                self.assertEqual(result[0].cosine_distance, 1.0)
                self.assertIn('Disclosing Party: __________', result[0].content)
                self.assertEqual(len(result), top_k)
                self.assertEqual(len({c.chunk_id for c in result}), top_k)
                self.assertEqual([asdict(c) for c in result[1:]], [asdict(c) for c in baseline[:top_k-1]])

    @async_test
    async def test_identity_evidence_cannot_escape_authorization_or_ready_filters(self):
        selected = (await search_similar_chunks(self.database, vector()))[0].document_id
        for allowed, expected in (([], 0), ([uuid4()], 0), ([selected], 1)):
            with self.subTest(allowed=allowed):
                result = await search_similar_chunks(
                    self.database, vector(), query='owner of this policy',
                    document_ids=[selected], allowed_document_ids=allowed,
                    include_document_identity=True,
                )
                self.assertEqual(len(result), expected)
                self.assertTrue(all(c.document_id == selected for c in result))
        result = await search_similar_chunks(
            self.database, vector(), top_k=20, query='owner of this policy',
            include_document_identity=True,
        )
        self.assertEqual({c.chunk_id.int for c in result}, {1, 2, 3, 4, 5})
