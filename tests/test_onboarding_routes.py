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


def test_onboarding_azienda_vuota_mostra_errore_non_avanza(client_http, db, utente_test):
    """Regressione: POST /azienda con campi vuoti avanzava comunque al passo
    2 senza salvare nulla e senza alcun avviso - sembrava che il salvataggio
    fosse andato a buon fine. Ora resta sul passo 1 con un errore visibile."""
    resp = client_http.post(
        "/onboarding/azienda",
        data={"nome_azienda": "", "partita_iva": "", "telefono": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=campo_vuoto" in resp.headers["location"]

    from app.models import ImpostazioniAzienda
    imp = db.query(ImpostazioniAzienda).filter(
        ImpostazioniAzienda.utente_id == utente_test.id
    ).first()
    assert imp is None

    # Il passo non deve essere avanzato a 2
    pagina = client_http.get("/onboarding?errore=campo_vuoto")
    assert "Passo 1 di 3" in pagina.text
    assert "Inserisci almeno il nome dell'azienda" in pagina.text


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


def test_onboarding_cliente_senza_nome_mostra_errore_non_avanza(client_http, db, utente_test):
    """Regressione: POST /cliente senza nome avanzava comunque al passo 3
    senza creare nulla e senza alcun avviso. Ora resta sul passo 2 con un
    errore visibile."""
    resp = client_http.post(
        "/onboarding/cliente",
        data={"nome": "", "cognome": "", "telefono": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=nome_cliente" in resp.headers["location"]

    count = db.query(models.Cliente).filter(
        models.Cliente.utente_id == utente_test.id
    ).count()
    assert count == 0

    pagina = client_http.get("/onboarding?errore=nome_cliente")
    assert "Passo 1 di 3" in pagina.text  # step non avanzato
    assert "Inserisci il nome del cliente" in pagina.text


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


def test_onboarding_lavoro_senza_titolo_mostra_errore_non_completa(client_http, db, utente_test):
    """Regressione: POST /lavoro senza titolo completava comunque
    l'onboarding (onboarding_done=True) senza creare nulla e senza alcun
    avviso. Ora mostra un errore e NON marca l'onboarding come completato."""
    utente_test.onboarding_done = False
    db.commit()
    client_http.post(
        "/onboarding/cliente",
        data={"nome": "Luigi", "cognome": "Bianchi", "telefono": ""},
        follow_redirects=False,
    )

    resp = client_http.post(
        "/onboarding/lavoro",
        data={"titolo": "", "descrizione": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=titolo_lavoro" in resp.headers["location"]

    count = db.query(models.Lavoro).filter(
        models.Lavoro.utente_id == utente_test.id
    ).count()
    assert count == 0

    db.refresh(utente_test)
    assert utente_test.onboarding_done is False


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
