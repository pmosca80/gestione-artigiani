from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# CSP permissiva sugli script/stili inline: il markup esistente ne fa uso
# estensivo in decine di template. Restringerlo a nonce/hash è un refactor
# a parte; qui chiudiamo comunque l'esecuzione di script da domini non
# allowlistati e il caricamento di plugin/oggetti esterni.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://res.cloudinary.com; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Aggiunge gli header di sicurezza standard a ogni risposta."""

    def __init__(self, app, https_only: bool = False):
        super().__init__(app)
        self.https_only = https_only

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = _CSP
        if self.https_only:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
