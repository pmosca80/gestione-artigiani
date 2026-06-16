"""
Test HTTP per le route /documenti/* (PDF fattura, PDF preventivo, archivio, FatturaPA XML).

Copre: archivio documenti (GET /documenti/ → 200), scarica PDF preventivo (happy path,
lavoro altrui → 404), scarica PDF fattura (happy path, senza numero_fattura → 404,
lavoro altrui → 404), fattura-xml con dati azienda mancanti → 422, apri documento
inesistente → 404, apri documento con file non presente su disco → 404.
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


def _lavoro(db, utente_id, titolo="Lavoro test"):
    c = _cliente(db, utente_id)
    l = models.Lavoro(
        utente_id=utente_id,
        cliente_id=c.id,
        titolo=titolo,
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        importo_preventivato=1000.0,
        aliquota_iva=22.0,
        sconto=0.0,
        importo_pagato=0.0,
        residuo_pagamento=1000.0,
        data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


# ── GET /documenti/ ───────────────────────────────────────────────────────────

def test_archivio_documenti_ok(client_http):
    """GET /documenti/ → 200 (lista vuota)."""
    resp = client_http.get("/documenti/")
    assert resp.status_code == 200


# ── GET /documenti/lavori/{id}/preventivo.pdf ─────────────────────────────────

def test_scarica_preventivo_pdf_ok(client_http, lavoro_test):
    """GET /documenti/lavori/{id}/preventivo.pdf → 200, application/pdf."""
    resp = client_http.get(f"/documenti/lavori/{lavoro_test.id}/preventivo.pdf")
    assert resp.status_code == 200
    assert "pdf" in resp.headers["content-type"]


def test_scarica_preventivo_pdf_lavoro_altrui_404(client_http, db):
    """GET preventivo.pdf su lavoro altrui → 404."""
    altro = _utente(db, "altro1@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.get(f"/documenti/lavori/{lav.id}/preventivo.pdf")
    assert resp.status_code == 404


# ── GET /documenti/lavori/{id}/fattura.pdf ───────────────────────────────────

def test_scarica_fattura_pdf_ok(client_http, db, lavoro_test):
    """GET /documenti/lavori/{id}/fattura.pdf con numero_fattura impostato → 200, pdf."""
    lavoro_test.numero_fattura = 1
    lavoro_test.data_fattura = date.today()
    db.commit()

    resp = client_http.get(f"/documenti/lavori/{lavoro_test.id}/fattura.pdf")
    assert resp.status_code == 200
    assert "pdf" in resp.headers["content-type"]


def test_scarica_fattura_pdf_senza_numero_fattura_404(client_http, lavoro_test):
    """GET fattura.pdf senza numero_fattura → 404."""
    resp = client_http.get(f"/documenti/lavori/{lavoro_test.id}/fattura.pdf")
    assert resp.status_code == 404


def test_scarica_fattura_pdf_lavoro_altrui_404(client_http, db):
    """GET fattura.pdf su lavoro altrui → 404."""
    altro = _utente(db, "altro2@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.get(f"/documenti/lavori/{lav.id}/fattura.pdf")
    assert resp.status_code == 404


# ── GET /documenti/lavori/{id}/fattura-xml ────────────────────────────────────

def test_scarica_fattura_xml_dati_azienda_mancanti_422(client_http, lavoro_test):
    """GET fattura-xml con azienda senza PIVA/indirizzo → 422 con lista errori."""
    resp = client_http.get(f"/documenti/lavori/{lavoro_test.id}/fattura-xml")
    assert resp.status_code == 422


def test_scarica_fattura_xml_lavoro_altrui_404(client_http, db):
    """GET fattura-xml su lavoro altrui → 404."""
    altro = _utente(db, "altro3@t.it")
    lav = _lavoro(db, altro.id)

    resp = client_http.get(f"/documenti/lavori/{lav.id}/fattura-xml")
    assert resp.status_code == 404


# ── GET /documenti/{id}/apri ──────────────────────────────────────────────────

def test_apri_documento_non_trovato_404(client_http):
    """GET /documenti/9999/apri con ID inesistente → 404."""
    resp = client_http.get("/documenti/9999/apri")
    assert resp.status_code == 404


def test_apri_documento_file_su_disco_mancante_404(client_http, db, utente_test, lavoro_test):
    """GET /apri con documento in DB ma file non presente su disco → 404."""
    doc = models.DocumentoPDF(
        utente_id=utente_test.id,
        lavoro_id=lavoro_test.id,
        numero=1,
        nome_file="test_doc.pdf",
        percorso_file="/tmp/percorso-inesistente-9999/test_doc.pdf",
        data_creazione=oggi_str,
    )
    db.add(doc); db.commit(); db.refresh(doc)

    resp = client_http.get(f"/documenti/{doc.id}/apri")
    assert resp.status_code == 404
