from fastapi import Request
from slowapi import Limiter


def _get_ip(request: Request) -> str:
    # Railway (e la maggior parte dei proxy) mette il vero IP in X-Forwarded-For
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return (request.client and request.client.host) or "unknown"


limiter = Limiter(key_func=_get_ip)
