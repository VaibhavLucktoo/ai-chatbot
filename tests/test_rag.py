"""Test POST /v1/chat without a running database or model server.

Run with: uv run pytest tests/test_rag.py -v
"""

from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.chat import get_db_session
from app.api.v1.router import api_router
from app.providers.base import BaseEmbeddingProvider
from app.services import rag
from app.services.llm import LLMTimeoutError
from app.services.rag import INSUFFICIENT_CONTEXT_ANSWER
from app.services.retrieval import RetrievalResult
from app.storage.documents import StoredChunkResult


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def db_session() -> Iterator[AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    yield session
    session.execute.assert_not_awaited()


@pytest.fixture
def app(db_session: AsyncMock) -> Iterator[FastAPI]:
    """Use production routes without the database startup lifecycle."""
    application = FastAPI()
    application.include_router(api_router, prefix="/v1")

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_db_session
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI, anyio_backend: str) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


@pytest.fixture
def embedding_provider(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Prevent real embedding configuration and model initialization."""
    provider = Mock(spec=BaseEmbeddingProvider)
    monkeypatch.setattr(rag, "get_embedding_provider", Mock(return_value=provider))
    return provider


@pytest.fixture
def retrieve_chunks_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch the imported function where the RAG service calls it."""
    retrieve = AsyncMock(spec=rag.retrieve_chunks)
    monkeypatch.setattr(rag, "retrieve_chunks", retrieve)
    return retrieve


@pytest.fixture
def generate_llm_response_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    generate = AsyncMock(spec=rag.generate_llm_response)
    monkeypatch.setattr(rag, "generate_llm_response", generate)
    return generate


@pytest.fixture
def mock_chunks() -> list[StoredChunkResult]:
    return [
        StoredChunkResult(
            chunk_id=UUID("00000000-0000-0000-0000-000000000101"),
            document_id=UUID("00000000-0000-0000-0000-000000000001"),
            filename="architecture.pdf",
            page_number=2,
            chunk_index=0,
            content="Document vectors are stored in PostgreSQL using pgvector.",
            cosine_distance=0.08,
        ),
        StoredChunkResult(
            chunk_id=UUID("00000000-0000-0000-0000-000000000202"),
            document_id=UUID("00000000-0000-0000-0000-000000000002"),
            filename="embeddings.pdf",
            page_number=7,
            chunk_index=3,
            content="Each document chunk has a 384-dimensional embedding.",
            cosine_distance=0.17,
        ),
    ]


async def test_successful_rag_answer_returns_matching_sources(
    client: httpx.AsyncClient,
    db_session: AsyncMock,
    embedding_provider: Mock,
    retrieve_chunks_mock: AsyncMock,
    generate_llm_response_mock: AsyncMock,
    mock_chunks: list[StoredChunkResult],
) -> None:
    question = "Where are document vectors stored, and how many dimensions do they have?"
    expected_answer = (
        "Document vectors are stored in PostgreSQL using pgvector [1]. "
        "Each embedding has 384 dimensions [2]."
    )
    retrieve_chunks_mock.return_value = RetrievalResult(
        query=question,
        top_k=2,
        chunks=mock_chunks,
    )
    generate_llm_response_mock.return_value = expected_answer

    response = await client.post(
        "/v1/chat",
        json={"question": f"  {question}  ", "top_k": 2},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "answer": expected_answer,
        "sources": [
            {
                "document_id": str(chunk.document_id),
                "chunk_id": str(chunk.chunk_id),
                "filename": chunk.filename,
                "page_number": chunk.page_number,
            }
            for chunk in mock_chunks
        ],
    }
    retrieve_chunks_mock.assert_awaited_once_with(
        database=db_session,
        embeddings=embedding_provider,
        query=question,
        top_k=2,
        document_ids=None,
    )
    generate_llm_response_mock.assert_awaited_once()

    prompt = generate_llm_response_mock.await_args.args[0]
    assert question in prompt
    assert "ONLY" in generate_llm_response_mock.await_args.kwargs["system_prompt"]
    for chunk in mock_chunks:
        assert chunk.content in prompt
        assert chunk.filename in prompt
        assert str(chunk.chunk_id) in prompt


async def test_empty_retrieval_returns_fallback_without_invoking_llm(
    client: httpx.AsyncClient,
    db_session: AsyncMock,
    embedding_provider: Mock,
    retrieve_chunks_mock: AsyncMock,
    generate_llm_response_mock: AsyncMock,
) -> None:
    question = "What is the company's travel policy?"
    retrieve_chunks_mock.return_value = RetrievalResult(
        query=question,
        top_k=5,
        chunks=[],
    )

    response = await client.post("/v1/chat", json={"question": question})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "answer": INSUFFICIENT_CONTEXT_ANSWER,
        "sources": [],
    }
    retrieve_chunks_mock.assert_awaited_once_with(
        database=db_session,
        embeddings=embedding_provider,
        query=question,
        top_k=5,
        document_ids=None,
    )
    generate_llm_response_mock.assert_not_called()
    generate_llm_response_mock.assert_not_awaited()


async def test_llm_timeout_returns_http_504(
    client: httpx.AsyncClient,
    db_session: AsyncMock,
    embedding_provider: Mock,
    retrieve_chunks_mock: AsyncMock,
    generate_llm_response_mock: AsyncMock,
    mock_chunks: list[StoredChunkResult],
) -> None:
    question = "Where are document vectors stored?"
    retrieve_chunks_mock.return_value = RetrievalResult(
        query=question,
        top_k=2,
        chunks=mock_chunks,
    )
    private_error = "Private upstream connection details must not reach the client."
    generate_llm_response_mock.side_effect = LLMTimeoutError(private_error)

    response = await client.post(
        "/v1/chat",
        json={"question": question, "top_k": 2},
    )

    assert response.status_code == 504, response.text
    assert response.json() == {
        "detail": "The language model timed out. Please try again.",
    }
    assert private_error not in response.text
    retrieve_chunks_mock.assert_awaited_once_with(
        database=db_session,
        embeddings=embedding_provider,
        query=question,
        top_k=2,
        document_ids=None,
    )
    generate_llm_response_mock.assert_awaited_once()
