"""
Test HTTP per le route del portale cliente.

Copre: portale pubblico (GET /portale/{token} — no auth), token non trovato → 404,
contenuto pagina (nome cliente, lavori attivi vs annullati), generazione token
(POST /clienti/{id}/genera-portale), genera-portale cliente altrui → 404.
"""
from datetime import date

import pytest

from app import models, crud

oggi_str = str(date.today())


# ── Helper di setup ────────────────────────────────────────────────────────────

def _utente(db, username):
    u = models.Utente(
        username=username, password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


# ── GET /portale/{token} — nessuna autenticazione richiesta ───────────────────

def test_portale_token_valido(client_http, db, cliente_test):
    """GET /portale/{token} con token valido → 200."""
    cliente_test.token_portale = "tok-abc123"
    db.commit()

    resp = client_http.get("/portale/tok-abc123")
    assert resp.status_code == 200


def test_portale_token_non_trovato(client_http):
    """GET /portale/{token} con token inesistente → 404."""
    resp = client_http.get("/portale/token-che-non-esiste-xyz")
    assert resp.status_code == 404


def test_portale_mostra_nome_cliente(client_http, db, cliente_test):
    """Portale mostra nome e cognome del cliente."""
    cliente_test.token_portale = "tok-nome"
    db.commit()

    resp = client_http.get("/portale/tok-nome")
    assert resp.status_code == 200
    assert "Mario" in resp.text
    assert "Rossi" in resp.text


def test_portale_mostra_lavori_attivi(client_http, db, cliente_test, lavoro_test):
    """Portale mostra lavori non annullati del cliente."""
    cliente_test.token_portale = "tok-lavori"
    db.commit()

    resp = client_http.get("/portale/tok-lavori")
    assert resp.status_code == 200
    assert lavoro_test.titolo in resp.text


def test_portale_non_mostra_lavori_annullati(client_http, db, cliente_test, lavoro_test):
    """Portale esclude lavori con stato='annullato'."""
    lavoro_test.stato = "annullato"
    db.commit()
    cliente_test.token_portale = "tok-annullato"
    db.commit()

    resp = client_http.get("/portale/tok-annullato")
    assert resp.status_code == 200
    assert lavoro_test.titolo not in resp.text


# ── POST /clienti/{id}/genera-portale ────────────────────────────────────────

def test_genera_portale_ok(client_http, db, cliente_test):
    """POST genera-portale → token generato, redirect a /clienti/{id}."""
    assert cliente_test.token_portale is None

    resp = client_http.post(
        f"/clienti/{cliente_test.id}/genera-portale",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/clienti/{cliente_test.id}" in resp.headers["location"]

    db.refresh(cliente_test)
    assert cliente_test.token_portale is not None
    assert len(cliente_test.token_portale) > 10


def test_genera_portale_token_diverso_ogni_volta(client_http, db, cliente_test):
    """POST genera-portale due volte → token rinnovato."""
    client_http.post(f"/clienti/{cliente_test.id}/genera-portale", follow_redirects=False)
    db.refresh(cliente_test)
    primo_token = cliente_test.token_portale

    client_http.post(f"/clienti/{cliente_test.id}/genera-portale", follow_redirects=False)
    db.refresh(cliente_test)
    secondo_token = cliente_test.token_portale

    assert primo_token != secondo_token


def test_genera_portale_cliente_altrui_404(client_http, db):
    """POST genera-portale su cliente altrui → 404."""
    altro = _utente(db, "altro1@t.it")
    c_altro = models.Cliente(
        utente_id=altro.id, tipo_cliente="privato",
        nome="Altro", cognome="Cliente", data_creazione=oggi_str,
    )
    db.add(c_altro); db.commit(); db.refresh(c_altro)

    resp = client_http.post(
        f"/clienti/{c_altro.id}/genera-portale",
        follow_redirects=False,
    )
    assert resp.status_code == 404
