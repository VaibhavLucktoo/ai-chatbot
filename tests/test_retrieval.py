import asyncio
import math
import os
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import delete, insert, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import get_settings
from app.providers.embeddings import get_embedding_provider
from app.schemas.documents import DocumentSearchRequest
from app.services.retrieval import RetrievalProviderError, RetrievalResult, retrieve_chunks
from app.storage.db import Database
from app.storage.documents import StoredChunkResult, search_similar_chunks
from app.storage.models import Base, Document, DocumentChunk, EMBEDDING_SPACE
from tests.helpers import AsyncTestCase, StubEmbeddings, api_client, async_test, make_pdf


def vector(first=1.0, second=0.0):
    return [first, second] + [0.0] * 382


def stored_chunk():
    return StoredChunkResult(uuid4(), uuid4(), 'source.pdf', 2, 3, 'Source text', 0.25)


class SearchSchemaTests(unittest.TestCase):
    def test_defaults_and_normalization(self):
        request = DocumentSearchRequest(query='  What is pgvector?  ')
        self.assertEqual(request.query, 'What is pgvector?')
        self.assertEqual(request.top_k, 5)
        self.assertEqual(DocumentSearchRequest(query='a' * 600).query, 'a' * 600)

    def test_rejects_invalid_requests(self):
        for body in ({'query': ''}, {'query': ' \n\t '}, {'query': 123},
                     {'query': 'test', 'top_k': 0}, {'query': 'test', 'top_k': 21},
                     {'query': 'test', 'extra': True}):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                DocumentSearchRequest.model_validate(body)


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
        search.assert_awaited_once_with(database=database, query_vector=vector(), top_k=5)
        self.assertEqual(result, RetrievalResult('Question', 5, results))

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
                for body in ({}, {'query': ''}, {'query': '  '}, {'query': 'Q', 'top_k': 21}):
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
