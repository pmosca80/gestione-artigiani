"""
Test HTTP per le route /lavori/{id}/timesheet/*.

Copre: lista timesheet, crea entry (happy path, ore con virgola,
lavoro altrui → 404), elimina (propria e altrui), multi-tenant.
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


def _lavoro(db, utente_id, titolo="Impianto elettrico"):
    c = _cliente(db, utente_id)
    l = models.Lavoro(
        utente_id=utente_id,
        cliente_id=c.id,
        titolo=titolo,
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        importo_preventivato=2500.0,
        aliquota_iva=22.0,
        sconto=0.0,
        importo_pagato=0.0,
        residuo_pagamento=2500.0,
        data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


def _entry(db, utente_id, lavoro_id, nome="Luca Bianchi", ore=6.0, costo=30.0):
    return crud.crea_timesheet_entry(
        db, utente_id, lavoro_id,
        nome_operaio=nome,
        data=oggi_str,
        ore=ore,
        costo_orario=costo,
        note="",
    )


# ── GET /lavori/{id}/timesheet ────────────────────────────────────────────────

def test_lista_timesheet_ok(client_http, lavoro_test):
    """GET /lavori/{id}/timesheet → 200."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}/timesheet")
    assert resp.status_code == 200


def test_lista_timesheet_lavoro_altrui_404(client_http, db):
    """GET /timesheet con lavoro altrui → 404."""
    altro = _utente(db, "altro1@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.get(f"/lavori/{lav.id}/timesheet")
    assert resp.status_code == 404


# ── POST /lavori/{id}/timesheet/nuovo ────────────────────────────────────────

def test_crea_timesheet_entry_happy_path(client_http, db, utente_test, lavoro_test):
    """POST timesheet/nuovo → entry in DB con dati corretti, redirect."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/timesheet/nuovo",
        data={
            "nome_operaio": "Marco Ferrari",
            "data": oggi_str,
            "ore": "8",
            "costo_orario": "35.00",
            "note": "Cablaggio pannello",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/lavori/{lavoro_test.id}/timesheet" in resp.headers["location"]

    entries = crud.get_timesheet_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(entries) == 1
    assert entries[0].nome_operaio == "Marco Ferrari"
    assert entries[0].ore == 8.0
    assert entries[0].costo_orario == 35.0
    assert entries[0].utente_id == utente_test.id


def test_crea_timesheet_entry_ore_virgola(client_http, db, utente_test, lavoro_test):
    """POST con ore in formato italiano ('6,5') → 6.5 in DB."""
    client_http.post(
        f"/lavori/{lavoro_test.id}/timesheet/nuovo",
        data={
            "nome_operaio": "Paolo Verdi",
            "data": oggi_str,
            "ore": "6,5",
            "costo_orario": "28",
            "note": "",
        },
        follow_redirects=False,
    )

    entries = crud.get_timesheet_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(entries) == 1
    assert abs(entries[0].ore - 6.5) < 0.01


def test_crea_timesheet_entry_lavoro_altrui_404(client_http, db):
    """POST timesheet/nuovo su lavoro altrui → 404."""
    altro = _utente(db, "altro2@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.post(
        f"/lavori/{lav.id}/timesheet/nuovo",
        data={
            "nome_operaio": "Intruso",
            "data": oggi_str,
            "ore": "4",
            "costo_orario": "20",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── POST /lavori/{id}/timesheet/{entry_id}/elimina ───────────────────────────

def test_elimina_timesheet_entry_propria(client_http, db, utente_test, lavoro_test):
    """POST /elimina → entry rimossa dal DB."""
    entry = _entry(db, utente_test.id, lavoro_test.id)

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/timesheet/{entry.id}/elimina",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    entries = crud.get_timesheet_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(entries) == 0


def test_elimina_timesheet_entry_altrui_no_effetto(client_http, db, utente_test, lavoro_test):
    """POST elimina entry altrui → entry altrui intatta."""
    altro = _utente(db, "altro3@t.it")
    lav_altro = _lavoro(db, altro.id)
    entry = _entry(db, altro.id, lav_altro.id)

    client_http.post(
        f"/lavori/{lav_altro.id}/timesheet/{entry.id}/elimina",
        follow_redirects=False,
    )

    entries_altro = crud.get_timesheet_lavoro(db, altro.id, lav_altro.id)
    assert len(entries_altro) == 1
