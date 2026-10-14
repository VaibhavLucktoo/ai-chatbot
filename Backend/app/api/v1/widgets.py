"""Local widget administration and a separate visitor API."""
import html
import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.api.v1.assistants import ConfigurationRoute
from app.api.v1.chat import get_db_session, run_chat
from app.core.local_access import require_admin_token
from app.schemas.chat import ChatRequest, ChatResponse, ClarificationResponse
from app.schemas.widgets import VisitorChat, VisitorSession, VisitorStart, WidgetResponse, WidgetWrite, website_origin
from app.services.widgets import admin_widget, start_visitor, visitor, visitor_passage, widget_page, remember_sources

ASSETS = Path(__file__).resolve().parents[2] / "widget"
admin_router = APIRouter(prefix="/admin/assistants", tags=["website widget administration"],
    route_class=ConfigurationRoute, dependencies=[Depends(require_admin_token)])
router = APIRouter(prefix="/widget", tags=["website widget"], route_class=ConfigurationRoute)
page_router = APIRouter(route_class=ConfigurationRoute)


@admin_router.get("/{assistant_id}/widget", response_model=WidgetResponse | None)
async def get_widget(assistant_id: UUID, request: Request):
    return await admin_widget(request.app.state.database, assistant_id)


@admin_router.put("/{assistant_id}/widget", response_model=WidgetResponse)
async def save_widget(assistant_id: UUID, payload: WidgetWrite, request: Request):
    return await admin_widget(request.app.state.database, assistant_id, payload)


@page_router.get("/widget/{widget_id}", response_class=HTMLResponse)
async def render_widget(widget_id: UUID, request: Request, parent_origin: str):
    try:
        parent_origin = website_origin(parent_origin)
    except ValueError:
        raise HTTPException(403, "Invalid embedding website.") from None
    row = await widget_page(request.app.state.database, widget_id, parent_origin)
    config = {name: row[name] for name in ("title", "greeting", "color", "position", "revision")}
    config.update(widget_id=str(widget_id), parent_origin=parent_origin)
    template = (ASSETS / "index.html").read_text(encoding="utf-8")
    text = template.replace('data-config="__CONFIG__"', 'data-config="' + html.escape(json.dumps(config), quote=True) + '"', 1)
    text = text.replace('<title>__TITLE__</title>', '<title>' + html.escape(row["title"]) + '</title>', 1)
    # Browser framing restrictions apply to every ancestor, not just the direct parent.
    policy = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
              "frame-ancestors " + " ".join(row["allowed_origins"]) + "; base-uri 'none'; form-action 'none'")
    return HTMLResponse(text, headers={"Content-Security-Policy": policy, "Cache-Control": "no-store",
                                      "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})


@page_router.get("/widget-assets/{filename}")
async def widget_asset(filename: str):
    types = {"loader.js": "application/javascript", "chat.js": "application/javascript", "style.css": "text/css"}
    if filename not in types:
        raise HTTPException(404, "Widget asset unavailable.")
    return Response((ASSETS / filename).read_bytes(), media_type=types[filename],
                    headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


@router.post("/{widget_id}/sessions", response_model=VisitorSession, status_code=201)
async def start(widget_id: UUID, payload: VisitorStart, request: Request):
    return await start_visitor(request.app.state.database, widget_id, payload.parent_origin)


@router.post("/{widget_id}/sessions/{session_id}/chat", response_model=ChatResponse | ClarificationResponse)
async def widget_chat(widget_id: UUID, session_id: UUID, payload: VisitorChat, request: Request,
                      token: str | None = Header(default=None, alias="X-Widget-Token"),
                      db=Depends(get_db_session, scope="function")):
    database = request.app.state.database
    widget, session = await visitor(database, widget_id, session_id, token, consume=True)
    result = await run_chat(db, ChatRequest(question=payload.question, top_k=5, document_ids=payload.document_ids,
        assistant_id=widget["assistant_id"], conversation_id=session["conversation_id"]),
        conversation_database=database, conversation_key=token)
    if isinstance(result, ChatResponse):
        await remember_sources(database, session_id, result.sources)
    return result


@router.get("/{widget_id}/sessions/{session_id}/passages/{chunk_id}")
async def passage(widget_id: UUID, session_id: UUID, chunk_id: UUID, request: Request,
                  token: str | None = Header(default=None, alias="X-Widget-Token")):
    database = request.app.state.database
    widget, session = await visitor(database, widget_id, session_id, token)
    return await visitor_passage(database, widget, session, chunk_id)
