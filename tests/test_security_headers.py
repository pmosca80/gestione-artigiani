"""Verifica che ogni risposta porti gli header di sicurezza standard
(X-Frame-Options, X-Content-Type-Options, CSP, Referrer-Policy)."""


def test_header_di_sicurezza_presenti(client_http):
    resp = client_http.get("/login")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in resp.headers["content-security-policy"]


def test_hsts_assente_in_locale_http(client_http):
    """In locale (no Railway) https_only è False: niente HSTS, altrimenti
    si rischia di forzare HTTPS su un dominio servito in HTTP."""
    resp = client_http.get("/login")
    assert "strict-transport-security" not in resp.headers
