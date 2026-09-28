import asyncio
from functools import wraps
from io import BytesIO
import unittest
from uuid import uuid4

import httpx
from fastapi import FastAPI
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject
from tokenizers import Tokenizer, models, pre_tokenizers, processors

from app.api.v1.documents import router
from app.providers.base import BaseEmbeddingProvider
from app.storage.models import EMBEDDING_SPACE
from run import create_event_loop


def make_pdf(*pages, encrypted=False, unsupported_filter=False, image_only=False):
    """Small, generated fixtures keep tests independent of personal documents."""
    writer = PdfWriter()
    writer.add_metadata({'/TestID': uuid4().hex})
    for content in pages:
        page = writer.add_blank_page(width=612, height=792)
        if content is None and not image_only:
            continue
        stream = DecodedStreamObject()
        if image_only:
            picture = DecodedStreamObject()
            picture.set_data(b'\xff\xff\xff')
            picture.update({
                NameObject('/Type'): NameObject('/XObject'),
                NameObject('/Subtype'): NameObject('/Image'),
                NameObject('/Width'): NumberObject(1),
                NameObject('/Height'): NumberObject(1),
                NameObject('/BitsPerComponent'): NumberObject(8),
                NameObject('/ColorSpace'): NameObject('/DeviceRGB'),
            })
            page[NameObject('/Resources')] = DictionaryObject({
                NameObject('/XObject'): DictionaryObject({
                    NameObject('/Im0'): writer._add_object(picture),
                }),
            })
            stream.set_data(b'q 100 0 0 100 0 0 cm /Im0 Do Q')
        else:
            page[NameObject('/Resources')] = DictionaryObject({
                NameObject('/Font'): DictionaryObject({
                    NameObject('/F1'): DictionaryObject({
                        NameObject('/Type'): NameObject('/Font'),
                        NameObject('/Subtype'): NameObject('/Type1'),
                        NameObject('/BaseFont'): NameObject('/Helvetica'),
                    }),
                }),
            })
            escaped = content.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            stream.set_data(f'BT /F1 12 Tf 40 740 Td ({escaped}) Tj ET'.encode('latin-1'))
        if unsupported_filter:
            stream[NameObject('/Filter')] = NameObject('/UnsupportedTestFilter')
        page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('test-password')
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def small_tokenizer():
    tokenizer = Tokenizer(models.WordLevel(
        {'[UNK]': 0, '[CLS]': 1, '[SEP]': 2, 'word': 3}, unk_token='[UNK]',
    ))
    tokenizer.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    tokenizer.post_processor = processors.TemplateProcessing(
        single='[CLS] $A [SEP]', special_tokens=[('[CLS]', 1), ('[SEP]', 2)],
    )
    return tokenizer


class StubEmbeddings(BaseEmbeddingProvider):
    dimensions = 384
    space_id = EMBEDDING_SPACE

    def __init__(self):
        self.batch_sizes = []

    async def embed_documents(self, texts):
        self.batch_sizes.append(len(texts))
        return [[1.0] + [0.0] * 383 for _ in texts]

    async def embed_query(self, text):
        return [1.0] + [0.0] * 383


def api_client(database=None):
    application = FastAPI()
    application.state.database = database
    application.include_router(router, prefix='/v1')
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url='http://test',
    )


def async_test(function):
    @wraps(function)
    def run(self):
        return self.runner.run(function(self))
    return run


class AsyncTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        # Psycopg requires a selector loop on Windows, including during tests.
        self.runner = asyncio.Runner(loop_factory=create_event_loop)
        self.addCleanup(self.runner.close)
