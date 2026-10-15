"""Document-independent extraction, atomic indexing and backfill fencing."""

import math
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from app.schemas.document_metadata import METADATA_VERSION
from app.services.document_metadata import extract_document_metadata, ensure_document_metadata
from app.storage.document_metadata import metadata_snapshot, publish_metadata_backfill
from app.storage.models import Document, DocumentChunk, DocumentMetadata
from tests.helpers import AsyncTestCase, async_test, make_pdf, api_client, small_tokenizer
from tests import test_ingestion as ingestion_tests


def source(text, page=1):
    return {"id": uuid4(), "page_number": page, "content": text}


class MetadataExtractionTests(unittest.TestCase):
    def test_generic_labels_conflicts_contacts_and_blank_legal_names(self):
        chunks = [source('Title: Staff Handbook\nOrganization: Northwind Labs\nAuthor: Jane Doe\n'
                         'Version: 2.1\nEffective date: 2026-10-01\nDisclosing Party: ______\n'
                         'https://northwind.example/contact\nhello@northwind.example', 3),
                  source('Title: Supplier Agreement\nOrganization: Contoso Limited\n'
                         'Disclosing Party: Contoso Limited', 8)]
        with patch('app.services.chunking._get_tokenizer', return_value=small_tokenizer()):
            result = extract_document_metadata('unrelated.pdf', chunks)
        facts = {(f.field, f.value): f for f in result.facts}
        self.assertIn(('organization', 'Northwind Labs'), facts)
        self.assertIn(('organization', 'Contoso Limited'), facts)
        self.assertEqual(facts[('disclosing_party', None)].status, 'unspecified')
        self.assertEqual(facts[('disclosing_party', 'Contoso Limited')].page_number, 8)
        for field, value in (('author', 'Jane Doe'), ('version', '2.1'),
                             ('website', 'https://northwind.example/contact'), ('email', 'hello@northwind.example')):
            self.assertIn((field, value), facts)
        for fact in result.facts:
            original = next(chunk for chunk in chunks if chunk['id'] == fact.chunk_id)
            self.assertIn(fact.quote, original['content'])
            self.assertEqual(fact.page_number, original['page_number'])
        self.assertNotIn(('document_owner', 'Northwind Labs'), facts)

    def test_unknown_identity_is_not_invented_and_contact_repetition_is_bounded(self):
        chunks = [source('Unlabelled prose. team@example.test www.example.test', page=n) for n in range(1, 101)]
        with patch('app.services.chunking._get_tokenizer', return_value=small_tokenizer()):
            result = extract_document_metadata('random.pdf', chunks)
        self.assertEqual({f.field for f in result.facts}, {'email', 'website'})
        self.assertEqual(len(result.facts), 2)
        with patch('app.services.chunking._get_tokenizer', return_value=small_tokenizer()):
            unknown = extract_document_metadata('other.pdf', [source('A plain text paragraph.')])
        self.assertEqual(unknown.facts, ())
        self.assertIn('A plain text paragraph.', unknown.summary)


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'Set RUN_DB_TESTS=1 for PostgreSQL checks')
class MetadataDatabaseTests(AsyncTestCase):
    # Reuse the private ingestion fixture setup without collecting its test cases again.
    def setUp(self):
        super().setUp()
        from app.core.config import get_settings
        from app.storage.db import Database
        from tests.helpers import StubEmbeddings
        self.database = Database(get_settings())
        self.schema = 'ingestion_test_' + uuid4().hex
        self.schema_created = False
        self.addCleanup(lambda: self.runner.run(self.clean_database()))
        self.runner.run(ingestion_tests.IngestionDatabaseTests.prepare_database(self))
        self.embeddings = StubEmbeddings()
        self.provider_patch = patch('app.api.v1.documents.get_embedding_provider', return_value=self.embeddings)
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        tokenizer = patch('app.services.chunking._get_tokenizer', return_value=small_tokenizer())
        tokenizer.start()
        self.addCleanup(tokenizer.stop)

    clean_database = ingestion_tests.IngestionDatabaseTests.clean_database

    @async_test
    async def test_every_upload_and_recovery_publish_metadata_atomically_and_delete_cascades(self):
        from app.services.recovery import recover_once
        async with api_client(self.database) as client:
            for filename, text, queued in (('research.pdf', 'Author: Alice; Organization: Alpha Labs', False),
                                           ('operations.pdf', 'Publisher: Beta Foundation; Version: 7', True)):
                with self.subTest(filename=filename):
                    path = '/v1/documents/jobs' if queued else '/v1/documents/upload'
                    response = await client.post(path, files={'file': (filename, make_pdf(text), 'application/pdf')})
                    self.assertIn(response.status_code, (201, 202), response.text)
                    identifier = response.json()['document_id']
                    if queued:
                        with patch('app.services.recovery.get_embedding_provider', return_value=self.embeddings):
                            self.assertTrue(await recover_once(self.database))
                    async with self.database.transaction() as connection:
                        row = (await connection.execute(select(DocumentMetadata).where(
                            DocumentMetadata.document_id == identifier))).mappings().one()
                        chunk_ids = set((await connection.execute(select(DocumentChunk.id).where(
                            DocumentChunk.document_id == identifier))).scalars())
                    self.assertEqual(row['version'], METADATA_VERSION)
                    self.assertAlmostEqual(math.hypot(*row['embedding']), 1.0)
                    self.assertTrue(row['facts'])
                    self.assertTrue(all(f['chunk_id'] in {str(c) for c in chunk_ids} for f in row['facts']))
                    self.assertFalse(await ensure_document_metadata(self.database, self.embeddings, identifier))
                    self.assertEqual((await client.delete('/v1/documents/' + identifier)).status_code, 204)
                    async with self.database.transaction() as connection:
                        self.assertEqual(await connection.scalar(select(func.count()).select_from(DocumentMetadata)), 0)

    @async_test
    async def test_backfill_reuses_original_chunks_and_vectors_and_is_idempotent(self):
        data = make_pdf('Organization: Example Institute; Author: Sam')
        async with api_client(self.database) as client:
            response = await client.post('/v1/documents/upload', files={'file': ('old.pdf', data, 'application/pdf')})
            identifier = response.json()['document_id']
            async with self.database.transaction() as connection:
                await connection.execute(delete(DocumentMetadata))
                before = (await connection.execute(select(DocumentChunk.__table__))).mappings().all()
            self.assertTrue(await ensure_document_metadata(self.database, self.embeddings, identifier))
            self.assertFalse(await ensure_document_metadata(self.database, self.embeddings, identifier))
            async with self.database.transaction() as connection:
                after = (await connection.execute(select(DocumentChunk.__table__))).mappings().all()
            for old, new in zip(before, after, strict=True):
                self.assertEqual(old['id'], new['id'])
                self.assertEqual(old['content'], new['content'])
                self.assertEqual(list(old['embedding']), list(new['embedding']))
            async with self.database.transaction() as connection:
                await connection.execute(delete(DocumentMetadata))
            batches = len(self.embeddings.batch_sizes)
            with patch('app.services.ingestion.extract_pdf_isolated', side_effect=AssertionError('Duplicate reparsed')):
                duplicate = await client.post('/v1/documents/upload', files={'file': ('same.pdf', data, 'application/pdf')})
            self.assertEqual(duplicate.status_code, 200)
            self.assertEqual(len(self.embeddings.batch_sizes), batches + 1)

    @async_test
    async def test_backfill_cannot_publish_for_replaced_chunks_or_failed_document(self):
        from app.services.document_metadata import metadata_record
        async with api_client(self.database) as client:
            response = await client.post('/v1/documents/upload', files={'file': ('old.pdf', make_pdf('Author: Jane'), 'application/pdf')})
        identifier = response.json()['document_id']
        async with self.database.transaction() as connection:
            await connection.execute(delete(DocumentMetadata))
        filename, digest, chunks = await metadata_snapshot(self.database, identifier)
        payload = extract_document_metadata(filename, chunks)
        record = metadata_record(payload, [1.0] + [0.0] * 383)
        changed = [{**chunks[0], 'id': uuid4()}]
        self.assertFalse(await publish_metadata_backfill(self.database, identifier, digest, changed, record))
        async with self.database.transaction() as connection:
            await connection.execute(update(Document).values(status='failed'))
        self.assertFalse(await publish_metadata_backfill(self.database, identifier, digest, chunks, record))

    @async_test
    async def test_ready_duplicate_still_succeeds_when_metadata_backfill_provider_is_down(self):
        data = make_pdf('Author: Existing Author')
        async with api_client(self.database) as client:
            first = await client.post('/v1/documents/upload', files={'file': ('existing.pdf', data, 'application/pdf')})
            async with self.database.transaction() as connection:
                await connection.execute(delete(DocumentMetadata))
            with patch.object(self.embeddings, 'embed_documents', side_effect=OSError('offline')):
                duplicate = await client.post('/v1/documents/upload', files={'file': ('existing.pdf', data, 'application/pdf')})
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()['document_id'], first.json()['document_id'])
