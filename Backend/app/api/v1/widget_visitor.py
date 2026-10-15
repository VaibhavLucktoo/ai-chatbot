"""Visitor sessions, scoped chat and issued source passages."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.api.common.routes import WidgetConfigurationRoute
from app.api.dependencies import get_db_session
from app.schemas.chat import ChatRequest, ChatResponse, ClarificationResponse
from app.schemas.widgets import (
    VisitorChat,
    VisitorSession,
    VisitorStart,
    WidgetPassageResponse,
)
from app.services.chat_service import run_chat
from app.services.widgets import (
    start_visitor,
    visitor,
    visitor_passage,
    remember_sources,
)

router = APIRouter(
    prefix="/widget", tags=["website widget"], route_class=WidgetConfigurationRoute
)


@router.post("/{widget_id}/sessions", response_model=VisitorSession, status_code=201)
async def start(widget_id: UUID, payload: VisitorStart, request: Request):
    return await start_visitor(
        request.app.state.database, widget_id, payload.parent_origin
    )


@router.post(
    "/{widget_id}/sessions/{session_id}/chat",
    response_model=ChatResponse | ClarificationResponse,
)
async def widget_chat(
    widget_id: UUID,
    session_id: UUID,
    payload: VisitorChat,
    request: Request,
    token: str | None = Header(default=None, alias="X-Widget-Token"),
    db=Depends(get_db_session, scope="function"),
):
    database = request.app.state.database
    widget, session = await visitor(
        database, widget_id, session_id, token, consume=True
    )
    result = await run_chat(
        db,
        ChatRequest(
            question=payload.question,
            top_k=5,
            document_ids=payload.document_ids,
            assistant_id=widget["assistant_id"],
            conversation_id=session["conversation_id"],
        ),
        conversation_database=database,
        conversation_key=token,
    )
    if isinstance(result, ChatResponse):
        await remember_sources(database, session_id, result.sources)
    return result


@router.get(
    "/{widget_id}/sessions/{session_id}/passages/{chunk_id}",
    response_model=WidgetPassageResponse,
)
async def passage(
    widget_id: UUID,
    session_id: UUID,
    chunk_id: UUID,
    request: Request,
    token: str | None = Header(default=None, alias="X-Widget-Token"),
):
    database = request.app.state.database
    widget, session = await visitor(database, widget_id, session_id, token)
    return await visitor_passage(database, widget, session, chunk_id)
