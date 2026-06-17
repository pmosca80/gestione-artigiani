"""
Test HTTP per le route /fatture/*.

Copre: emissione fattura (crea-da-lavoro), aggiornamento stato/pagamento,
nota di credito, download XML e isolamento multi-tenant.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import models, crud
from app.database import get_db
from app.dependencies import get_current_user
from app.main import app

oggi = date.today()


# ── Helper di setup ───────────────────────────────────────────────────────────

def _crea_azienda(db, utente_id, partita_iva="12345678901"):
    az = models.ImpostazioniAzienda(
        utente_id=utente_id,
        nome_azienda="Test Srl",
        partita_iva=partita_iva,
        indirizzo="Via Roma 1",
        cap="00100",
        citta="Roma",
        provincia="RM",
        regime_fiscale="RF01",
        email="azienda@test.it",
        ultimo_numero_fattura=0,
    )
    db.add(az)
    db.commit()
    db.refresh(az)
    return az


def _crea_cliente_cf(db, utente_id):
    c = models.Cliente(
        utente_id=utente_id,
        tipo_cliente="privato",
        nome="Mario", cognome="Rossi",
        codice_fiscale="RSSMRA80A01H501U",
        indirizzo="Via Verdi 5",
        cap="00200", citta="Milano",
        data_creazione=str(oggi),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _crea_lavoro(db, utente_id, cliente_id):
    l = models.Lavoro(
        utente_id=utente_id, cliente_id=cliente_id,
        titolo="Impianto gas",
        data_lavoro=oggi,
        stato="completato", priorita="normale",
        importo_consuntivo=500.0,
        totale_iva=110.0,
        totale_documento=610.0,
        aliquota_iva=22.0,
        sconto=0.0,
        importo_pagato=0.0,
        data_scadenza_pagamento=oggi,
        data_creazione=str(oggi),
    )
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


def _crea_fattura(db, utente_id, lavoro_id, numero=1):
    f = models.FatturaEmessa(
        utente_id=utente_id, lavoro_id=lavoro_id,
        numero=numero, anno=oggi.year,
        data_emissione=str(oggi),
        importo_imponibile=500.0,
        importo_iva=110.0,
        importo_totale=610.0,
        stato="emessa",
        tipo_documento="TD01",
        nome_file="IT12345678901_00001.xml",
        data_creazione=str(oggi),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ── GET /fatture/ ─────────────────────────────────────────────────────────────

def test_registro_fatture_ok(client_http, db, utente_test):
    _crea_azienda(db, utente_test.id)
    resp = client_http.get("/fatture/")
    assert resp.status_code == 200


# ── POST /fatture/crea-da-lavoro/{lavoro_id} ──────────────────────────────────

def test_crea_da_lavoro_happy_path(client_http, db, utente_test):
    """Happy path: FatturaEmessa creata in DB, redirect con creata=1."""
    _crea_azienda(db, utente_test.id)
    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)

    resp = client_http.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)

    assert resp.status_code == 303
    assert "creata=1" in resp.headers["location"]

    fatture = crud.get_fatture_registro(db, utente_test.id)
    assert len(fatture) == 1
    assert fatture[0].lavoro_id == lav.id


def test_crea_da_lavoro_assegna_numero_e_stato(client_http, db, utente_test):
    """Numero fattura auto-assegnato e stato_fattura aggiornato sul lavoro."""
    _crea_azienda(db, utente_test.id)
    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)

    client_http.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)

    db.refresh(lav)
    assert lav.numero_fattura == 1
    assert lav.stato_fattura == "emessa"


def test_crea_da_lavoro_idempotente(client_http, db, utente_test):
    """Seconda emissione sullo stesso lavoro aggiorna la fattura esistente, non la duplica."""
    _crea_azienda(db, utente_test.id)
    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)

    client_http.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)
    client_http.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)

    fatture = crud.get_fatture_registro(db, utente_test.id)
    assert len(fatture) == 1


def test_crea_da_lavoro_invia_automaticamente_se_abilitato(client_http, db, utente_test):
    """Con invio_automatico_sdi=True e PEC configurata, l'invio a SDI parte da solo."""
    from unittest.mock import patch

    az = _crea_azienda(db, utente_test.id)
    az.pec_indirizzo = "azienda@pec.it"
    az.pec_smtp_host = "smtp.pec.it"
    az.pec_smtp_password = "segreta"
    az.invio_automatico_sdi = True
    db.commit()

    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)

    with patch("app.services.sdi.invia_xml_a_sdi") as mock_invia, \
         patch("app.services.fatturapa.genera_xml_fatturapa", return_value=b"<xml/>"):
        resp = client_http.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)

    assert resp.status_code == 303
    mock_invia.assert_called_once()
    fatture = crud.get_fatture_registro(db, utente_test.id)
    assert fatture[0].stato == "inviata_sdi"


def test_crea_da_lavoro_non_invia_se_disabilitato(client_http, db, utente_test):
    """Senza invio_automatico_sdi, la fattura resta in stato 'emessa' e nessun invio parte."""
    from unittest.mock import patch

    az = _crea_azienda(db, utente_test.id)
    az.pec_indirizzo = "azienda@pec.it"
    az.pec_smtp_host = "smtp.pec.it"
    az.pec_smtp_password = "segreta"
    db.commit()

    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)

    with patch("app.services.sdi.invia_xml_a_sdi") as mock_invia:
        client_http.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)

    mock_invia.assert_not_called()
    fatture = crud.get_fatture_registro(db, utente_test.id)
    assert fatture[0].stato != "inviata_sdi"


def test_crea_da_lavoro_lavoro_inesistente(client_http, db, utente_test):
    _crea_azienda(db, utente_test.id)
    resp = client_http.post("/fatture/crea-da-lavoro/999999", follow_redirects=False)
    assert resp.status_code == 404


def test_crea_da_lavoro_dati_mancanti_422(client_http, db, utente_test):
    """Azienda senza P.IVA → 422 HTML con errori leggibili."""
    az = models.ImpostazioniAzienda(
        utente_id=utente_test.id,
        nome_azienda="Test", partita_iva="",  # mancante
        indirizzo="Via Roma 1", cap="00100", citta="Roma",
        regime_fiscale="RF01", ultimo_numero_fattura=0,
    )
    db.add(az); db.commit()

    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)

    resp = client_http.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)

    assert resp.status_code == 422
    assert "Partita IVA" in resp.text


def test_crea_da_lavoro_piano_free_redirect(db, utente_test):
    """Piano free → redirect a /piani?upgrade=fatturapa senza creare nulla."""
    u_free = models.Utente(
        username="free@t.it", password="x", piano="free",
        attivo=2, onboarding_done=True, data_registrazione=str(oggi),
    )
    db.add(u_free); db.commit(); db.refresh(u_free)

    _crea_azienda(db, u_free.id)
    cli = _crea_cliente_cf(db, u_free.id)
    lav = _crea_lavoro(db, u_free.id, cli.id)

    def _db(): yield db
    def _user(): return u_free.id
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user

    with TestClient(app, raise_server_exceptions=True) as c:
        resp = c.post(f"/fatture/crea-da-lavoro/{lav.id}", follow_redirects=False)

    app.dependency_overrides.clear()

    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert "/piani" in loc and "upgrade=fatturapa" in loc

    assert crud.get_fatture_registro(db, u_free.id) == []


# ── POST /fatture/{fattura_id}/pagamento ──────────────────────────────────────

def test_aggiorna_pagamento_segna_pagato(client_http, db, utente_test):
    """POST pagamento=pagato → stato_pagamento del Lavoro aggiornato."""
    _crea_azienda(db, utente_test.id)
    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)
    fat = _crea_fattura(db, utente_test.id, lav.id)

    resp = client_http.post(
        f"/fatture/{fat.id}/pagamento",
        data={"stato": "pagato"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(lav)
    assert lav.stato_pagamento == "pagato"


# ── POST /fatture/{fattura_id}/stato ─────────────────────────────────────────

def test_aggiorna_stato_fattura(client_http, db, utente_test):
    """POST stato=inviata_sdi → FatturaEmessa.stato aggiornato."""
    _crea_azienda(db, utente_test.id)
    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)
    fat = _crea_fattura(db, utente_test.id, lav.id)

    resp = client_http.post(
        f"/fatture/{fat.id}/stato",
        data={"stato": "inviata_sdi"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(fat)
    assert fat.stato == "inviata_sdi"


# ── POST /fatture/{fattura_id}/nota-credito ───────────────────────────────────

def test_crea_nota_credito_td04(client_http, db, utente_test):
    """Nota di credito TD04 creata con riferimento alla fattura originale."""
    _crea_azienda(db, utente_test.id)
    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)
    fat = _crea_fattura(db, utente_test.id, lav.id)

    resp = client_http.post(f"/fatture/{fat.id}/nota-credito", follow_redirects=False)
    assert resp.status_code == 303

    tutte = crud.get_fatture_registro(db, utente_test.id)
    nc = next((f for f in tutte if f.tipo_documento == "TD04"), None)
    assert nc is not None
    assert nc.fattura_rif_numero == fat.numero
    assert nc.fattura_rif_anno == fat.anno


def test_crea_nota_credito_invia_automaticamente_se_abilitato(client_http, db, utente_test):
    """La nota di credito TD04 viene inviata a SDI in automatico come la fattura originale."""
    from unittest.mock import patch

    az = _crea_azienda(db, utente_test.id)
    az.pec_indirizzo = "azienda@pec.it"
    az.pec_smtp_host = "smtp.pec.it"
    az.pec_smtp_password = "segreta"
    az.invio_automatico_sdi = True
    db.commit()

    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)
    fat = _crea_fattura(db, utente_test.id, lav.id)

    with patch("app.services.sdi.invia_xml_a_sdi") as mock_invia, \
         patch("app.services.fatturapa.genera_xml_fatturapa", return_value=b"<xml/>") as mock_genera:
        resp = client_http.post(f"/fatture/{fat.id}/nota-credito", follow_redirects=False)

    assert resp.status_code == 303
    mock_invia.assert_called_once()
    assert mock_genera.call_args.kwargs["tipo_documento"] == "TD04"


def test_crea_nota_credito_fattura_non_trovata(client_http, db, utente_test):
    """Fattura inesistente → redirect con errore, nessuna nota creata."""
    _crea_azienda(db, utente_test.id)

    resp = client_http.post("/fatture/999999/nota-credito", follow_redirects=False)

    assert resp.status_code == 303
    assert "errore=fattura_non_trovata" in resp.headers["location"]


# ── GET /fatture/{fattura_id}/scarica-xml ────────────────────────────────────

def test_scarica_xml_ritorna_xml(client_http, db, utente_test):
    """Fattura esistente → 200 con content-type XML e intestazione FPR12."""
    _crea_azienda(db, utente_test.id)
    cli = _crea_cliente_cf(db, utente_test.id)
    lav = _crea_lavoro(db, utente_test.id, cli.id)
    lav.numero_fattura = 1
    lav.data_fattura = oggi
    db.commit(); db.refresh(lav)

    fat = _crea_fattura(db, utente_test.id, lav.id)

    resp = client_http.get(f"/fatture/{fat.id}/scarica-xml")

    assert resp.status_code == 200
    assert "xml" in resp.headers["content-type"]
    assert b"FPR12" in resp.content


def test_scarica_xml_piano_free_redirect(db, utente_test):
    """Piano free → redirect a /piani anche per il download XML."""
    u_free = models.Utente(
        username="free2@t.it", password="x", piano="free",
        attivo=2, onboarding_done=True, data_registrazione=str(oggi),
    )
    db.add(u_free); db.commit(); db.refresh(u_free)

    def _db(): yield db
    def _user(): return u_free.id
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user

    with TestClient(app, raise_server_exceptions=True) as c:
        resp = c.get("/fatture/1/scarica-xml", follow_redirects=False)

    app.dependency_overrides.clear()

    assert resp.status_code == 303
    assert "/piani" in resp.headers["location"]


# ── Isolamento multi-tenant ───────────────────────────────────────────────────

def test_pagamento_fattura_altro_utente_ignorato(client_http, db, utente_test):
    """utente_test non può aggiornare il pagamento di fatture altrui."""
    altro = models.Utente(
        username="altro@t.it", password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=str(oggi),
    )
    db.add(altro); db.commit(); db.refresh(altro)

    _crea_azienda(db, altro.id)
    cli = _crea_cliente_cf(db, altro.id)
    lav = _crea_lavoro(db, altro.id, cli.id)
    fat = _crea_fattura(db, altro.id, lav.id)

    resp = client_http.post(
        f"/fatture/{fat.id}/pagamento",
        data={"stato": "pagato"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(lav)
    assert lav.stato_pagamento != "pagato"
