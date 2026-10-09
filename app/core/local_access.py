"""A loopback-only development boundary, not multi-user authentication."""

from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_local_scope(scope: dict) -> bool:
    headers = dict(scope.get("headers", []))
    try:
        hostname = urlsplit("//" + headers.get(b"host", b"").decode("ascii")).hostname
        client = scope.get("client")
        return hostname in LOCAL_HOSTS and client is not None and ip_address(client[0]).is_loopback
    except (ValueError, UnicodeError):
        return False


async def require_admin_token(request: Request) -> None:
    import secrets
    if not is_local_scope(request.scope):
        raise HTTPException(403, "This admin workspace is only available on the local machine.")
    token = request.headers.get("X-Admin-Token", "")
    if not secrets.compare_digest(token, request.app.state.admin_token):
        raise HTTPException(403, "Reload the admin page to start a valid local session.")
