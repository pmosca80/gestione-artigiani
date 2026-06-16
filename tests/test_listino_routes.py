"""
Test HTTP per le route /listino/*.

Copre: lista HTML, API JSON, creazione, modifica (propria e altrui),
eliminazione (propria e altrui), isolamento multi-tenant.
"""
from datetime import date

import pytest

from app import models, crud

oggi_str = str(date.today())


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username):
    u = models.Utente(
        username=username, password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _voce(db, utente_id, descrizione="Posa tubi", prezzo=25.0, categoria="idraulica"):
    return crud.crea_listino_voce(
        db, utente_id,
        descrizione=descrizione,
        unita_misura="ora",
        prezzo_unitario=prezzo,
        categoria=categoria,
    )


# ── GET /listino/ ──────────────────────────────────────────────────────────────

def test_lista_listino_ok(client_http):
    """GET /listino/ → 200."""
    resp = client_http.get("/listino/")
    assert resp.status_code == 200


def test_lista_mostra_solo_proprie(client_http, db, utente_test):
    """Lista HTML filtra per utente → voci altrui non appaiono."""
    altro = _utente(db, "altro1@t.it")
    _voce(db, utente_test.id, descrizione="Voce propria XYZ")
    _voce(db, altro.id, descrizione="Voce altrui ABC")

    resp = client_http.get("/listino/")
    assert resp.status_code == 200
    assert "Voce propria XYZ" in resp.text
    assert "Voce altrui ABC" not in resp.text


# ── GET /listino/api/json ─────────────────────────────────────────────────────

def test_listino_json_ok(client_http, db, utente_test):
    """GET /listino/api/json → 200, lista JSON con le proprie voci."""
    _voce(db, utente_test.id, descrizione="Manodopera elettrica", prezzo=30.0)

    resp = client_http.get("/listino/api/json")
    assert resp.status_code == 200
    dati = resp.json()
    assert isinstance(dati, list)
    assert len(dati) == 1
    assert dati[0]["descrizione"] == "Manodopera elettrica"
    assert dati[0]["prezzo_unitario"] == 30.0


def test_listino_json_non_mostra_altrui(client_http, db, utente_test):
    """GET /listino/api/json non include voci di altri utenti."""
    altro = _utente(db, "altro2@t.it")
    _voce(db, altro.id, descrizione="Voce segreta altrui")

    resp = client_http.get("/listino/api/json")
    dati = resp.json()
    assert all(v["descrizione"] != "Voce segreta altrui" for v in dati)


# ── POST /listino/nuovo ────────────────────────────────────────────────────────

def test_crea_voce_happy_path(client_http, db, utente_test):
    """POST /listino/nuovo → voce in DB, redirect a /listino/."""
    resp = client_http.post(
        "/listino/nuovo",
        data={
            "descrizione": "Installazione rubinetto",
            "unita_misura": "pz",
            "prezzo_unitario": "45.00",
            "categoria": "idraulica",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/listino/" in resp.headers["location"]

    voci = crud.get_listino(db, utente_test.id)
    assert len(voci) == 1
    assert voci[0].descrizione == "Installazione rubinetto"
    assert voci[0].prezzo_unitario == 45.0
    assert voci[0].utente_id == utente_test.id


def test_crea_voce_prezzo_virgola(client_http, db, utente_test):
    """POST con prezzo in formato italiano ('12,50') → 12.5 in DB."""
    client_http.post(
        "/listino/nuovo",
        data={
            "descrizione": "Guarnizione gomma",
            "unita_misura": "pz",
            "prezzo_unitario": "12,50",
            "categoria": "materiali",
        },
        follow_redirects=False,
    )

    voci = crud.get_listino(db, utente_test.id)
    assert len(voci) == 1
    assert abs(voci[0].prezzo_unitario - 12.5) < 0.01


# ── POST /listino/{id}/modifica ───────────────────────────────────────────────

def test_modifica_voce_propria(client_http, db, utente_test):
    """POST /{id}/modifica → campi aggiornati in DB, redirect."""
    voce = _voce(db, utente_test.id)

    resp = client_http.post(
        f"/listino/{voce.id}/modifica",
        data={
            "descrizione": "Posa tubi PEX",
            "unita_misura": "m",
            "prezzo_unitario": "18.00",
            "categoria": "idraulica",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(voce)
    assert voce.descrizione == "Posa tubi PEX"
    assert voce.unita_misura == "m"
    assert voce.prezzo_unitario == 18.0


def test_modifica_voce_altrui_no_effetto(client_http, db, utente_test):
    """POST modifica voce di altro utente → redirect, descrizione invariata."""
    altro = _utente(db, "altro3@t.it")
    voce = _voce(db, altro.id, descrizione="Originale ABC")

    client_http.post(
        f"/listino/{voce.id}/modifica",
        data={
            "descrizione": "Alterata XYZ",
            "unita_misura": "ora",
            "prezzo_unitario": "99.00",
            "categoria": "altro",
        },
        follow_redirects=False,
    )

    db.refresh(voce)
    assert voce.descrizione == "Originale ABC"


# ── POST /listino/{id}/elimina ────────────────────────────────────────────────

def test_elimina_voce_propria(client_http, db, utente_test):
    """POST /{id}/elimina → voce rimossa dal DB."""
    voce = _voce(db, utente_test.id)

    resp = client_http.post(f"/listino/{voce.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303

    voci = crud.get_listino(db, utente_test.id)
    assert len(voci) == 0


def test_elimina_voce_altrui_no_effetto(client_http, db, utente_test):
    """POST elimina voce altrui → redirect, voce intatta."""
    altro = _utente(db, "altro4@t.it")
    voce = _voce(db, altro.id)

    client_http.post(f"/listino/{voce.id}/elimina", follow_redirects=False)

    voci_altro = crud.get_listino(db, altro.id)
    assert len(voci_altro) == 1
