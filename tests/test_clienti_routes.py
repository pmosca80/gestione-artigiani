"""
Test HTTP per le route /clienti/*.

Copre: dettaglio, form modifica, modifica POST, eliminazione (propria,
altrui, bloccata da lavori), form nuovo, gate piano free.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import models, crud
from app.database import get_db
from app.dependencies import get_current_user
from app.main import app

oggi = date.today()
oggi_str = str(oggi)


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username, piano="pro"):
    u = models.Utente(
        username=username, password="x", piano=piano,
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _cliente(db, utente_id, nome="Giovanni", cognome="Verdi"):
    c = models.Cliente(
        utente_id=utente_id, tipo_cliente="privato",
        nome=nome, cognome=cognome,
        data_creazione=oggi_str,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _lavoro(db, utente_id, cliente_id):
    l = models.Lavoro(
        utente_id=utente_id, cliente_id=cliente_id,
        titolo="Lavoro collegato", data_lavoro=oggi,
        stato="in_corso", priorita="normale",
        aliquota_iva=22.0, sconto=0.0, importo_pagato=0.0,
        data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


# ── GET /clienti/{id} ────────────────────────────────────────────────────────

def test_dettaglio_cliente_ok(client_http, db, utente_test, cliente_test):
    """GET dettaglio cliente proprio → 200 con nome nel testo."""
    resp = client_http.get(f"/clienti/{cliente_test.id}")
    assert resp.status_code == 200
    assert cliente_test.nome in resp.text


def test_dettaglio_cliente_altrui_404(client_http, db, utente_test):
    """GET dettaglio cliente di altro utente → 404."""
    altro = _utente(db, "altro1@t.it")
    cli = _cliente(db, altro.id)

    resp = client_http.get(f"/clienti/{cli.id}")
    assert resp.status_code == 404


# ── GET /clienti/{id}/modifica ────────────────────────────────────────────────

def test_form_modifica_cliente_ok(client_http, db, utente_test, cliente_test):
    """GET form modifica cliente proprio → 200."""
    resp = client_http.get(f"/clienti/{cliente_test.id}/modifica")
    assert resp.status_code == 200


def test_form_modifica_cliente_altrui_404(client_http, db, utente_test):
    """GET form modifica cliente altrui → 404."""
    altro = _utente(db, "altro2@t.it")
    cli = _cliente(db, altro.id)

    resp = client_http.get(f"/clienti/{cli.id}/modifica")
    assert resp.status_code == 404


# ── POST /clienti/{id}/modifica ───────────────────────────────────────────────

def test_modifica_cliente_aggiorna_campi(client_http, db, utente_test, cliente_test):
    """POST modifica → campi aggiornati in DB, redirect a /clienti/{id}."""
    resp = client_http.post(
        f"/clienti/{cliente_test.id}/modifica",
        data={
            "tipo_cliente": "azienda",
            "nome": "Luca",
            "cognome": "Bianchi",
            "ragione_sociale": "Bianchi Srl",
            "telefono": "0612345678",
            "email": "luca@bianchi.it",
            "indirizzo": "Via Roma 10",
            "citta": "Roma",
            "provincia": "RM",
            "cap": "00100",
            "partita_iva": "12345678901",
            "codice_fiscale": "",
            "codice_destinatario": "",
            "pec_destinatario": "",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/clienti/{cliente_test.id}" in resp.headers["location"]

    db.refresh(cliente_test)
    assert cliente_test.nome == "Luca"
    assert cliente_test.tipo_cliente == "azienda"


def test_modifica_cliente_altrui_404(client_http, db, utente_test):
    """POST modifica cliente di altro utente → 404."""
    altro = _utente(db, "altro3@t.it")
    cli = _cliente(db, altro.id)

    resp = client_http.post(
        f"/clienti/{cli.id}/modifica",
        data={
            "tipo_cliente": "privato",
            "nome": "Tentativo",
            "cognome": "Hacker",
            "ragione_sociale": "",
            "telefono": "",
            "email": "",
            "indirizzo": "",
            "citta": "",
            "provincia": "",
            "cap": "",
            "partita_iva": "",
            "codice_fiscale": "",
            "codice_destinatario": "",
            "pec_destinatario": "",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── POST /clienti/{id}/elimina ────────────────────────────────────────────────

def test_elimina_cliente_proprio(client_http, db, utente_test, cliente_test):
    """POST elimina cliente senza lavori → redirect a /clienti."""
    resp = client_http.post(f"/clienti/{cliente_test.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303
    assert "/clienti" in resp.headers["location"]

    rimasto = db.get(models.Cliente, cliente_test.id)
    assert rimasto is None


def test_elimina_cliente_altrui_404(client_http, db, utente_test):
    """POST elimina cliente di altro utente → 404."""
    altro = _utente(db, "altro4@t.it")
    cli = _cliente(db, altro.id)

    resp = client_http.post(f"/clienti/{cli.id}/elimina", follow_redirects=False)
    assert resp.status_code == 404


def test_elimina_cliente_con_lavori_bloccato(client_http, db, utente_test, cliente_test):
    """POST elimina cliente con lavori collegati → redirect con errore=ha_lavori."""
    _lavoro(db, utente_test.id, cliente_test.id)

    resp = client_http.post(f"/clienti/{cliente_test.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303
    assert "errore=ha_lavori" in resp.headers["location"]

    rimasto = db.get(models.Cliente, cliente_test.id)
    assert rimasto is not None


# ── GET /clienti/nuovo ────────────────────────────────────────────────────────

def test_form_nuovo_cliente_ok(client_http):
    """GET /clienti/nuovo → 200."""
    resp = client_http.get("/clienti/nuovo")
    assert resp.status_code == 200


# ── Piano free al limite clienti ─────────────────────────────────────────────

def test_crea_cliente_piano_free_al_limite(db):
    """Piano free con 5 clienti → redirect a /piani?limite=clienti."""
    u_free = _utente(db, "free1@t.it", piano="free")
    for i in range(5):
        _cliente(db, u_free.id, nome=f"Cliente{i}", cognome="Test")

    def _db(): yield db
    def _user(): return u_free.id
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user

    with TestClient(app, raise_server_exceptions=True) as c:
        resp = c.post(
            "/clienti/nuovo",
            data={"nome": "Extra", "cognome": "Sesto", "tipo_cliente": "privato"},
            follow_redirects=False,
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 303
    assert "/piani" in resp.headers["location"]
    assert "limite=clienti" in resp.headers["location"]

    totale = db.query(models.Cliente).filter(models.Cliente.utente_id == u_free.id).count()
    assert totale == 5
