"""
Test HTTP per le route /garanzie/*.

Copre: lista, form creazione, creazione (con e senza lavoro collegato),
eliminazione (propria e altrui), creazione lavoro da garanzia, multi-tenant.
"""
from datetime import date

import pytest

from app import models, crud

oggi = date.today()
oggi_str = str(oggi)


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username):
    u = models.Utente(
        username=username, password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _cliente(db, utente_id):
    c = models.Cliente(
        utente_id=utente_id, tipo_cliente="privato",
        nome="Marco", cognome="Neri",
        data_creazione=oggi_str,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _garanzia(db, utente_id, cliente_id, lavoro_id=None, descrizione="Caldaia murale"):
    return crud.crea_garanzia(
        db, utente_id, cliente_id,
        lavoro_id=lavoro_id,
        descrizione=descrizione,
        data_installazione=oggi_str,
        durata_mesi=24,
        note="",
    )


def _lavoro(db, utente_id, cliente_id):
    l = models.Lavoro(
        utente_id=utente_id, cliente_id=cliente_id,
        titolo="Installazione caldaia", data_lavoro=oggi,
        stato="completato", priorita="normale",
        aliquota_iva=22.0, sconto=0.0, importo_pagato=0.0,
        data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


# ── GET /garanzie/ ────────────────────────────────────────────────────────────

def test_lista_garanzie_ok(client_http):
    """GET /garanzie/ → 200."""
    resp = client_http.get("/garanzie/")
    assert resp.status_code == 200


def test_lista_garanzie_mostra_solo_proprie(client_http, db, utente_test, cliente_test):
    """Lista garanzie filtra per utente → garanzie altrui non appaiono."""
    altro = _utente(db, "altro1@t.it")
    cli_altro = _cliente(db, altro.id)

    _garanzia(db, utente_test.id, cliente_test.id, descrizione="Impianto proprio XYZ")
    _garanzia(db, altro.id, cli_altro.id, descrizione="Impianto altrui ABC")

    resp = client_http.get("/garanzie/")
    assert resp.status_code == 200
    assert "Impianto proprio XYZ" in resp.text
    assert "Impianto altrui ABC" not in resp.text


# ── GET /garanzie/nuova ───────────────────────────────────────────────────────

def test_form_nuova_garanzia_ok(client_http):
    """GET /garanzie/nuova → 200."""
    resp = client_http.get("/garanzie/nuova")
    assert resp.status_code == 200


# ── POST /garanzie/nuova ─────────────────────────────────────────────────────

def test_crea_garanzia_happy_path(client_http, db, utente_test, cliente_test):
    """POST crea garanzia → garanzia in DB, redirect a /garanzie/."""
    resp = client_http.post(
        "/garanzie/nuova",
        data={
            "cliente_id": str(cliente_test.id),
            "lavoro_id": "",
            "descrizione": "Scaldabagno elettrico",
            "data_installazione": oggi_str,
            "durata_mesi": "24",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/garanzie/" in resp.headers["location"]

    garanzie = crud.get_garanzie(db, utente_test.id)
    assert len(garanzie) == 1
    assert garanzie[0].descrizione == "Scaldabagno elettrico"
    assert garanzie[0].utente_id == utente_test.id


def test_crea_garanzia_con_lavoro(client_http, db, utente_test, cliente_test):
    """POST con lavoro_id → garanzia collegata al lavoro in DB."""
    lav = _lavoro(db, utente_test.id, cliente_test.id)

    resp = client_http.post(
        "/garanzie/nuova",
        data={
            "cliente_id": str(cliente_test.id),
            "lavoro_id": str(lav.id),
            "descrizione": "Pompa di calore",
            "data_installazione": oggi_str,
            "durata_mesi": "36",
            "note": "con lavoro collegato",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    garanzie = crud.get_garanzie(db, utente_test.id)
    assert len(garanzie) == 1
    assert garanzie[0].lavoro_id == lav.id
    assert garanzie[0].durata_mesi == 36


# ── POST /garanzie/{id}/elimina ───────────────────────────────────────────────

def test_elimina_garanzia_propria(client_http, db, utente_test, cliente_test):
    """POST elimina garanzia propria → garanzia rimossa dal DB."""
    g = _garanzia(db, utente_test.id, cliente_test.id)

    resp = client_http.post(f"/garanzie/{g.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303

    garanzie = crud.get_garanzie(db, utente_test.id)
    assert len(garanzie) == 0


def test_elimina_garanzia_altrui_non_rimuove(client_http, db, utente_test):
    """POST elimina garanzia di altro utente → redirect, garanzia intatta."""
    altro = _utente(db, "altro2@t.it")
    cli = _cliente(db, altro.id)
    g = _garanzia(db, altro.id, cli.id)

    resp = client_http.post(f"/garanzie/{g.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303

    garanzie_altro = crud.get_garanzie(db, altro.id)
    assert len(garanzie_altro) == 1


# ── POST /garanzie/{id}/crea-lavoro ─────────────────────────────────────────

def test_crea_lavoro_da_garanzia(client_http, db, utente_test, cliente_test):
    """POST crea-lavoro → nuovo Lavoro in DB, redirect a /lavori/{id}."""
    g = _garanzia(db, utente_test.id, cliente_test.id, descrizione="Condizionatore")

    resp = client_http.post(f"/garanzie/{g.id}/crea-lavoro", follow_redirects=False)
    assert resp.status_code == 303

    loc = resp.headers["location"]
    assert loc.startswith("/lavori/")

    lavoro_id = int(loc.split("/lavori/")[1].rstrip("/"))
    lavoro = db.get(models.Lavoro, lavoro_id)
    assert lavoro is not None
    assert lavoro.utente_id == utente_test.id
    assert lavoro.cliente_id == cliente_test.id
    assert "Condizionatore" in lavoro.titolo


def test_crea_lavoro_da_garanzia_altrui_404(client_http, db, utente_test):
    """POST crea-lavoro su garanzia altrui → 404."""
    altro = _utente(db, "altro3@t.it")
    cli = _cliente(db, altro.id)
    g = _garanzia(db, altro.id, cli.id)

    resp = client_http.post(f"/garanzie/{g.id}/crea-lavoro", follow_redirects=False)
    assert resp.status_code == 404
