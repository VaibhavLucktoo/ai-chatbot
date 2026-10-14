from io import BytesIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from pypdf.errors import LimitReachedError
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.documents import read_limited_pdf
from app.providers.documents import (
    ExtractedDocument, ExtractedPage, MAX_PDF_BYTES,
    PDFExtractionError, PDFTooLargeError, extract_pdf,
)
from app.schemas.documents import DocumentUploadMetadata, IngestionPayload
from app.services import chunking
from app.services.ingestion import IngestionProcessingError, IngestionResult
from scripts.ingest import read_pdf
from tests.helpers import (
    AsyncTestCase, StubEmbeddings, api_client, async_test, make_pdf, small_tokenizer,
)


class ExtractionTests(unittest.TestCase):
    def test_null_padding_preserves_words_and_blank_page_positions(self):
        result = extract_pdf(make_pdf('Before\x00after', '\x00\x00', 'Last page'))
        self.assertEqual(result.page_count, 3)
        self.assertEqual([(page.page_number, page.text) for page in result.pages],
                         [(1, 'Before after'), (3, 'Last page')])

    def test_null_only_pdf_has_no_searchable_text(self):
        with self.assertRaisesRegex(PDFExtractionError, 'No searchable text'):
            extract_pdf(make_pdf('\x00\x00'))

    def test_preserves_page_numbers_across_blank_pages(self):
        result = extract_pdf(make_pdf('First page', None, 'Third page'))
        self.assertEqual(result.page_count, 3)
        self.assertEqual([(page.page_number, page.text) for page in result.pages],
                         [(1, 'First page'), (3, 'Third page')])

    def test_rejects_invalid_empty_encrypted_and_image_only_pdfs(self):
        fixtures = {
            'empty bytes': b'', 'non-PDF': b'not pdf',
            'damaged PDF': b'%PDF-1.7\ninvalid\n%%EOF\n',
            'zero pages': make_pdf(), 'blank pages': make_pdf(None),
            'scanned page': make_pdf(None, image_only=True),
            'encrypted': make_pdf('secret', encrypted=True),
            'truncated': make_pdf('text')[:-10],
        }
        for name, data in fixtures.items():
            with self.subTest(name=name), self.assertRaises(PDFExtractionError):
                extract_pdf(data)

    def test_unsupported_stream_filter_becomes_client_error(self):
        with self.assertRaises(PDFExtractionError) as caught:
            extract_pdf(make_pdf('text', unsupported_filter=True))
        self.assertIsInstance(caught.exception.__cause__, NotImplementedError)

    def test_parser_resource_limit_becomes_client_error(self):
        with patch('app.providers.documents.PdfReader', side_effect=LimitReachedError('limit')):
            with self.assertRaises(PDFExtractionError):
                extract_pdf(make_pdf('text'))

    def test_file_page_and_text_limits(self):
        with self.assertRaises(PDFTooLargeError):
            extract_pdf(b'%PDF-' + b'x' * MAX_PDF_BYTES)
        with self.assertRaisesRegex(PDFExtractionError, '100-page'):
            extract_pdf(make_pdf(*([None] * 101)))
        with patch('app.providers.documents.MAX_EXTRACTED_CHARS', 10):
            with self.assertRaisesRegex(PDFExtractionError, 'too much'):
                extract_pdf(make_pdf('long extracted text'))


class ChunkingTests(unittest.TestCase):
    def test_long_page_preserves_tail_overlap_and_original_text(self):
        words = [f'word{i}' for i in range(1800)] + ['FINAL_SENTINEL']
        original = ' '.join(words)
        tokenizer = small_tokenizer()
        document = ExtractedDocument(3, (
            ExtractedPage(1, original), ExtractedPage(3, 'Third-page tail'),
        ))
        with patch('app.services.chunking._get_tokenizer', return_value=tokenizer):
            chunks = chunking.chunk_document(document)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))
        first_page = [chunk for chunk in chunks if chunk.page_number == 1]
        self.assertTrue(first_page[-1].content.endswith('FINAL_SENTINEL'))
        for previous, current in zip(first_page, first_page[1:]):
            self.assertEqual(previous.content.split()[-40:], current.content.split()[:40])
        for chunk in first_page:
            self.assertIn(chunk.content, original)
            self.assertLessEqual(len(tokenizer.encode(chunk.content).ids), 480)
        self.assertEqual(chunks[-1].page_number, 3)

    def test_downloaded_tokenizer_truncation_and_padding_are_disabled(self):
        tokenizer = small_tokenizer()
        tokenizer.enable_truncation(max_length=32)
        tokenizer.enable_padding(length=32)
        with TemporaryDirectory() as folder:
            path = str(Path(folder) / 'tokenizer.json')
            tokenizer.save(path)
            chunking._get_tokenizer.cache_clear()
            self.addCleanup(chunking._get_tokenizer.cache_clear)
            with patch('app.services.chunking.hf_hub_download', return_value=path):
                loaded = chunking._get_tokenizer()
            self.assertIsNone(loaded.truncation)
            self.assertIsNone(loaded.padding)
            self.assertEqual(len(loaded.encode('word ' * 100).ids), 102)

    def test_no_text_is_rejected(self):
        with patch('app.services.chunking._get_tokenizer', return_value=small_tokenizer()):
            with self.assertRaises(chunking.ChunkingError):
                chunking.chunk_document(ExtractedDocument(1, ()))


class SchemaAndCliTests(unittest.TestCase):
    def test_unsafe_filenames_are_rejected(self):
        for name in ('../file.pdf', 'C:\\file.pdf', 'CON.pdf', 'bad\x00.pdf', 'x.txt', 'x' * 256 + '.pdf'):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                DocumentUploadMetadata(filename=name, content_type='application/pdf')
        self.assertEqual(DocumentUploadMetadata(
            filename=' report.PDF ', content_type='application/pdf',
        ).filename, 'report.PDF')

    def test_invalid_internal_batches_are_rejected(self):
        chunk = dict(chunk_index=0, page_number=1, content='text')
        for chunks in ([chunk, chunk], [{**chunk, 'page_number': 3}], [chunk] * 257):
            with self.subTest(size=len(chunks)), self.assertRaises(ValidationError):
                IngestionPayload(document_id=uuid4(), page_count=2, chunks=chunks)

    def test_cli_module_starts(self):
        for arguments in (['-m', 'scripts.ingest'], ['scripts/ingest.py']):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, *arguments, '--help'],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('document.pdf', result.stdout)

    def test_cli_reads_with_a_file_size_bound(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'large.pdf'
            path.write_bytes(b'x' * 20)
            with patch('scripts.ingest.MAX_PDF_BYTES', 10):
                with self.assertRaises(PDFExtractionError):
                    read_pdf(path)


class UploadApiTests(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.provider_patch = patch('app.api.v1.documents.get_embedding_provider', return_value=StubEmbeddings())
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        lookup = patch('app.services.ingestion.find_document_by_hash', new_callable=AsyncMock, return_value=None)
        lookup.start()
        self.addCleanup(lookup.stop)

    @async_test
    async def test_upload_validation_statuses(self):
        cases = (
            ('text.txt', b'plain', 'text/plain', 415),
            ('../bad.pdf', make_pdf('text'), 'application/pdf', 422),
            ('empty.pdf', b'', 'application/pdf', 422),
            ('bad.pdf', b'not pdf', 'application/pdf', 422),
            ('filter.pdf', make_pdf('text', unsupported_filter=True), 'application/pdf', 422),
            ('encrypted.pdf', make_pdf('text', encrypted=True), 'application/pdf', 422),
            ('image.pdf', make_pdf(None, image_only=True), 'application/pdf', 422),
        )
        async with api_client() as client:
            for filename, data, mime, expected in cases:
                with self.subTest(filename=filename):
                    response = await client.post('/v1/documents/upload', files={'file': (filename, data, mime)})
                    self.assertEqual(response.status_code, expected, response.text)
            with patch('app.api.v1.documents.MAX_PDF_BYTES', 10):
                response = await client.post('/v1/documents/upload', files={'file': ('big.pdf', b'x' * 11, 'application/pdf')})
                self.assertEqual(response.status_code, 413)
            self.assertEqual((await client.post('/v1/documents/upload')).status_code, 422)

    @async_test
    async def test_unknown_file_size_is_still_bounded(self):
        upload = UploadFile(BytesIO(b'x' * 11), filename='big.pdf')
        with patch('app.api.v1.documents.MAX_PDF_BYTES', 10):
            with self.assertRaises(HTTPException) as caught:
                await read_limited_pdf(upload)
        self.assertEqual(caught.exception.status_code, 413)
        await upload.close()

    @async_test
    async def test_new_existing_and_pending_response_contracts(self):
        async with api_client() as client:
            for status, existed, expected in (('ready', False, 201), ('ready', True, 200), ('pending', True, 409)):
                result = IngestionResult(uuid4(), 'test.pdf', 1, 1, status, existed)
                with self.subTest(status=status, existed=existed), patch(
                    'app.api.v1.documents.ingest_pdf', new_callable=AsyncMock, return_value=result,
                ):
                    response = await client.post('/v1/documents/upload', files={'file': ('test.pdf', make_pdf('text'), 'application/pdf')})
                    self.assertEqual(response.status_code, expected, response.text)
                    if expected == 409:
                        self.assertEqual(response.headers['retry-after'], '5')
                    else:
                        self.assertEqual(response.json()['document_id'], str(result.document_id))

    @async_test
    async def test_processing_and_database_failures_are_retryable(self):
        async with api_client() as client:
            for failure in (IngestionProcessingError('private detail'), SQLAlchemyError('private detail')):
                with self.subTest(error=type(failure).__name__), patch(
                    'app.api.v1.documents.ingest_pdf', new_callable=AsyncMock, side_effect=failure,
                ):
                    response = await client.post('/v1/documents/upload', files={'file': ('test.pdf', make_pdf('text'), 'application/pdf')})
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn('private detail', response.text)

    @async_test
    async def test_provider_configuration_errors_are_not_bad_pdf_errors(self):
        with patch('app.api.v1.documents.get_embedding_provider', side_effect=ValueError('bad config')):
            async with api_client() as client:
                response = await client.post('/v1/documents/upload', files={'file': ('test.pdf', make_pdf('text'), 'application/pdf')})
        self.assertEqual(response.status_code, 503)
