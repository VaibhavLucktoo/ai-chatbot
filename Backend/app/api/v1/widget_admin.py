"""Local widget settings endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.common.routes import WidgetConfigurationRoute
from app.core.local_access import require_admin_token
from app.schemas.widgets import WidgetResponse, WidgetWrite
from app.services.widgets import admin_widget

admin_router = APIRouter(
    prefix="/admin/assistants",
    tags=["website widget administration"],
    route_class=WidgetConfigurationRoute,
    dependencies=[Depends(require_admin_token)],
)


@admin_router.get("/{assistant_id}/widget", response_model=WidgetResponse | None)
async def get_widget(assistant_id: UUID, request: Request):
    return await admin_widget(request.app.state.database, assistant_id)


@admin_router.put("/{assistant_id}/widget", response_model=WidgetResponse)
async def save_widget(assistant_id: UUID, payload: WidgetWrite, request: Request):
    return await admin_widget(request.app.state.database, assistant_id, payload)
