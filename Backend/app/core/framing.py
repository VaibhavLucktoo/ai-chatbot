"""Shared widget routing and response framing policy for both access boundaries."""

import re


WORKSPACE_CSP = (
    b"default-src 'self'; script-src 'self'; "
    b"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    b"font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; "
    b"connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; "
    b"object-src 'none'; base-uri 'none'; form-action 'self'"
)
LOCAL_CSP = (
    b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    b"connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
)


def widget_route(scope):
    path, method = scope.get("path", ""), scope.get("method")
    return bool(
        (method == "GET" and (
            re.fullmatch(r"/widget/[0-9a-fA-F-]{36}", path)
            or path.startswith("/widget-assets/")
        ))
        or (path.startswith("/v1/widget/") and method in {"GET", "POST"})
    )


def framing_headers(headers, *, widget, asset=False, workspace_policy=WORKSPACE_CSP):
    """Emit one CSP header; preserve route CSP and remove XFO for widgets."""
    policies = list(dict.fromkeys(value for name, value in headers
                                 if name.lower() == b"content-security-policy"))
    headers = [(name, value) for name, value in headers
               if name.lower() not in {b"x-frame-options", b"content-security-policy"}]
    if widget:
        policy = (b"frame-ancestors *" if asset else
                  b", ".join(policies) if policies else b"frame-ancestors 'none'")
    else:
        # Preserve other CSP restrictions while making framing protection explicit.
        policies = policies or [workspace_policy]
        policy = b", ".join(
            b"; ".join(part.strip() for part in item.split(b";")
                       if part.strip() and part.strip().split()[0].lower() != b"frame-ancestors")
            + b"; frame-ancestors 'none'" for item in policies
        )
        headers.append((b"x-frame-options", b"DENY"))
    headers.append((b"content-security-policy", policy))
    return headers
