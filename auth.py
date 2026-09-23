import ipaddress
import secrets
from urllib.parse import parse_qs

from starlette.responses import JSONResponse

PROTECTED_PREFIXES = ("/api/", "/live")
LOCAL_NETWORKS = [
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
]


def is_local(host):
    try:
        ip = ipaddress.ip_address(host)
    except (TypeError, ValueError):
        return False
    return any(ip in net for net in LOCAL_NETWORKS)


def _request_token(scope):
    for name, value in scope["headers"]:
        if name == b"authorization":
            scheme, _, token = value.decode().partition(" ")
            if scheme.lower() == "bearer":
                return token
    query = parse_qs(scope.get("query_string", b"").decode())
    return query.get("token", [None])[0]


class TokenAuthMiddleware:
    def __init__(self, app, token):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not scope["path"].startswith(PROTECTED_PREFIXES)
            or is_local((scope.get("client") or (None,))[0])
        ):
            return await self.app(scope, receive, send)

        given = _request_token(scope)
        if self.token and given and secrets.compare_digest(given, self.token):
            return await self.app(scope, receive, send)

        response = JSONResponse({"detail": "Invalid or missing access token"}, 401)
        await response(scope, receive, send)
