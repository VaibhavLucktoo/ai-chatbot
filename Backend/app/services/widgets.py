"""Durable widget capabilities and budgets; no provider credentials in public data."""
import secrets
from datetime import timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select, update

from app.schemas.widgets import WidgetResponse, WidgetWrite
from app.storage.models import Assistant, ProviderConnection, WebsiteWidget, WidgetSession, Document, DocumentChunk, AssistantDocument


def public_origin(database):
    return database.settings.widget_public_origin


def configuration(row, database, today=None):
    data = {key: row[key] for key in WidgetWrite.model_fields}
    usage = row["usage"] or {}
    return WidgetResponse(**data, id=row["id"], assistant_id=row["assistant_id"], revision=row["revision"],
                          public_origin=public_origin(database), public_access_enabled=database.settings.widget_public_enabled,
                          requests_today=usage.get("chat_day_count", 0) if usage.get("chat_day") == today else 0)


async def admin_widget(database, assistant_id, payload=None):
    async with database.transaction() as connection:
        if await connection.scalar(select(Assistant.id).where(Assistant.id == assistant_id).with_for_update()) is None:
            raise HTTPException(404, "Assistant not found.")
        row = (await connection.execute(select(WebsiteWidget).where(WebsiteWidget.assistant_id == assistant_id))).mappings().one_or_none()
        if payload is not None:
            if payload.enabled and not payload.allowed_origins:
                raise HTTPException(422, "Add at least one allowed website before enabling the widget.")
            values = payload.model_dump()
            if row is None:
                statement = insert(WebsiteWidget).values(id=uuid4(), assistant_id=assistant_id, **values)
            else:
                statement = update(WebsiteWidget).where(WebsiteWidget.id == row["id"]).values(**values, revision=WebsiteWidget.revision + 1)
            row = (await connection.execute(statement.returning(*WebsiteWidget.__table__.c))).mappings().one()
        if row is None:
            return None
        now = (await connection.scalar(select(func.now()))).astimezone(timezone.utc)
        return configuration(row, database, now.date().isoformat())


async def available_widget(connection, widget_id, *, lock=False):
    query = select(WebsiteWidget).join(Assistant).join(ProviderConnection, ProviderConnection.id == Assistant.connection_id).where(
        WebsiteWidget.id == widget_id, WebsiteWidget.enabled.is_(True), Assistant.active.is_(True), ProviderConnection.active.is_(True))
    if lock:
        query = query.with_for_update(of=WebsiteWidget)
    row = (await connection.execute(query)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "This widget is unavailable.")
    return row


async def widget_page(database, widget_id, parent_origin):
    async with database.transaction() as connection:
        row = await available_widget(connection, widget_id)
        require_website(row, parent_origin)
        return dict(row)


def require_website(row, origin):
    if origin not in row["allowed_origins"]:
        raise HTTPException(403, "This website is not allowed to use this widget.")


def budget(usage, now, *, category, minute_limit, day_limit):
    """Called under a row lock, shared by all processes and retained across restarts."""
    now = now.astimezone(timezone.utc)
    result = dict(usage or {})
    minute, day = now.strftime("%Y-%m-%dT%H:%M"), now.date().isoformat()
    minute_count = result.get(category + "_minute_count", 0) if result.get(category + "_minute") == minute else 0
    day_count = result.get(category + "_day_count", 0) if result.get(category + "_day") == day else 0
    if minute_count >= minute_limit or day_count >= day_limit:
        retry = 60 - now.second if minute_count >= minute_limit else int((now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1) - now).total_seconds())
        raise HTTPException(429, "Widget usage limit reached. Please try again later.", headers={"Retry-After": str(max(1, retry))})
    result.update({category + "_minute": minute, category + "_minute_count": minute_count + 1,
                   category + "_day": day, category + "_day_count": day_count + 1})
    return result


async def start_visitor(database, widget_id, parent_origin):
    token = secrets.token_hex(32)
    async with database.transaction() as connection:
        row = await available_widget(connection, widget_id, lock=True)
        require_website(row, parent_origin)
        now = await connection.scalar(select(func.now()))
        usage = budget(row["usage"], now, category="sessions", minute_limit=30,
                       day_limit=min(10000, max(100, row["requests_per_day"] * 2)))
        await connection.execute(update(WebsiteWidget).where(WebsiteWidget.id == widget_id).values(usage=usage))
        expired = select(WidgetSession.id).where(WidgetSession.expires_at <= now).limit(200)
        await connection.execute(delete(WidgetSession).where(WidgetSession.id.in_(expired)))
        session_id, conversation_id = uuid4(), uuid4()
        expires = now + timedelta(seconds=database.settings.conversation_ttl_seconds)
        await connection.execute(insert(WidgetSession).values(id=session_id, widget_id=widget_id,
            token_hash=sha256(token.encode()).hexdigest(), conversation_id=conversation_id,
            widget_revision=row["revision"], parent_origin=parent_origin, expires_at=expires))
    return {"session_id": session_id, "token": token, "expires_at": expires.isoformat()}


async def visitor(database, widget_id, session_id, token, *, consume=False):
    if not isinstance(token, str) or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise HTTPException(403, "Visitor session expired or invalid. Start a new chat.")
    async with database.transaction() as connection:
        row = await available_widget(connection, widget_id, lock=consume)
        query = select(WidgetSession).where(WidgetSession.id == session_id, WidgetSession.widget_id == widget_id,
            WidgetSession.widget_revision == row["revision"], WidgetSession.expires_at > func.now())
        if consume:
            query = query.with_for_update()
        session = (await connection.execute(query)).mappings().one_or_none()
        if session is None or not secrets.compare_digest(session["token_hash"], sha256(token.encode()).hexdigest()):
            raise HTTPException(403, "Visitor session expired or invalid. Start a new chat.")
        require_website(row, session["parent_origin"])
        if consume:
            now = await connection.scalar(select(func.now()))
            per_visitor = budget(session["usage"], now, category="chat", minute_limit=6, day_limit=row["requests_per_day"])
            usage = budget(row["usage"], now, category="chat", minute_limit=row["requests_per_minute"], day_limit=row["requests_per_day"])
            await connection.execute(update(WebsiteWidget).where(WebsiteWidget.id == widget_id).values(usage=usage))
            await connection.execute(update(WidgetSession).where(WidgetSession.id == session_id).values(usage=per_visitor))
        return dict(row), dict(session)


async def remember_sources(database, session_id, sources):
    async with database.transaction() as connection:
        saved = await connection.scalar(select(WidgetSession.allowed_chunks).where(WidgetSession.id == session_id).with_for_update())
        if saved is not None:
            chunks = list(dict.fromkeys([*saved, *(str(source.chunk_id) for source in sources)]))[-100:]
            await connection.execute(update(WidgetSession).where(WidgetSession.id == session_id).values(allowed_chunks=chunks))


async def visitor_passage(database, widget, session, chunk_id):
    if str(chunk_id) not in session["allowed_chunks"]:
        raise HTTPException(404, "Source passage unavailable.")
    async with database.transaction() as connection:
        row = (await connection.execute(select(DocumentChunk.id, DocumentChunk.document_id, Document.filename,
            DocumentChunk.page_number, DocumentChunk.chunk_index, DocumentChunk.content).join(Document).where(
            DocumentChunk.id == chunk_id, Document.status == "ready", Document.active.is_(True), Document.id.in_(
                select(AssistantDocument.document_id).where(AssistantDocument.assistant_id == widget["assistant_id"]))
        ))).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Source passage unavailable.")
    return dict(row)
