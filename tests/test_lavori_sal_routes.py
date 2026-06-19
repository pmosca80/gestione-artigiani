"""
Test HTTP per le route /lavori/{id}/sal/*.

Copre: lista SAL, crea SAL (happy path, importo con virgola, lavoro altrui → 404),
toggle stato emesso/pagato, elimina (proprio e altrui), PDF SAL.
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


def _lavoro(db, utente_id, titolo="Ristrutturazione bagno"):
    c = _cliente(db, utente_id)
    l = models.Lavoro(
        utente_id=utente_id,
        cliente_id=c.id,
        titolo=titolo,
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        importo_preventivato=3000.0,
        aliquota_iva=22.0,
        sconto=0.0,
        importo_pagato=0.0,
        residuo_pagamento=3000.0,
        data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


def _sal(db, utente_id, lavoro_id, percentuale=30.0, importo=900.0):
    return crud.crea_sal(
        db, utente_id, lavoro_id,
        data=oggi_str,
        percentuale=percentuale,
        importo_richiesto=importo,
        descrizione="Prima tranche di lavori",
        note="",
    )


# ── GET /lavori/{id}/sal ──────────────────────────────────────────────────────

def test_lista_sal_ok(client_http, lavoro_test):
    """GET /lavori/{id}/sal → 200."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}/sal")
    assert resp.status_code == 200


def test_lista_sal_lavoro_altrui_404(client_http, db):
    """GET /lavori/{id}/sal con lavoro altrui → 404."""
    altro = _utente(db, "altro1@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.get(f"/lavori/{lav.id}/sal")
    assert resp.status_code == 404


# ── POST /lavori/{id}/sal/nuovo ───────────────────────────────────────────────

def test_crea_sal_happy_path(client_http, db, utente_test, lavoro_test):
    """POST sal/nuovo → SAL in DB con dati corretti, redirect."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/sal/nuovo",
        data={
            "data": oggi_str,
            "percentuale": "40",
            "importo_richiesto": "800.00",
            "descrizione": "Demolizioni e scavi",
            "note": "Verificare fondazioni",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/lavori/{lavoro_test.id}/sal" in resp.headers["location"]

    sal_list = crud.get_sal_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(sal_list) == 1
    assert sal_list[0].percentuale == 40.0
    assert sal_list[0].importo_richiesto == 800.0
    assert sal_list[0].descrizione == "Demolizioni e scavi"
    assert sal_list[0].utente_id == utente_test.id
    assert sal_list[0].numero == 1


def test_crea_sal_importo_negativo_non_registrato(client_http, db, utente_test, lavoro_test):
    """Regressione: un SAL con importo negativo veniva registrato, falsificando
    il totale già richiesto/pagato sul lavoro."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/sal/nuovo",
        data={
            "data": oggi_str,
            "percentuale": "40",
            "importo_richiesto": "-800",
            "descrizione": "SAL con importo negativo",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert crud.get_sal_lavoro(db, utente_test.id, lavoro_test.id) == []


def test_crea_sal_importo_virgola(client_http, db, utente_test, lavoro_test):
    """POST con importo in formato italiano ('750,50') → 750.5 in DB."""
    client_http.post(
        f"/lavori/{lavoro_test.id}/sal/nuovo",
        data={
            "data": oggi_str,
            "percentuale": "25",
            "importo_richiesto": "750,50",
            "descrizione": "SAL con virgola",
            "note": "",
        },
        follow_redirects=False,
    )

    sal_list = crud.get_sal_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(sal_list) == 1
    assert abs(sal_list[0].importo_richiesto - 750.5) < 0.01


def test_crea_sal_lavoro_altrui_404(client_http, db):
    """POST sal/nuovo su lavoro altrui → 404."""
    altro = _utente(db, "altro2@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.post(
        f"/lavori/{lav.id}/sal/nuovo",
        data={
            "data": oggi_str,
            "percentuale": "50",
            "importo_richiesto": "1000",
            "descrizione": "Tentativo",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── POST /lavori/{id}/sal/{sal_id}/stato ──────────────────────────────────────

def test_toggle_sal_stato_emesso_a_pagato(client_http, db, utente_test, lavoro_test):
    """POST /stato su SAL emesso → stato 'pagato'."""
    sal = _sal(db, utente_test.id, lavoro_test.id)
    assert sal.stato == "emesso"

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/sal/{sal.id}/stato",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(sal)
    assert sal.stato == "pagato"


def test_toggle_sal_stato_pagato_a_emesso(client_http, db, utente_test, lavoro_test):
    """POST /stato due volte → torna allo stato 'emesso'."""
    sal = _sal(db, utente_test.id, lavoro_test.id)

    client_http.post(f"/lavori/{lavoro_test.id}/sal/{sal.id}/stato", follow_redirects=False)
    client_http.post(f"/lavori/{lavoro_test.id}/sal/{sal.id}/stato", follow_redirects=False)

    db.refresh(sal)
    assert sal.stato == "emesso"


def test_toggle_sal_altrui_no_effetto(client_http, db, utente_test, lavoro_test):
    """POST /stato su SAL altrui → stato invariato (CRUD filtra per utente_id)."""
    altro = _utente(db, "altro3@t.it")
    lav_altro = _lavoro(db, altro.id)
    sal = _sal(db, altro.id, lav_altro.id)

    client_http.post(
        f"/lavori/{lav_altro.id}/sal/{sal.id}/stato",
        follow_redirects=False,
    )

    db.refresh(sal)
    assert sal.stato == "emesso"


# ── POST /lavori/{id}/sal/{sal_id}/elimina ────────────────────────────────────

def test_elimina_sal_proprio(client_http, db, utente_test, lavoro_test):
    """POST /elimina → SAL rimosso dal DB."""
    sal = _sal(db, utente_test.id, lavoro_test.id)

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/sal/{sal.id}/elimina",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    sal_list = crud.get_sal_lavoro(db, utente_test.id, lavoro_test.id)
    assert len(sal_list) == 0


def test_elimina_sal_altrui_no_effetto(client_http, db, utente_test, lavoro_test):
    """POST elimina SAL altrui → SAL altrui intatto."""
    altro = _utente(db, "altro4@t.it")
    lav_altro = _lavoro(db, altro.id)
    sal = _sal(db, altro.id, lav_altro.id)

    client_http.post(
        f"/lavori/{lav_altro.id}/sal/{sal.id}/elimina",
        follow_redirects=False,
    )

    sal_list = crud.get_sal_lavoro(db, altro.id, lav_altro.id)
    assert len(sal_list) == 1


# ── GET /lavori/{id}/sal/{sal_id}/pdf ─────────────────────────────────────────

def test_pdf_sal_ok(client_http, db, utente_test, lavoro_test):
    """GET /pdf → 200, content-type application/pdf."""
    sal = _sal(db, utente_test.id, lavoro_test.id)

    resp = client_http.get(f"/lavori/{lavoro_test.id}/sal/{sal.id}/pdf")
    assert resp.status_code == 200
    assert "pdf" in resp.headers["content-type"]
