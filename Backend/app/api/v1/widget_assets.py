"""Widget iframe HTML and its narrowly allowed static assets."""

import html
import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from app.api.common.routes import WidgetConfigurationRoute
from app.schemas.widgets import website_origin
from app.services.widgets import widget_page

ASSETS = Path(__file__).resolve().parents[2] / "widget"
page_router = APIRouter(route_class=WidgetConfigurationRoute)


@page_router.get("/widget/{widget_id}", response_class=HTMLResponse)
async def render_widget(widget_id: UUID, request: Request, parent_origin: str):
    try:
        parent_origin = website_origin(parent_origin)
    except ValueError:
        raise HTTPException(403, "Invalid embedding website.") from None
    row = await widget_page(request.app.state.database, widget_id, parent_origin)
    config = {
        name: row[name]
        for name in ("title", "greeting", "color", "position", "revision")
    }
    config.update(widget_id=str(widget_id), parent_origin=parent_origin)
    template = (ASSETS / "index.html").read_text(encoding="utf-8")
    text = template.replace(
        'data-config="__CONFIG__"',
        'data-config="' + html.escape(json.dumps(config), quote=True) + '"',
        1,
    )
    text = text.replace(
        "<title>__TITLE__</title>",
        "<title>" + html.escape(row["title"]) + "</title>",
        1,
    )
    # Browser framing restrictions apply to every ancestor, not just the direct parent.
    policy = (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "frame-ancestors "
        + " ".join(row["allowed_origins"])
        + "; base-uri 'none'; form-action 'none'"
    )
    return HTMLResponse(
        text,
        headers={
            "Content-Security-Policy": policy,
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@page_router.get("/widget-assets/{filename}")
async def widget_asset(filename: str):
    types = {
        "loader.js": "application/javascript",
        "chat.js": "application/javascript",
        "style.css": "text/css",
    }
    if filename not in types:
        raise HTTPException(404, "Widget asset unavailable.")
    return Response(
        (ASSETS / filename).read_bytes(),
        media_type=types[filename],
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "frame-ancestors *"},
    )
