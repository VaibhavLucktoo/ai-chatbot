import asyncio
import math
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import get_settings
from app.providers.embeddings import get_embedding_provider
from app.services.chunking import TextChunk
from app.services.document_hash import pdf_sha256
from app.services.ingestion import IngestionProcessingError, ingest_pdf
from app.storage.db import Database
from app.storage.documents import (
    ClaimedDocument, claim_document, fail_document, find_document_by_hash,
)
from app.storage.models import Base, Document, DocumentChunk, EMBEDDING_SPACE
from tests.helpers import AsyncTestCase, StubEmbeddings, api_client, async_test, make_pdf, small_tokenizer


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'Set RUN_DB_TESTS=1 for PostgreSQL checks')
class IngestionDatabaseTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.database = Database(get_settings())
        self.schema = 'ingestion_test_' + uuid4().hex
        self.schema_created = False
        self.addCleanup(lambda: self.runner.run(self.clean_database()))
        self.runner.run(self.prepare_database())
        self.embeddings = StubEmbeddings()
        self.provider_patch = patch('app.api.v1.documents.get_embedding_provider', return_value=self.embeddings)
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        self.tokenizer_patch = patch('app.services.chunking._get_tokenizer', return_value=small_tokenizer())
        self.tokenizer_patch.start()
        self.addCleanup(self.tokenizer_patch.stop)

    async def prepare_database(self):
        self.assertTrue(await self.database.is_ready(), 'Start PostgreSQL with pgvector first')
        async with self.database.transaction() as connection:
            await connection.execute(CreateSchema(self.schema))
        self.schema_created = True
        # SQLAlchemy maps all application tables into this test's private schema.
        self.database._engine = self.database._engine.execution_options(
            schema_translate_map={None: self.schema},
        )
        async with self.database.transaction() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def clean_database(self):
        try:
            if self.schema_created:
                assert self.schema.startswith('ingestion_test_')
                async with self.database.transaction() as connection:
                    await connection.execute(DropSchema(self.schema, cascade=True))
        finally:
            await self.database.close()

    async def upload(self, client, data, filename='test.pdf'):
        return await client.post('/v1/documents/upload', files={'file': (filename, data, 'application/pdf')})

    async def document(self, data):
        return await find_document_by_hash(self.database, pdf_sha256(data))

    @async_test
    async def test_multipage_upload_and_duplicate(self):
        data = make_pdf('word ' * 750 + 'FIRST_TAIL', None, 'Third page tail')
        original_embed = self.embeddings.embed_documents

        async def check_pending(texts):
            pending = await self.document(data)
            self.assertEqual((pending.status, pending.chunk_count), ('pending', 0))
            self.assertEqual(self.database._engine.pool.checkedout(), 0)
            return await original_embed(texts)

        with patch.object(self.embeddings, 'embed_documents', side_effect=check_pending):
            async with api_client(self.database) as client:
                first = await self.upload(client, data)
                self.assertEqual(first.status_code, 201, first.text)
                # A ready duplicate must not parse, tokenize, or embed again.
                with patch('app.services.ingestion.extract_pdf', side_effect=AssertionError('duplicate parsed')):
                    duplicate = await self.upload(client, data, 'renamed.pdf')
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(first.json()['document_id'], duplicate.json()['document_id'])
        self.assertEqual(duplicate.json()['filename'], 'test.pdf')
        saved = await self.document(data)
        self.assertEqual((saved.status, saved.page_count), ('ready', 3))
        async with self.database.transaction() as connection:
            chunks = (await connection.execute(select(DocumentChunk.__table__).where(
                DocumentChunk.document_id == saved.id,
            ).order_by(DocumentChunk.chunk_index))).mappings().all()
        self.assertEqual([row['chunk_index'] for row in chunks], list(range(len(chunks))))
        self.assertEqual({row['page_number'] for row in chunks}, {1, 3})
        self.assertTrue(any('FIRST_TAIL' in row['content'] for row in chunks))
        self.assertTrue(all(len(row['embedding']) == 384 for row in chunks))
        self.assertTrue(all(row['embedding_space'] == EMBEDDING_SPACE for row in chunks))

    @async_test
    async def test_invalid_pdf_leaves_no_document(self):
        data = make_pdf('text', unsupported_filter=True)
        async with api_client(self.database) as client:
            response = await self.upload(client, data)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(await self.document(data))

    @async_test
    async def test_failed_embedding_can_be_retried_with_same_id(self):
        data = make_pdf('Retry this document')
        async with api_client(self.database) as client:
            with patch.object(self.embeddings, 'embed_documents', side_effect=RuntimeError('model failed')):
                failure = await self.upload(client, data)
            self.assertEqual(failure.status_code, 503, failure.text)
            failed = await self.document(data)
            self.assertEqual((failed.status, failed.chunk_count), ('failed', 0))
            retry = await self.upload(client, data, 'new-name.pdf')
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()['document_id'], str(failed.id))
        self.assertEqual(retry.json()['filename'], 'test.pdf')
        self.assertTrue(retry.json()['already_existed'])
        self.assertEqual((await self.document(data)).status, 'ready')

    @async_test
    async def test_simultaneous_create_and_retry_claims_have_one_owner(self):
        data = make_pdf('Concurrent claims')
        for attempt in range(2):
            results = await asyncio.gather(*[
                claim_document(self.database, filename='test.pdf', content_sha256=pdf_sha256(data), page_count=1)
                for _ in range(2)
            ])
            claimed = [result for result in results if isinstance(result, ClaimedDocument)]
            self.assertEqual(len(claimed), 1)
            self.assertEqual(claimed[0].already_existed, attempt == 1)
            self.assertEqual(len({result.id for result in results}), 1)
            await fail_document(self.database, claimed[0].id)

    @async_test
    async def test_pending_duplicate_returns_conflict_then_ready_duplicate_succeeds(self):
        data = make_pdf('Simultaneous upload')
        started, release = asyncio.Event(), asyncio.Event()
        original_embed = self.embeddings.embed_documents

        async def wait_before_embedding(texts):
            started.set()
            await release.wait()
            return await original_embed(texts)

        async with api_client(self.database) as client:
            with patch.object(self.embeddings, 'embed_documents', side_effect=wait_before_embedding):
                task = asyncio.create_task(self.upload(client, data))
                try:
                    await asyncio.wait_for(started.wait(), timeout=10)
                    pending = await self.upload(client, data)
                    self.assertEqual(pending.status_code, 409, pending.text)
                    self.assertEqual(pending.headers['retry-after'], '5')
                finally:
                    release.set()
                    first = await task
            duplicate = await self.upload(client, data)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertEqual(first.json()['document_id'], duplicate.json()['document_id'])

    @async_test
    async def test_cancelled_ingestion_is_failed_and_retryable(self):
        data = make_pdf('Cancelled upload')
        started = asyncio.Event()

        async def block(texts):
            started.set()
            await asyncio.Event().wait()

        with patch.object(self.embeddings, 'embed_documents', side_effect=block):
            task = asyncio.create_task(ingest_pdf(
                database=self.database, embeddings=self.embeddings,
                filename='test.pdf', data=data,
            ))
            try:
                await asyncio.wait_for(started.wait(), timeout=10)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        failed = await self.document(data)
        self.assertEqual((failed.status, failed.chunk_count), ('failed', 0))
        result = await ingest_pdf(database=self.database, embeddings=self.embeddings, filename='test.pdf', data=data)
        self.assertEqual(result.document_id, failed.id)
        self.assertEqual(result.status, 'ready')

    @async_test
    async def test_bad_embeddings_never_publish_ready_documents(self):
        invalid_vectors = ([0.0] * 384, [float('nan')] * 384, [1.0] * 383, [1.0] * 384)
        for vector in invalid_vectors:
            data = make_pdf('Invalid model output')
            with patch.object(self.embeddings, 'embed_documents', return_value=[vector]):
                with self.assertRaises(IngestionProcessingError):
                    await ingest_pdf(database=self.database, embeddings=self.embeddings, filename='test.pdf', data=data)
            failed = await self.document(data)
            self.assertEqual((failed.status, failed.chunk_count), ('failed', 0))

    @async_test
    async def test_more_than_256_chunks_and_database_rollback(self):
        data = make_pdf('Large chunk collection')
        chunks = [TextChunk(index, 1, f'Chunk {index}') for index in range(300)]
        statements = []

        def fail_second_batch(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith('INSERT INTO') and 'document_chunks' in statement:
                statements.append(statement)
                if len(statements) == 2:
                    raise OperationalError('injected second-batch failure', None, RuntimeError('test'))

        engine = self.database._engine.sync_engine
        with patch('app.services.ingestion.chunk_document', return_value=chunks):
            event.listen(engine, 'before_cursor_execute', fail_second_batch)
            try:
                with self.assertRaises(IngestionProcessingError):
                    await ingest_pdf(database=self.database, embeddings=self.embeddings, filename='test.pdf', data=data)
            finally:
                event.remove(engine, 'before_cursor_execute', fail_second_batch)
            self.assertEqual(len(statements), 2)
            failed = await self.document(data)
            self.assertEqual((failed.status, failed.chunk_count), ('failed', 0))
            result = await ingest_pdf(database=self.database, embeddings=self.embeddings, filename='test.pdf', data=data)
        self.assertEqual(result.document_id, failed.id)
        self.assertEqual((result.status, result.chunk_count), ('ready', 300))
        self.assertLessEqual(max(self.embeddings.batch_sizes), 32)
        self.assertEqual((await self.document(data)).chunk_count, 300)

    @async_test
    async def test_chunk_limit_is_explicit_and_does_not_truncate(self):
        data = make_pdf('Excessive chunks')
        chunks = [TextChunk(index, 1, 'text') for index in range(1001)]
        async with api_client(self.database) as client:
            with patch('app.services.ingestion.chunk_document', return_value=chunks):
                response = await self.upload(client, data)
        self.assertEqual(response.status_code, 422, response.text)
        failed = await self.document(data)
        self.assertEqual((failed.status, failed.chunk_count), ('failed', 0))
        self.assertEqual(self.embeddings.batch_sizes, [])

    @unittest.skipUnless(os.environ.get('RUN_MODEL_TESTS') == '1', 'Set RUN_MODEL_TESTS=1 for real FastEmbed')
    @async_test
    async def test_real_pdf_tokenizer_embeddings_and_persistence(self):
        self.tokenizer_patch.stop()
        provider = get_embedding_provider()
        data = make_pdf('PostgreSQL stores document vectors. ' * 150 + 'FIRST_TAIL', None,
                        'Sources retain their PDF page numbers. THIRD_TAIL')
        with patch('app.api.v1.documents.get_embedding_provider', return_value=provider):
            async with api_client(self.database) as client:
                response = await self.upload(client, data)
                duplicate = await self.upload(client, data, 'duplicate.pdf')
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        saved = await self.document(data)
        async with self.database.transaction() as connection:
            rows = (await connection.execute(select(DocumentChunk.__table__).where(
                DocumentChunk.document_id == saved.id,
            ).order_by(DocumentChunk.chunk_index))).mappings().all()
        self.assertEqual(saved.page_count, 3)
        self.assertGreater(len(rows), 2)
        self.assertEqual({row['page_number'] for row in rows}, {1, 3})
        self.assertTrue(any('FIRST_TAIL' in row['content'] for row in rows))
        self.assertTrue(any('THIRD_TAIL' in row['content'] for row in rows))
        self.assertEqual([row['chunk_index'] for row in rows], list(range(len(rows))))
        for row in rows:
            self.assertEqual(len(row['embedding']), 384)
            self.assertTrue(all(math.isfinite(value) for value in row['embedding']))
            self.assertAlmostEqual(math.hypot(*row['embedding']), 1.0, places=5)
            self.assertEqual(row['embedding_space'], EMBEDDING_SPACE)
