"""
Test HTTP per le route /onboarding/*.

Copre: visualizzazione wizard (GET /onboarding), salvataggio dati azienda
(POST /azienda → crea ImpostazioniAzienda o salta se vuoto), creazione cliente
(POST /cliente → crea Cliente o salta se nome vuoto), creazione lavoro (POST /lavoro
usa onboarding_cliente_id dalla sessione), salta wizard (GET /salta).
"""
from datetime import date

import pytest

from app import models

oggi_str = str(date.today())


# ── GET /onboarding ────────────────────────────────────────────────────────────

def test_onboarding_page_ok(client_http):
    """GET /onboarding → 200."""
    resp = client_http.get("/onboarding")
    assert resp.status_code == 200


# ── POST /onboarding/azienda ───────────────────────────────────────────────────

def test_onboarding_azienda_salva_impostazioni(client_http, db, utente_test):
    """POST /azienda con nome_azienda → redirect /onboarding, impostazioni salvate in DB."""
    resp = client_http.post(
        "/onboarding/azienda",
        data={"nome_azienda": "Idraulica Rossi", "partita_iva": "12345678901", "telefono": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/onboarding"

    from app.models import ImpostazioniAzienda
    imp = db.query(ImpostazioniAzienda).filter(
        ImpostazioniAzienda.utente_id == utente_test.id
    ).first()
    assert imp is not None
    assert imp.nome_azienda == "Idraulica Rossi"
    assert imp.partita_iva == "12345678901"


def test_onboarding_azienda_vuota_non_salva(client_http, db, utente_test):
    """POST /azienda con campi vuoti → redirect /onboarding, nessuna impostazione creata."""
    resp = client_http.post(
        "/onboarding/azienda",
        data={"nome_azienda": "", "partita_iva": "", "telefono": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    from app.models import ImpostazioniAzienda
    imp = db.query(ImpostazioniAzienda).filter(
        ImpostazioniAzienda.utente_id == utente_test.id
    ).first()
    assert imp is None


# ── POST /onboarding/cliente ───────────────────────────────────────────────────

def test_onboarding_cliente_crea_cliente(client_http, db, utente_test):
    """POST /cliente con nome → redirect /onboarding, cliente creato in DB."""
    resp = client_http.post(
        "/onboarding/cliente",
        data={"nome": "Giovanni", "cognome": "Verdi", "telefono": "3331234567"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/onboarding"

    clienti = db.query(models.Cliente).filter(
        models.Cliente.utente_id == utente_test.id
    ).all()
    assert len(clienti) == 1
    assert clienti[0].nome == "Giovanni"


def test_onboarding_cliente_senza_nome_non_crea(client_http, db, utente_test):
    """POST /cliente senza nome → redirect /onboarding, nessun cliente creato."""
    resp = client_http.post(
        "/onboarding/cliente",
        data={"nome": "", "cognome": "", "telefono": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    count = db.query(models.Cliente).filter(
        models.Cliente.utente_id == utente_test.id
    ).count()
    assert count == 0


# ── POST /onboarding/lavoro ────────────────────────────────────────────────────

def test_onboarding_lavoro_con_sessione_crea_lavoro(client_http, db, utente_test):
    """Catena POST /cliente → POST /lavoro: cliente_id va in sessione, lavoro creato."""
    # Step 1: crea cliente e metti cliente_id in sessione
    client_http.post(
        "/onboarding/cliente",
        data={"nome": "Luigi", "cognome": "Bianchi", "telefono": ""},
        follow_redirects=False,
    )

    # Step 2: crea lavoro usando cliente_id dalla sessione
    resp = client_http.post(
        "/onboarding/lavoro",
        data={"titolo": "Impianto elettrico", "descrizione": "Ristrutturazione"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"

    lavori = db.query(models.Lavoro).filter(
        models.Lavoro.utente_id == utente_test.id
    ).all()
    assert len(lavori) == 1
    assert lavori[0].titolo == "Impianto elettrico"

    db.refresh(utente_test)
    assert utente_test.onboarding_done is True


def test_onboarding_lavoro_senza_sessione_non_crea(client_http, db, utente_test):
    """POST /lavoro senza onboarding_cliente_id in sessione → redirect /, nessun lavoro."""
    resp = client_http.post(
        "/onboarding/lavoro",
        data={"titolo": "Lavoro qualsiasi", "descrizione": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"

    count = db.query(models.Lavoro).filter(
        models.Lavoro.utente_id == utente_test.id
    ).count()
    assert count == 0

    db.refresh(utente_test)
    assert utente_test.onboarding_done is True


# ── GET /onboarding/salta ─────────────────────────────────────────────────────

def test_onboarding_salta_marca_done_e_redirect(client_http, db, utente_test):
    """GET /onboarding/salta → redirect /, onboarding_done=True."""
    utente_test.onboarding_done = False
    db.commit()

    resp = client_http.get("/onboarding/salta", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"

    db.refresh(utente_test)
    assert utente_test.onboarding_done is True
