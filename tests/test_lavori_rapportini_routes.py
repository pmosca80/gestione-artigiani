"""
Test HTTP per le route /lavori/{id}/rapportini/*.

Copre: lista rapportini, crea rapportino (happy path, ore con virgola,
lavoro altrui → 404), elimina (proprio e altrui), PDF rapportino.
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


def _cliente(db, utente_id):
    c = models.Cliente(
        utente_id=utente_id, tipo_cliente="privato",
        nome="Test", cognome="Cliente", data_creazione=oggi_str,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _lavoro(db, utente_id, titolo="Posa pavimento"):
    c = _cliente(db, utente_id)
    l = models.Lavoro(
        utente_id=utente_id,
        cliente_id=c.id,
        titolo=titolo,
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        importo_preventivato=1500.0,
        aliquota_iva=22.0,
        sconto=0.0,
        importo_pagato=0.0,
        residuo_pagamento=1500.0,
        data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


def _rapportino(db, utente_id, lavoro_id, ore=6.0, descrizione="Posa piastrelle"):
    return crud.crea_rapportino(
        db, utente_id, lavoro_id,
        data=oggi_str,
        ore_lavorate=ore,
        descrizione_attivita=descrizione,
        materiali_note="",
        note="",
    )


# ── GET /lavori/{id}/rapportini ───────────────────────────────────────────────

def test_lista_rapportini_ok(client_http, lavoro_test):
    """GET /lavori/{id}/rapportini → 200."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}/rapportini")
    assert resp.status_code == 200


def test_lista_rapportini_lavoro_altrui_404(client_http, db):
    """GET /rapportini con lavoro altrui → 404."""
    altro = _utente(db, "altro1@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.get(f"/lavori/{lav.id}/rapportini")
    assert resp.status_code == 404


# ── POST /lavori/{id}/rapportini/nuovo ───────────────────────────────────────

def test_crea_rapportino_happy_path(client_http, db, utente_test, lavoro_test):
    """POST rapportini/nuovo → rapportino in DB con dati corretti, redirect."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/rapportini/nuovo",
        data={
            "data": oggi_str,
            "ore_lavorate": "8",
            "descrizione_attivita": "Installazione termosifoni",
            "materiali_note": "Termosifoni x3, raccordi",
            "note": "Nessuna criticità",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/lavori/{lavoro_test.id}/rapportini" in resp.headers["location"]

    rapportini = crud.get_rapportini_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(rapportini) == 1
    assert rapportini[0].ore_lavorate == 8.0
    assert rapportini[0].descrizione_attivita == "Installazione termosifoni"
    assert rapportini[0].materiali_note == "Termosifoni x3, raccordi"
    assert rapportini[0].utente_id == utente_test.id


def test_crea_rapportino_ore_virgola(client_http, db, utente_test, lavoro_test):
    """POST con ore in formato italiano ('7,5') → 7.5 in DB."""
    client_http.post(
        f"/lavori/{lavoro_test.id}/rapportini/nuovo",
        data={
            "data": oggi_str,
            "ore_lavorate": "7,5",
            "descrizione_attivita": "Rapportino con virgola",
            "materiali_note": "",
            "note": "",
        },
        follow_redirects=False,
    )

    rapportini = crud.get_rapportini_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(rapportini) == 1
    assert abs(rapportini[0].ore_lavorate - 7.5) < 0.01


def test_crea_rapportino_lavoro_altrui_404(client_http, db):
    """POST rapportini/nuovo su lavoro altrui → 404."""
    altro = _utente(db, "altro2@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.post(
        f"/lavori/{lav.id}/rapportini/nuovo",
        data={
            "data": oggi_str,
            "ore_lavorate": "4",
            "descrizione_attivita": "Tentativo accesso",
            "materiali_note": "",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── POST /lavori/{id}/rapportini/{id}/elimina ─────────────────────────────────

def test_elimina_rapportino_proprio(client_http, db, utente_test, lavoro_test):
    """POST /elimina → rapportino rimosso dal DB."""
    r = _rapportino(db, utente_test.id, lavoro_test.id)

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/rapportini/{r.id}/elimina",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    rapportini = crud.get_rapportini_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(rapportini) == 0


def test_elimina_rapportino_altrui_no_effetto(client_http, db, utente_test, lavoro_test):
    """POST elimina rapportino altrui → rapportino altrui intatto."""
    altro = _utente(db, "altro3@t.it")
    lav_altro = _lavoro(db, altro.id)
    r = _rapportino(db, altro.id, lav_altro.id)

    client_http.post(
        f"/lavori/{lav_altro.id}/rapportini/{r.id}/elimina",
        follow_redirects=False,
    )

    rapportini_altro = crud.get_rapportini_lavoro(db, altro.id, lav_altro.id)
    assert len(rapportini_altro) == 1


# ── GET /lavori/{id}/rapportini/{id}/pdf ─────────────────────────────────────

def test_pdf_rapportino_ok(client_http, db, utente_test, lavoro_test):
    """GET /pdf → 200, content-type application/pdf."""
    r = _rapportino(db, utente_test.id, lavoro_test.id, ore=4.0,
                    descrizione="Test PDF rapportino")

    resp = client_http.get(f"/lavori/{lavoro_test.id}/rapportini/{r.id}/pdf")
    assert resp.status_code == 200
    assert "pdf" in resp.headers["content-type"]
