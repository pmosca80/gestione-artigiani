from fastapi import Request
from slowapi import Limiter


def _get_ip(request: Request) -> str:
    # Railway (e la maggior parte dei proxy) mette il vero IP in X-Forwarded-For
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return (request.client and request.client.host) or "unknown"


def _get_user_or_ip(request: Request) -> str:
    # Per route autenticate: chiave per user_id evita falsi positivi su NAT condivisi
    user_id = request.session.get("user_id")
    if user_id:
        return f"user:{user_id}"
    return _get_ip(request)


limiter = Limiter(key_func=_get_ip)
user_limiter = Limiter(key_func=_get_user_or_ip)
