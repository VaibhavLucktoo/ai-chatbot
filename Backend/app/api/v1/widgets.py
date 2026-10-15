"""Deprecated widget import locations; import focused modules for new code."""

# Re-export existing router objects and handlers; do not construct extra routes here.
from app.api.v1.widget_admin import (
    admin_router as admin_router,
    get_widget as get_widget,
    save_widget as save_widget,
)
from app.api.v1.widget_assets import (
    ASSETS as ASSETS,
    page_router as page_router,
    render_widget as render_widget,
    widget_asset as widget_asset,
)
from app.api.v1.widget_visitor import (
    router as router,
    start as start,
    widget_chat as widget_chat,
    passage as passage,
)
