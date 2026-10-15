"""CI smoke test of the built image using synthetic PDFs and a disposable database."""

import io
import os
import time

import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def synthetic_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({
            NameObject('/F1'): DictionaryObject({
                NameObject('/Type'): NameObject('/Font'),
                NameObject('/Subtype'): NameObject('/Type1'),
                NameObject('/BaseFont'): NameObject('/Helvetica'),
            }),
        }),
    })
    stream = DecodedStreamObject()
    text = 'Synthetic document passage for hosted indexing verification. ' * 2000
    stream.set_data(f'BT /F1 12 Tf 40 740 Td ({text}) Tj ET'.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main():
    # Refuse to run this destructive smoke test against arbitrary live services.
    if os.getenv('HOSTED_SMOKE_TEST') != '1' or os.getenv('POSTGRES_DB') != 'chatbot_smoke':
        raise RuntimeError('This check requires the disposable chatbot_smoke database.')
    with httpx.Client(base_url='http://127.0.0.1:8000', headers={'Host': 'smoke.example.com'},
                      auth=(os.environ['WORKSPACE_USERNAME'], os.environ['WORKSPACE_PASSWORD']),
                      timeout=10) as client:
        for _ in range(120):
            try:
                if client.get('/v1/ready').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Hosted app did not become ready.')
        page = client.get('/')
        assert page.status_code == 200 and 'Document Assistant' in page.text
        uploaded = client.post('/v1/documents/jobs', files={'file': ('synthetic.pdf', synthetic_pdf(), 'application/pdf')})
        assert uploaded.status_code == 202, uploaded.text
        identifier = uploaded.json()['document_id']
        for _ in range(120):
            job = client.get(f'/v1/documents/jobs/{identifier}')
            assert job.status_code == 200, job.text
            state = job.json()['status']
            assert state != 'failed', 'Synthetic PDF processing failed; inspect the container logs.'
            assert client.get('/v1/health').status_code == 200
            if state == 'ready':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Synthetic PDF did not finish indexing.')
        document = client.get(f'/v1/documents/{identifier}').json()
        assert document['chunk_count'] > 32
        assert client.delete(f'/v1/documents/{identifier}').status_code == 204
        assert client.get(f'/v1/documents/{identifier}').status_code == 404
        print('Hosted runtime passed: offline model/tokenizer caches, PDF indexing, liveness during processing, and deletion.')


if __name__ == '__main__':
    main()
