import asyncio
import json
import math
import os
import unittest
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import Integer, Uuid, column, delete, insert, select, text, update, values
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import Settings, get_settings
from app.providers.embeddings import get_embedding_provider
from app.schemas.chat import ChatRequest
from app.schemas.documents import DocumentSearchRequest
from app.services.retrieval import RetrievalProviderError, RetrievalResult, has_sufficient_evidence, retrieve_chunks
from app.storage.db import Database
from app.storage.documents import StoredChunkResult, _lexical_query, _rrf_scores, search_similar_chunks
from app.storage.models import Base, Document, DocumentChunk, EMBEDDING_SPACE
from tests.helpers import AsyncTestCase, StubEmbeddings, api_client, async_test, make_pdf


def vector(first=1.0, second=0.0):
    return [first, second] + [0.0] * 382


def stored_chunk():
    return StoredChunkResult(uuid4(), uuid4(), 'source.pdf', 2, 3, 'Source text', 0.25)


class EvidenceGateTests(unittest.TestCase):
    def candidate(self, distance, matched=(), terms=('confidenti', 'inform')):
        return dict(cosine_distance=distance, query_lexemes=terms, matched_lexemes=matched)

    def test_strong_semantic_match_anywhere_in_set_passes(self):
        chunks = [self.candidate(0.8), self.candidate(0.3), self.candidate(0.7)]
        self.assertTrue(has_sufficient_evidence(chunks, max_cosine_distance=0.45))
        self.assertEqual([c['cosine_distance'] for c in chunks], [0.8, 0.3, 0.7])

    def test_weak_semantic_with_meaningful_lexical_match_passes(self):
        self.assertTrue(has_sufficient_evidence(
            [self.candidate(0.6, ('arab', 'support', 'enabl'), ('happen', 'arab', 'support', 'enabl'))],
            max_cosine_distance=0.45,
        ))

    def test_repeated_generic_term_does_not_pass_multi_term_question(self):
        self.assertFalse(has_sufficient_evidence(
            [self.candidate(0.51, ('inform',)), self.candidate(0.54, ('inform',))],
            max_cosine_distance=0.45,
        ))

    def test_lexical_support_can_span_multiple_chunks(self):
        chunks = [self.candidate(0.6, ('confidenti',)), self.candidate(0.7, ('inform',))]
        self.assertTrue(has_sufficient_evidence(chunks, max_cosine_distance=0.45))

    def test_single_term_query_and_empty_query_terms(self):
        self.assertTrue(has_sufficient_evidence(
            [self.candidate(0.6, ('confidenti',), ('confidenti',))], max_cosine_distance=0.45,
        ))
        self.assertFalse(has_sufficient_evidence(
            [self.candidate(0.6, (), ())], max_cosine_distance=0.45,
        ))
        self.assertFalse(has_sufficient_evidence([], max_cosine_distance=0.45))

    def test_threshold_boundary_and_invalid_distances(self):
        chunk = self.candidate(0.45)
        self.assertTrue(has_sufficient_evidence([chunk], max_cosine_distance=0.45))
        self.assertFalse(has_sufficient_evidence([chunk], max_cosine_distance=0.44))
        for distance in (float('nan'), float('inf'), -0.1, None):
            with self.subTest(distance=distance):
                self.assertFalse(has_sufficient_evidence(
                    [self.candidate(distance)], max_cosine_distance=0.45,
                ))

    def test_threshold_loads_from_existing_settings_and_rejects_invalid_values(self):
        for value in ('0.3', '0.6', '-1', '2.1', 'nan', 'inf'):
            with self.subTest(value=value), patch.dict(os.environ, {'RAG_MAX_COSINE_DISTANCE': value}):
                kwargs = dict(_env_file=None, postgres_db='test', postgres_user='test', postgres_password='test')
                if value in ('0.3', '0.6'):
                    self.assertEqual(Settings(**kwargs).rag_max_cosine_distance, float(value))
                else:
                    with self.assertRaises(ValidationError):
                        Settings(**kwargs)


class SearchSchemaTests(unittest.TestCase):
    def test_defaults_and_normalization(self):
        request = DocumentSearchRequest(query='  What is pgvector?  ')
        self.assertEqual(request.query, 'What is pgvector?')
        self.assertEqual(request.top_k, 5)
        self.assertEqual(DocumentSearchRequest(query='a' * 600).query, 'a' * 600)

    def test_rejects_invalid_requests(self):
        for body in ({'query': ''}, {'query': ' \n\t '}, {'query': 123},
                     {'query': 'test', 'top_k': 0}, {'query': 'test', 'top_k': 21},
                     {'query': 'test', 'top_k': True}, {'query': 'test', 'top_k': '5'},
                     {'query': 'test', 'extra': True}):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                DocumentSearchRequest.model_validate(body)

    def test_search_and_chat_accept_selected_document_ids(self):
        document_id = uuid4()
        for schema, field in ((DocumentSearchRequest, 'query'), (ChatRequest, 'question')):
            with self.subTest(schema=schema.__name__):
                request = schema.model_validate({field: 'Question', 'document_ids': [str(document_id)]})
                self.assertEqual(request.document_ids, [document_id])
                self.assertIsNone(schema.model_validate({field: 'Question'}).document_ids)

    def test_search_and_chat_reject_invalid_document_selection(self):
        for schema, field in ((DocumentSearchRequest, 'query'), (ChatRequest, 'question')):
            for selection in ([], ['bad-id'], [str(uuid4())] * 21, str(uuid4())):
                with self.subTest(schema=schema.__name__, selection=selection), self.assertRaises(ValidationError):
                    schema.model_validate({field: 'Question', 'document_ids': selection})


class RetrievalServiceTests(AsyncTestCase):
    @async_test
    async def test_embeds_trimmed_query_once_and_preserves_ranked_results(self):
        provider = StubEmbeddings()
        results = [stored_chunk()]
        database = object()
        with patch.object(provider, 'embed_query', return_value=vector()) as embed:
            with patch('app.services.retrieval.search_similar_chunks', new_callable=AsyncMock, return_value=results) as search:
                result = await retrieve_chunks(database, provider, '  Question  ')
        embed.assert_awaited_once_with('Question')
        search.assert_awaited_once_with(database=database, query_vector=vector(), top_k=5, document_ids=None, query='Question')
        self.assertEqual(result, RetrievalResult('Question', 5, results))

    @async_test
    async def test_document_selection_is_forwarded_to_storage(self):
        document_id = uuid4()
        database = object()
        with patch('app.services.retrieval.search_similar_chunks', new_callable=AsyncMock, return_value=[]) as search:
            await retrieve_chunks(database, StubEmbeddings(), 'Question', document_ids=[document_id])
        search.assert_awaited_once_with(
            database=database, query_vector=vector(), top_k=5, document_ids=(document_id,), query='Question',
        )

    @async_test
    async def test_invalid_document_filter_fails_before_embedding_or_database_access(self):
        provider = StubEmbeddings()
        with patch.object(provider, 'embed_query') as embed:
            for selection in ([], [uuid4()] * 21, ['not-a-uuid'], str(uuid4()), 123):
                with self.subTest(selection=selection):
                    with self.assertRaises(ValueError):
                        await retrieve_chunks(object(), provider, 'Question', document_ids=selection)
                    with self.assertRaises(ValueError):
                        await search_similar_chunks(object(), vector(), document_ids=selection)
            embed.assert_not_awaited()

    @async_test
    async def test_storage_applies_selection_in_sql_before_ranking_limit(self):
        document_id = uuid4()
        database = MagicMock(spec=Database)
        connection = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        connection.execute.return_value = result
        database.transaction.return_value.__aenter__.return_value = connection
        self.assertEqual(await search_similar_chunks(
            database, vector(), top_k=1, document_ids=[document_id],
        ), [])
        statement = connection.execute.await_args.args[0]
        compiled = statement.compile()
        sql = str(compiled)
        self.assertIn('document_chunks.document_id IN', sql)
        self.assertLess(sql.index('document_chunks.document_id IN'), sql.index('ORDER BY'))
        self.assertLess(sql.index('ORDER BY'), sql.index('LIMIT'))
        self.assertIn([document_id], list(compiled.params.values()))

    @async_test
    async def test_bad_parameters_fail_before_embedding(self):
        provider = StubEmbeddings()
        with patch.object(provider, 'embed_query') as embed:
            for query, top_k in (('', 5), ('   ', 5), (None, 5), ('text', 0), ('text', 21), ('text', True)):
                with self.subTest(query=query, top_k=top_k), self.assertRaises(ValueError):
                    await retrieve_chunks(object(), provider, query, top_k)
            embed.assert_not_awaited()

    @async_test
    async def test_wrong_model_space_or_dimensions_fail_before_embedding(self):
        provider = StubEmbeddings()
        with patch.object(provider, 'embed_query') as embed:
            for attribute, value in (('dimensions', 768), ('space_id', 'different-model')):
                with patch.object(provider, attribute, value), self.assertRaises(RetrievalProviderError):
                    await retrieve_chunks(object(), provider, 'Question')
            embed.assert_not_awaited()

    @async_test
    async def test_invalid_provider_vectors_are_server_failures(self):
        provider = StubEmbeddings()
        invalid = ([1.0] * 383, [0.0] * 384, [float('nan')] * 384,
                   [float('inf')] * 384, ['not a number'] * 384, vector(2.0), None)
        with patch('app.services.retrieval.search_similar_chunks', new_callable=AsyncMock) as search:
            for values in invalid:
                with patch.object(provider, 'embed_query', return_value=values):
                    with self.subTest(values=str(values)[:30]), self.assertRaises(RetrievalProviderError):
                        await retrieve_chunks(object(), provider, 'Question')
            search.assert_not_awaited()

    @async_test
    async def test_provider_failure_is_wrapped_but_cancellation_propagates(self):
        provider = StubEmbeddings()
        with patch.object(provider, 'embed_query', side_effect=ValueError('internal model problem')):
            with self.assertRaises(RetrievalProviderError):
                await retrieve_chunks(object(), provider, 'Question')
        with patch.object(provider, 'embed_query', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await retrieve_chunks(object(), provider, 'Question')

    @async_test
    async def test_storage_error_propagates_for_http_503(self):
        failure = SQLAlchemyError('storage unavailable')
        with patch('app.services.retrieval.search_similar_chunks', new_callable=AsyncMock, side_effect=failure):
            with self.assertRaises(SQLAlchemyError) as caught:
                await retrieve_chunks(object(), StubEmbeddings(), 'Question')
        self.assertIs(caught.exception, failure)

    @async_test
    async def test_storage_rejects_bad_vectors_without_a_connection(self):
        for values, top_k in ((vector(), 0), (vector(), 21), (vector(), True),
                              ([1.0] * 383, 5), ([0.0] * 384, 5),
                              ([float('nan')] * 384, 5), (['bad'] * 384, 5)):
            with self.subTest(top_k=top_k), self.assertRaises(ValueError):
                await search_similar_chunks(object(), values, top_k)


class SearchApiTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        provider = patch('app.api.v1.documents.get_embedding_provider', return_value=StubEmbeddings())
        provider.start()
        self.addCleanup(provider.stop)

    @async_test
    async def test_response_contains_sources_and_match_count(self):
        chunk = stored_chunk()
        with patch('app.api.v1.documents.retrieve_chunks', new_callable=AsyncMock, return_value=RetrievalResult('Question', 5, [chunk])):
            async with api_client() as client:
                response = await client.post('/v1/documents/search', json={'query': 'Question'})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body['query'], body['top_k'], body['matches']), ('Question', 5, 1))
        self.assertEqual(body['results'][0], {
            'chunk_id': str(chunk.chunk_id), 'document_id': str(chunk.document_id),
            'filename': 'source.pdf', 'page_number': 2, 'chunk_index': 3,
            'content': 'Source text', 'cosine_distance': 0.25,
        })

    @async_test
    async def test_empty_search_is_successful(self):
        with patch('app.api.v1.documents.retrieve_chunks', new_callable=AsyncMock, return_value=RetrievalResult('Question', 5, [])):
            async with api_client() as client:
                response = await client.post('/v1/documents/search', json={'query': 'Question'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])
        self.assertEqual(response.json()['matches'], 0)

    @async_test
    async def test_search_forwards_document_selection(self):
        document_id = uuid4()
        with patch('app.api.v1.documents.retrieve_chunks', new_callable=AsyncMock, return_value=RetrievalResult('Question', 5, [])) as retrieve:
            async with api_client() as client:
                response = await client.post('/v1/documents/search', json={
                    'query': 'Question', 'document_ids': [str(document_id)],
                })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(retrieve.await_args.kwargs['document_ids'], [document_id])

    @async_test
    async def test_requested_exception_mapping(self):
        async with api_client() as client:
            for failure, expected in ((ValueError('private detail'), 400),
                                      (RetrievalProviderError('private detail'), 500),
                                      (SQLAlchemyError('private detail'), 503),
                                      (TimeoutError('private detail'), 503)):
                with self.subTest(error=type(failure).__name__), patch(
                    'app.api.v1.documents.retrieve_chunks', new_callable=AsyncMock, side_effect=failure,
                ):
                    response = await client.post('/v1/documents/search', json={'query': 'Question'})
                    self.assertEqual(response.status_code, expected, response.text)
                    self.assertNotIn('private detail', response.text)

    @async_test
    async def test_schema_errors_remain_http_422(self):
        with patch('app.api.v1.documents.retrieve_chunks', new_callable=AsyncMock) as retrieve:
            async with api_client() as client:
                for body in ({}, {'query': ''}, {'query': '  '}, {'query': 'Q', 'top_k': 21},
                             {'query': 'Q', 'document_ids': []}, {'query': 'Q', 'document_ids': ['invalid']}):
                    response = await client.post('/v1/documents/search', json=body)
                    self.assertEqual(response.status_code, 422, response.text)
            retrieve.assert_not_awaited()

    @async_test
    async def test_factory_and_response_errors_are_http_500(self):
        async with api_client() as client:
            with patch('app.api.v1.documents.get_embedding_provider', side_effect=ValueError('bad config')):
                response = await client.post('/v1/documents/search', json={'query': 'Q'})
                self.assertEqual(response.status_code, 500)
            invalid = StoredChunkResult(uuid4(), uuid4(), 'source.pdf', 0, 0, 'text', 0.5)
            with patch('app.api.v1.documents.retrieve_chunks', new_callable=AsyncMock, return_value=RetrievalResult('Q', 5, [invalid])):
                response = await client.post('/v1/documents/search', json={'query': 'Q'})
                self.assertEqual(response.status_code, 500)


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'Set RUN_DB_TESTS=1 for PostgreSQL checks')
class RetrievalDatabaseTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.database = Database(get_settings())
        self.schema = 'retrieval_test_' + uuid4().hex
        self.created = False
        self.addCleanup(lambda: self.runner.run(self.cleanup_database()))
        self.runner.run(self.prepare_database())

    async def prepare_database(self):
        self.assertTrue(await self.database.is_ready(), 'Start PostgreSQL with pgvector first')
        async with self.database.transaction() as connection:
            await connection.execute(CreateSchema(self.schema))
        self.created = True
        self.database._engine = self.database._engine.execution_options(schema_translate_map={None: self.schema})
        async with self.database.transaction() as connection:
            await connection.run_sync(Base.metadata.create_all)
            # Simulate a legacy incompatible embedding space only in this
            # isolated schema, to verify the query also enforces the filter.
            await connection.execute(text(
                f'ALTER TABLE "{self.schema}".document_chunks '
                'DROP CONSTRAINT ck_document_chunks_supported_embedding_space'
            ))
            for index, (state, space, embedding) in enumerate((
                ('ready', EMBEDDING_SPACE, vector()),
                ('ready', EMBEDDING_SPACE, vector()),
                ('ready', EMBEDDING_SPACE, vector(math.sqrt(0.5), math.sqrt(0.5))),
                ('ready', EMBEDDING_SPACE, vector(0.0, 1.0)),
                ('ready', EMBEDDING_SPACE, vector(-1.0)),
                ('pending', EMBEDDING_SPACE, vector()),
                ('failed', EMBEDDING_SPACE, vector()),
                ('ready', 'legacy:incompatible-model', vector()),
            ), start=1):
                document_id = uuid4()
                await connection.execute(insert(Document).values(
                    id=document_id, filename=f'source-{index}.pdf', content_sha256=uuid4().hex * 2,
                    page_count=3, status=state,
                ))
                await connection.execute(insert(DocumentChunk).values(
                    id=UUID(int=index), document_id=document_id, page_number=2, chunk_index=0,
                    content=f'Passage {index}', embedding_space=space, embedding=embedding,
                ))

    async def cleanup_database(self):
        try:
            if self.created:
                assert self.schema.startswith('retrieval_test_')
                async with self.database.transaction() as connection:
                    await connection.execute(DropSchema(self.schema, cascade=True))
        finally:
            await self.database.close()

    @async_test
    async def test_cosine_ranking_filters_and_default_limit(self):
        results = await search_similar_chunks(self.database, vector())
        self.assertEqual([item.chunk_id.int for item in results], [1, 2, 3, 4, 5])
        for result, expected in zip(results, [0.0, 0.0, 1.0 - math.sqrt(0.5), 1.0, 2.0]):
            self.assertAlmostEqual(result.cosine_distance, expected, places=6)
            self.assertEqual((result.page_number, result.chunk_index), (2, 0))
        self.assertEqual(results[0].filename, 'source-1.pdf')
        limited = await search_similar_chunks(self.database, vector(), top_k=2)
        self.assertEqual([item.chunk_id.int for item in limited], [1, 2])

    @async_test
    async def test_document_filter_excludes_nearer_chunks_from_other_uploads(self):
        all_results = await search_similar_chunks(self.database, vector())
        selected_document = all_results[3].document_id
        results = await search_similar_chunks(
            self.database, vector(), top_k=1, document_ids=[selected_document],
        )
        self.assertEqual([item.chunk_id.int for item in results], [4])
        self.assertEqual(await search_similar_chunks(
            self.database, vector(), document_ids=[uuid4()],
        ), [])

    @async_test
    async def test_chat_returns_database_connection_before_model_generation(self):
        from app.services.rag import answer_question

        async with self.database.session() as session:
            async def generate(prompt, *, system_prompt, trace=None):
                self.assertFalse(session.in_transaction())
                self.assertEqual(self.database._engine.pool.checkedout(), 0)
                self.assertIn("Passage 1", prompt)
                return json.dumps({'answer': 'Passage 1', 'source_numbers': [1]})

            with (
                patch('app.services.rag.get_embedding_provider', return_value=StubEmbeddings()),
                patch('app.services.rag.generate_llm_response', side_effect=generate),
            ):
                response = await answer_question(session, ChatRequest(question='Question'))
        self.assertEqual(response.answer, 'Passage 1 [1]')
        self.assertEqual(len(response.sources), 1)

    @async_test
    async def test_async_session_search_preserves_pending_changes_and_transaction(self):
        async with self.database.transaction() as connection:
            async with AsyncSession(bind=connection) as session:
                # This incomplete object would fail if retrieval autoflushed it.
                pending_document = Document(filename='unsaved.pdf')
                session.add(pending_document)
                results = await search_similar_chunks(session, vector(), top_k=2, query='Passage')
                self.assertEqual([item.chunk_id.int for item in results], [1, 2])
                self.assertIn(pending_document, session.new)
                self.assertTrue(session.autoflush)
                self.assertTrue(session.in_transaction())
                self.assertTrue(connection.in_transaction())
                session.expunge(pending_document)

    @async_test
    async def test_endpoint_uses_real_sql_and_reports_actual_matches(self):
        with patch('app.api.v1.documents.get_embedding_provider', return_value=StubEmbeddings()):
            async with api_client(self.database) as client:
                response = await client.post('/v1/documents/search', json={'query': '  Question  ', 'top_k': 20})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body['query'], body['top_k'], body['matches']), ('Question', 20, 5))
        self.assertEqual([item['filename'] for item in body['results']], [f'source-{index}.pdf' for index in range(1, 6)])

    @async_test
    async def test_no_ready_documents_returns_no_matches(self):
        async with self.database.transaction() as connection:
            await connection.execute(update(Document).values(status='failed'))
        self.assertEqual(await search_similar_chunks(self.database, vector()), [])
        self.assertEqual(await search_similar_chunks(self.database, vector(), query='Passage'), [])

    @async_test
    async def test_lexical_no_matches_preserves_vector_order_and_distances(self):
        expected = await search_similar_chunks(self.database, vector())
        for query in ('xylophonicallyabsent', 'the and is', '?! -- "'):
            with self.subTest(query=query):
                actual = await search_similar_chunks(self.database, vector(), query=query)
                self.assertEqual(actual, expected)

    @async_test
    async def test_hybrid_filters_both_lists_to_selected_ready_compatible_documents(self):
        # All fixtures have a lexical match, including pending/failed/legacy rows.
        results = await search_similar_chunks(self.database, vector(), top_k=20, query='Passage')
        self.assertEqual([c.chunk_id.int for c in results], [1, 2, 3, 4, 5])
        selected = results[-1].document_id
        results = await search_similar_chunks(
            self.database, vector(), top_k=1, query='Passage', document_ids=[selected],
        )
        self.assertEqual([c.chunk_id.int for c in results], [5])
        self.assertEqual(await search_similar_chunks(
            self.database, vector(), query='Passage', document_ids=[uuid4()],
        ), [])

    @async_test
    async def test_natural_language_lexical_signal_promotes_relevant_rule(self):
        async with self.database.transaction() as connection:
            for number, content in (
                (1, 'Arabic FAQ and translations.'),
                (2, 'Ticket names in Arabic.'),
                (3, 'Language settings.'),
                (4, 'Event Title (Arabic). Mandatory if Arabic support is enabled.'),
                (5, 'Other display settings.'),
            ):
                await connection.execute(update(DocumentChunk).where(
                    DocumentChunk.id == UUID(int=number),
                ).values(content=content))
            query = _lexical_query('What happens if Arabic support is enabled?')
            lexemes = await connection.scalar(select(query))
            self.assertIn('|', lexemes)
            # The relevant chunk lacks "happens" but matches the OR query.
        baseline = await search_similar_chunks(self.database, vector())
        actual = await search_similar_chunks(
            self.database, vector(), query='What happens if Arabic support is enabled?',
        )
        self.assertEqual(baseline[3].chunk_id.int, 4)
        self.assertLess([c.chunk_id.int for c in actual].index(4), 3)
        distances = {c.chunk_id: c.cosine_distance for c in baseline}
        self.assertTrue(all(c.cosine_distance == distances[c.chunk_id] for c in actual))
        relevant = next(c for c in actual if c.chunk_id.int == 4)
        self.assertTrue({'arab', 'support', 'enabl'}.issubset(relevant.matched_lexemes))
        self.assertIn('happen', relevant.query_lexemes)
        self.assertNotIn('happen', relevant.matched_lexemes)

    @async_test
    async def test_evidence_gate_never_uses_unselected_document(self):
        from app.services.rag import answer_question, INSUFFICIENT_CONTEXT_ANSWER

        async with self.database.transaction() as connection:
            await connection.execute(update(DocumentChunk).where(
                DocumentChunk.id == UUID(int=1),
            ).values(content='Confidential Information means proprietary business records.'))
            await connection.execute(update(DocumentChunk).where(
                DocumentChunk.id == UUID(int=5),
            ).values(content='Event information and display settings.'))
            selected = await connection.scalar(select(DocumentChunk.document_id).where(
                DocumentChunk.id == UUID(int=5),
            ))
        candidates = await retrieve_chunks(
            self.database, StubEmbeddings(), 'What is Confidential Information?',
            document_ids=[selected],
        )
        self.assertEqual(len(candidates.chunks), 1)
        self.assertEqual(candidates.chunks[0].matched_lexemes, ('inform',))
        self.assertFalse(has_sufficient_evidence(
            [asdict(c) for c in candidates.chunks], max_cosine_distance=0.45,
        ))
        async with self.database.session() as session:
            with (
                patch('app.services.rag.get_embedding_provider', return_value=StubEmbeddings()),
                patch('app.services.rag.generate_llm_response') as generate,
            ):
                response = await answer_question(session, ChatRequest(
                    question='What is Confidential Information?', document_ids=[selected],
                ))
                generate.assert_not_awaited()
                self.assertFalse(session.in_transaction())
                self.assertEqual(self.database._engine.pool.checkedout(), 0)
        self.assertEqual(response.answer, INSUFFICIENT_CONTEXT_ANSWER)
        self.assertEqual(response.sources, [])

    @async_test
    async def test_lexical_candidate_outside_vector_pool_and_public_limits(self):
        async with self.database.transaction() as connection:
            await connection.execute(delete(Document))
            doc_id = uuid4()
            await connection.execute(insert(Document).values(
                id=doc_id, filename='hybrid.pdf', content_sha256=uuid4().hex * 2,
                page_count=1, status='ready',
            ))
            await connection.execute(insert(DocumentChunk), [
                dict(id=UUID(int=n), document_id=doc_id, page_number=1, chunk_index=n-1,
                     content='quasar' if n == 60 else 'General information',
                     embedding_space=EMBEDDING_SPACE, embedding=vector())
                for n in range(1, 61)
            ])
        for top_k in (1, 5, 20):
            with self.subTest(top_k=top_k):
                results = await search_similar_chunks(
                    self.database, vector(), top_k=top_k, query='quasar',
                )
                self.assertEqual(len(results), top_k)
                self.assertEqual(len({c.chunk_id for c in results}), top_k)
                if top_k > 1:
                    # Rank 1 in the lexical list ties vector rank 1, then UUID wins.
                    self.assertEqual([c.chunk_id.int for c in results[:2]], [1, 60])
                    self.assertEqual(results[1].cosine_distance, 0.0)

    @async_test
    async def test_rrf_ranks_ties_and_empty_list_fallbacks(self):
        def candidates(name, ids):
            # Typed VALUES allow testing either empty strategy independently.
            data = [(UUID(int=n), rank) for rank, n in enumerate(ids, start=1)]
            rows = values(column('chunk_id', Uuid), column('rank', Integer), name=name).data(
                data or [(UUID(int=0), 0)],
            )
            statement = select(rows.c.chunk_id, rows.c.rank)
            return statement.where(rows.c.rank > 0).subquery()

        cases = (([1, 2, 3], [2, 1, 4], [1, 2, 3, 4]),
                 ([2, 1], [], [2, 1]), ([], [3, 1], [3, 1]), ([], [], []))
        async with self.database.transaction() as connection:
            for semantic, lexical, expected in cases:
                with self.subTest(semantic=semantic, lexical=lexical):
                    fused = _rrf_scores(candidates('semantic', semantic), candidates('lexical', lexical))
                    rows = (await connection.execute(select(fused).order_by(
                        fused.c.rrf_score.desc(), fused.c.chunk_id.asc(),
                    ))).all()
                    self.assertEqual([r.chunk_id.int for r in rows], expected)
                    for row in rows:
                        score = sum(1 / (60 + ids.index(row.chunk_id.int) + 1)
                                    for ids in (semantic, lexical) if row.chunk_id.int in ids)
                        self.assertAlmostEqual(row.rrf_score, score)

    @unittest.skipUnless(os.environ.get('RUN_MODEL_TESTS') == '1', 'Set RUN_MODEL_TESTS=1 for real FastEmbed')
    @async_test
    async def test_real_upload_then_query_embedding_and_search(self):
        async with self.database.transaction() as connection:
            await connection.execute(delete(Document))
        provider = get_embedding_provider()
        with patch('app.api.v1.documents.get_embedding_provider', return_value=provider):
            async with api_client(self.database) as client:
                for filename, passage in (
                    ('database.pdf', 'Document embeddings are stored in PostgreSQL with pgvector.'),
                    ('recipe.pdf', 'A chocolate cake recipe uses flour, butter, sugar, and cocoa.'),
                ):
                    uploaded = await client.post('/v1/documents/upload', files={'file': (filename, make_pdf(passage), 'application/pdf')})
                    self.assertEqual(uploaded.status_code, 201, uploaded.text)
                response = await client.post('/v1/documents/search', json={
                    'query': 'What database stores our document vectors?', 'top_k': 2,
                })
        self.assertEqual(response.status_code, 200, response.text)
        results = response.json()['results']
        self.assertEqual(response.json()['matches'], 2)
        self.assertEqual(results[0]['filename'], 'database.pdf')
        self.assertLess(results[0]['cosine_distance'], results[1]['cosine_distance'])
