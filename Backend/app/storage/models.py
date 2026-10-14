from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Float,
    Numeric,
    LargeBinary,
    JSON,
    Boolean,
    Index,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deliberately fixed schema contracts, not read from .env.
EMBEDDING_DIMENSIONS = 384
EMBEDDING_SPACE = "fastembed:bge-small-en-v1.5:384:l2:v1"


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("page_count > 0", name="positive_page_count"),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="valid_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    page_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16),
        server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    attempt_id: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    ingestion_attempts: Mapped[int] = mapped_column(Integer, server_default="0")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_content_english",
              text("to_tsvector('english'::regconfig, content)"), postgresql_using="gin"),
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_position",
        ),
        CheckConstraint("chunk_index >= 0", name="nonnegative_index"),
        CheckConstraint("page_number >= 1", name="positive_page"),
        CheckConstraint("length(btrim(content)) > 0", name="nonempty_content"),
        CheckConstraint(
            f"embedding_space = '{EMBEDDING_SPACE}'",
            name="supported_embedding_space",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding_space: Mapped[str] = mapped_column(String(128))
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR(EMBEDDING_DIMENSIONS)
    )


class ChatConversation(Base):
    """Private bounded turn memory, not persisted graph/source-passage state."""

    __tablename__ = "chat_conversations"
    __table_args__ = (Index("ix_chat_conversations_expires_at", "expires_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_key_hash: Mapped[str] = mapped_column(String(64))
    # Retained namespace, even after an assistant is removed. Legacy chats use NULL.
    assistant_id: Mapped[UUID | None] = mapped_column(nullable=True)
    history: Mapped[list] = mapped_column(JSON, server_default="[]")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_id: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatMetric(Base):
    """Measured request metadata only. No questions, answers or visitor identifiers."""
    __tablename__ = "chat_metrics"
    __table_args__ = (Index("ix_chat_metrics_started_at", "started_at"),
                      Index("ix_chat_metrics_assistant_started_at", "assistant_id", "started_at"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    instance_id: Mapped[UUID] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    endpoint: Mapped[str] = mapped_column(String(32))
    workflow_version: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(16))
    http_status: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(40))
    intent: Mapped[str | None] = mapped_column(String(24))
    error_type: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[float] = mapped_column(Float)
    graph_ms: Mapped[float | None] = mapped_column(Float)
    retrieval_performed: Mapped[bool] = mapped_column(Boolean)
    result_count: Mapped[int] = mapped_column(Integer)
    source_count: Mapped[int] = mapped_column(Integer)
    stage_timings_ms: Mapped[dict] = mapped_column(JSON)
    # Historical configuration snapshots deliberately have no cascading FK.
    assistant_id: Mapped[UUID | None] = mapped_column(nullable=True)
    assistant_name: Mapped[str | None] = mapped_column(String(100))
    assistant_revision: Mapped[int | None] = mapped_column(Integer)
    connection_id: Mapped[UUID | None] = mapped_column(nullable=True)
    connection_revision: Mapped[int | None] = mapped_column(Integer)
    configured_provider: Mapped[str | None] = mapped_column(String(16))
    configured_model: Mapped[str | None] = mapped_column(String(200))


class ModelCallMetric(Base):
    """One generation attempt; missing usage/prices are NULL rather than zero."""
    __tablename__ = "model_call_metrics"
    __table_args__ = (Index("ix_model_call_metrics_request_id", "request_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("chat_metrics.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(200))
    provider: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    error_type: Mapped[str | None] = mapped_column(String(64))
    provider_requested: Mapped[bool] = mapped_column(Boolean)
    http_status: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[float] = mapped_column(Float)
    queue_ms: Mapped[float | None] = mapped_column(Float)
    provider_ms: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 10))


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        CheckConstraint("provider IN ('groq', 'gemini')", name="supported_provider"),
        CheckConstraint("revision > 0", name="positive_revision"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(16))
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Assistant(Base):
    __tablename__ = "assistants"
    __table_args__ = (
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("max_output_tokens BETWEEN 64 AND 8192", name="output_limit"),
        CheckConstraint("context_window_tokens BETWEEN 4096 AND 1048576", name="context_limit"),
        CheckConstraint("context_window_tokens > max_output_tokens * 5 + 4560", name="usable_context"),
        CheckConstraint("temperature BETWEEN 0 AND 2", name="temperature_limit"),
        CheckConstraint("timeout_seconds > 0 AND timeout_seconds <= 600", name="timeout_limit"),
        Index("ix_assistants_connection_id", "connection_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), server_default="")
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("provider_connections.id", ondelete="RESTRICT"))
    model: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    max_output_tokens: Mapped[int] = mapped_column(Integer, server_default="2048")
    context_window_tokens: Mapped[int] = mapped_column(Integer, server_default="32768")
    temperature: Mapped[float] = mapped_column(Float, server_default="0")
    timeout_seconds: Mapped[float] = mapped_column(Float, server_default="120")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssistantDocument(Base):
    __tablename__ = "assistant_documents"
    __table_args__ = (Index("ix_assistant_documents_document_id", "document_id"),)
    assistant_id: Mapped[UUID] = mapped_column(ForeignKey("assistants.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)


class WebsiteWidget(Base):
    __tablename__ = "website_widgets"
    __table_args__ = (
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("requests_per_minute BETWEEN 1 AND 120", name="minute_limit"),
        CheckConstraint("requests_per_day BETWEEN 1 AND 10000", name="day_limit"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assistant_id: Mapped[UUID] = mapped_column(ForeignKey("assistants.id", ondelete="CASCADE"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")
    title: Mapped[str] = mapped_column(String(100))
    greeting: Mapped[str] = mapped_column(String(500))
    color: Mapped[str] = mapped_column(String(7))
    position: Mapped[str] = mapped_column(String(5))
    allowed_origins: Mapped[list] = mapped_column(JSON, server_default="[]")
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    requests_per_minute: Mapped[int] = mapped_column(Integer, server_default="20")
    requests_per_day: Mapped[int] = mapped_column(Integer, server_default="500")
    usage: Mapped[dict] = mapped_column(JSON, server_default="{}")


class WidgetSession(Base):
    __tablename__ = "widget_sessions"
    __table_args__ = (Index("ix_widget_sessions_expires_at", "expires_at"), Index("ix_widget_sessions_widget_id", "widget_id"))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    widget_id: Mapped[UUID] = mapped_column(ForeignKey("website_widgets.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64))
    conversation_id: Mapped[UUID] = mapped_column()
    widget_revision: Mapped[int] = mapped_column(Integer)
    parent_origin: Mapped[str] = mapped_column(String(300))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usage: Mapped[dict] = mapped_column(JSON, server_default="{}")
    allowed_chunks: Mapped[list] = mapped_column(JSON, server_default="[]")
