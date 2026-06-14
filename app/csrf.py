from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Endpoint che ricevono POST da service worker o webhook esterni
_EXEMPT = frozenset([
    "/notifiche/push/subscribe",
    "/notifiche/push/unsubscribe",
])


class CSRFMiddleware(BaseHTTPMiddleware):
    """Valida Origin/Referer su ogni richiesta mutante per bloccare CSRF cross-site."""

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.url.path not in _EXEMPT:
                host = request.headers.get("host", "").split(":")[0]
                origin = request.headers.get("origin", "")
                referer = request.headers.get("referer", "")
                check = origin or referer
                if check:
                    parsed = urlparse(check)
                    if parsed.hostname and parsed.hostname != host:
                        return Response(
                            "Richiesta non autorizzata",
                            status_code=403,
                            media_type="text/plain",
                        )
        return await call_next(request)
