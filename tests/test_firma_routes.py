"""
Test HTTP per le route /firma/* (portale firma preventivo — pubblico, no auth).

Copre: visualizza preventivo per firma (GET /firma/{token}), token invalido → 404,
firma accetta (POST /firma/{token}/accetta → redirect, stato aggiornato, nome salvato),
lavoro in stato non-preventivo → redirect immediato senza modifiche,
preventivo già accettato → dati non riscritti, conferma firma (GET /firma/{token}/ok).
"""
from datetime import date

import pytest

from app import models

_DATA_TEST = date(2025, 1, 15)

oggi_str = str(date.today())


# ── Helper ────────────────────────────────────────────────────────────────────

def _imposta_token(db, lavoro, token, stato="preventivo"):
    lavoro.token_firma = token
    lavoro.stato = stato
    db.commit()
    db.refresh(lavoro)


# ── GET /firma/{token} ────────────────────────────────────────────────────────

def test_firma_page_token_valido(client_http, db, lavoro_test):
    """GET /firma/{token} con token valido → 200."""
    _imposta_token(db, lavoro_test, "tok-firma-001")

    resp = client_http.get("/firma/tok-firma-001")
    assert resp.status_code == 200


def test_firma_page_token_non_trovato(client_http):
    """GET /firma/{token} con token inesistente → 404."""
    resp = client_http.get("/firma/token-inesistente-xyz")
    assert resp.status_code == 404


# ── POST /firma/{token}/accetta ───────────────────────────────────────────────

def test_firma_accetta_happy_path(client_http, db, lavoro_test):
    """POST /accetta su lavoro in stato 'preventivo' → redirect /ok, stato 'preventivo_accettato'."""
    _imposta_token(db, lavoro_test, "tok-firma-002", stato="preventivo")

    resp = client_http.post(
        "/firma/tok-firma-002/accetta",
        data={"nome_cliente": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/firma/tok-firma-002/ok" in resp.headers["location"]

    db.refresh(lavoro_test)
    assert lavoro_test.stato == "preventivo_accettato"


def test_firma_accetta_con_nome_cliente(client_http, db, lavoro_test):
    """POST /accetta con nome_cliente → lavoro.firma_nome_cliente salvato, stato accettato."""
    _imposta_token(db, lavoro_test, "tok-firma-003", stato="preventivo_inviato")

    client_http.post(
        "/firma/tok-firma-003/accetta",
        data={"nome_cliente": "Giovanni Verdi"},
        follow_redirects=False,
    )

    db.refresh(lavoro_test)
    assert lavoro_test.firma_nome_cliente == "Giovanni Verdi"
    assert lavoro_test.stato == "preventivo_accettato"


def test_firma_accetta_senza_nome_non_imposta_firma_nome(client_http, db, lavoro_test):
    """POST /accetta senza nome_cliente → firma_nome_cliente non modificato (rimane None)."""
    _imposta_token(db, lavoro_test, "tok-firma-004", stato="preventivo")

    client_http.post(
        "/firma/tok-firma-004/accetta",
        data={"nome_cliente": ""},
        follow_redirects=False,
    )

    db.refresh(lavoro_test)
    assert lavoro_test.firma_nome_cliente is None
    assert lavoro_test.stato == "preventivo_accettato"


def test_firma_accetta_token_non_trovato(client_http):
    """POST /firma/{token}/accetta con token inesistente → 404."""
    resp = client_http.post(
        "/firma/token-non-esiste/accetta",
        data={"nome_cliente": "Qualcuno"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


def test_firma_accetta_stato_non_preventivo_redirect_immediato(client_http, db, lavoro_test):
    """POST /accetta su lavoro con stato 'in_corso' → redirect immediato, stato invariato."""
    _imposta_token(db, lavoro_test, "tok-firma-005", stato="in_corso")

    resp = client_http.post(
        "/firma/tok-firma-005/accetta",
        data={"nome_cliente": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/firma/tok-firma-005/ok" in resp.headers["location"]

    db.refresh(lavoro_test)
    assert lavoro_test.stato == "in_corso"


def test_firma_accetta_preventivo_gia_accettato_non_riscrive_data(client_http, db, lavoro_test):
    """POST /accetta su preventivo già accettato → data_accettazione e stato invariati."""
    lavoro_test.token_firma = "tok-firma-006"
    lavoro_test.stato = "preventivo_accettato"
    lavoro_test.data_accettazione_preventivo = _DATA_TEST
    db.commit()
    db.refresh(lavoro_test)

    client_http.post(
        "/firma/tok-firma-006/accetta",
        data={"nome_cliente": ""},
        follow_redirects=False,
    )

    db.refresh(lavoro_test)
    assert lavoro_test.stato == "preventivo_accettato"
    assert lavoro_test.data_accettazione_preventivo == _DATA_TEST


def test_firma_accetta_preventivo_gia_accettato_non_sovrascrive_nome_firma(client_http, db, lavoro_test):
    """Regressione: il link /firma/{token} non scade e resta visitabile anche
    dopo l'accettazione. Una seconda submission (es. chiunque riapra il
    link e prema di nuovo "Confermo" con un nome diverso) non deve poter
    sovrascrivere il nome/IP della prima firma — altrimenti il valore
    probatorio di "chi ha accettato" verrebbe vanificato."""
    lavoro_test.token_firma = "tok-firma-008"
    lavoro_test.stato = "preventivo_accettato"
    lavoro_test.firma_nome_cliente = "Mario Rossi"
    lavoro_test.firma_ip = "1.2.3.4"
    db.commit()
    db.refresh(lavoro_test)

    resp = client_http.post(
        "/firma/tok-firma-008/accetta",
        data={"nome_cliente": "Qualcun altro"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/firma/tok-firma-008/ok" in resp.headers["location"]

    db.refresh(lavoro_test)
    assert lavoro_test.firma_nome_cliente == "Mario Rossi"
    assert lavoro_test.firma_ip == "1.2.3.4"


# ── GET /firma/{token}/ok ─────────────────────────────────────────────────────

def test_firma_ok_token_valido(client_http, db, lavoro_test):
    """GET /firma/{token}/ok con token valido → 200."""
    _imposta_token(db, lavoro_test, "tok-firma-007", stato="preventivo_accettato")

    resp = client_http.get("/firma/tok-firma-007/ok")
    assert resp.status_code == 200


def test_firma_ok_token_non_trovato(client_http):
    """GET /firma/{token}/ok con token inesistente → 404."""
    resp = client_http.get("/firma/token-inesistente-ok/ok")
    assert resp.status_code == 404
