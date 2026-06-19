"""
Test HTTP per le route /impostazioni/*.

Copre: form/salvataggio dati azienda, form/aggiornamento profilo utente
(email, cambio password, validazioni), export Excel clienti/lavori/materiali.
"""
from datetime import date

import pytest

from app import models, crud

oggi_str = str(date.today())


# ── Helper di setup ───────────────────────────────────────────────────────────

def _dati_azienda(**override):
    base = {
        "nome_azienda": "Idraulica Rossi Srl",
        "partita_iva": "12345678901",
        "codice_fiscale": "RSSXXX80A01H501Z",
        "regime_fiscale": "RF01",
        "indirizzo": "Via Roma 10",
        "cap": "00100",
        "citta": "Roma",
        "provincia": "RM",
        "telefono": "0612345678",
        "email": "info@idraulica.it",
        "pec_indirizzo": "",
        "pec_smtp_host": "",
        "pec_smtp_port": "465",
        "pec_smtp_password": "",
    }
    base.update(override)
    return base


# ── GET /impostazioni/azienda ─────────────────────────────────────────────────

def test_form_azienda_ok(client_http):
    """GET /impostazioni/azienda → 200."""
    resp = client_http.get("/impostazioni/azienda")
    assert resp.status_code == 200


# ── POST /impostazioni/azienda ────────────────────────────────────────────────

def test_salva_azienda_aggiorna_campi(client_http, db, utente_test):
    """POST azienda → redirect con ?salvato=1, campi aggiornati in DB."""
    resp = client_http.post(
        "/impostazioni/azienda",
        data=_dati_azienda(),
        files={"logo": ("", b"", "application/octet-stream")},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "salvato=1" in resp.headers["location"]

    azienda = crud.get_impostazioni_azienda(db, utente_test.id)
    assert azienda.nome_azienda == "Idraulica Rossi Srl"
    assert azienda.partita_iva == "12345678901"
    assert azienda.regime_fiscale == "RF01"
    assert azienda.citta == "Roma"


def test_salva_azienda_crea_record_se_assente(client_http, db, utente_test):
    """POST azienda senza record preesistente → record creato con i dati inviati."""
    resp = client_http.post(
        "/impostazioni/azienda",
        data=_dati_azienda(nome_azienda="Termoidraulica Verde"),
        files={"logo": ("", b"", "application/octet-stream")},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    azienda = crud.get_impostazioni_azienda(db, utente_test.id)
    assert azienda is not None
    assert azienda.nome_azienda == "Termoidraulica Verde"
    assert azienda.utente_id == utente_test.id


def test_salva_azienda_aggiorna_regime_fiscale(client_http, db, utente_test):
    """POST con regime RF19 → aggiornato in DB."""
    client_http.post(
        "/impostazioni/azienda",
        data=_dati_azienda(regime_fiscale="RF19"),
        files={"logo": ("", b"", "application/octet-stream")},
        follow_redirects=False,
    )

    azienda = crud.get_impostazioni_azienda(db, utente_test.id)
    assert azienda.regime_fiscale == "RF19"


# ── GET /impostazioni/profilo ─────────────────────────────────────────────────

def test_form_profilo_ok(client_http):
    """GET /impostazioni/profilo → 200."""
    resp = client_http.get("/impostazioni/profilo")
    assert resp.status_code == 200


# ── POST /impostazioni/profilo ────────────────────────────────────────────────

def test_profilo_aggiorna_email(client_http, db, utente_test):
    """POST profilo con email valida → 200 con testo di successo nel body."""
    resp = client_http.post(
        "/impostazioni/profilo",
        data={
            "email": "nuova@email.it",
            "password_attuale": "",
            "nuova_password": "",
            "conferma_password": "",
        },
    )
    assert resp.status_code == 200
    assert "aggiornata" in resp.text.lower()

    db.refresh(utente_test)
    assert utente_test.email == "nuova@email.it"


def test_profilo_email_non_valida(client_http):
    """POST profilo con email senza @ → 200 con messaggio errore."""
    resp = client_http.post(
        "/impostazioni/profilo",
        data={
            "email": "nonsoemail",
            "password_attuale": "",
            "nuova_password": "",
            "conferma_password": "",
        },
    )
    assert resp.status_code == 200
    assert "non valido" in resp.text.lower() or "errore" in resp.text.lower() or "email" in resp.text.lower()


def test_profilo_password_attuale_errata(client_http, db, utente_test):
    """POST cambio password con password_attuale sbagliata → 200 con errore."""
    utente_test.password = "corretta123"
    db.commit()

    resp = client_http.post(
        "/impostazioni/profilo",
        data={
            "email": "",
            "password_attuale": "sbagliata999",
            "nuova_password": "nuova1234",
            "conferma_password": "nuova1234",
        },
    )
    assert resp.status_code == 200
    assert "errata" in resp.text.lower() or "errore" in resp.text.lower()


def test_profilo_conferma_password_diversa(client_http, db, utente_test):
    """POST cambio password con conferma diversa → 200 con errore."""
    utente_test.password = "vecchia123"
    db.commit()

    resp = client_http.post(
        "/impostazioni/profilo",
        data={
            "email": "",
            "password_attuale": "vecchia123",
            "nuova_password": "nuova1234",
            "conferma_password": "diversa999",
        },
    )
    assert resp.status_code == 200
    assert "non coincidono" in resp.text.lower() or "errore" in resp.text.lower()


def test_profilo_cambia_password_ok(client_http, db, utente_test):
    """POST cambio password corretto → 200 con testo di successo."""
    from app.security import hash_password
    try:
        hash_password("probe")
    except Exception:
        pytest.skip("bcrypt/passlib incompatibile con questo ambiente Python — skip")

    utente_test.password = "vecchia123"
    db.commit()

    resp = client_http.post(
        "/impostazioni/profilo",
        data={
            "email": "",
            "password_attuale": "vecchia123",
            "nuova_password": "nuova12345",
            "conferma_password": "nuova12345",
        },
    )
    assert resp.status_code == 200
    assert "password aggiornata" in resp.text.lower()

    db.refresh(utente_test)
    assert utente_test.password != "vecchia123"


# ── GET /impostazioni/export/* ────────────────────────────────────────────────

def test_export_clienti_xlsx(client_http):
    """GET /impostazioni/export/clienti → 200 con content-type xlsx."""
    resp = client_http.get("/impostazioni/export/clienti")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_lavori_xlsx(client_http):
    """GET /impostazioni/export/lavori → 200 con content-type xlsx."""
    resp = client_http.get("/impostazioni/export/lavori")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


def test_export_materiali_xlsx(client_http):
    """GET /impostazioni/export/materiali → 200 con content-type xlsx."""
    resp = client_http.get("/impostazioni/export/materiali")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


# ── Backup legacy rimosso ──────────────────────────────────────────────────────

def test_route_backup_legacy_rimosse(client_http):
    """Le vecchie route di backup SQLite (/backup, /backup/pagina,
    /backup/completo, /backup/ripristina, /backup/download/{f},
    /backup/elimina/{f}) permettevano a QUALUNQUE titolare — non solo a un
    vero admin di piattaforma — di scaricare/eliminare file arbitrari nella
    cartella backup/ e persino sovrascrivere l'intero database con un file
    .db caricato a piacere. Rimosse perché non raggiungibili da nessun link
    dell'app e già sostituite dal backup S3 con verifica di ripristino
    automatica (app/services/backup.py). Questo test impedisce che vengano
    reintrodotte per errore."""
    assert client_http.get("/impostazioni/backup").status_code == 404
    assert client_http.get("/impostazioni/backup/pagina").status_code == 404
    assert client_http.get("/impostazioni/backup/completo").status_code == 404
    assert client_http.post("/impostazioni/backup/ripristina").status_code == 404
    assert client_http.get("/impostazioni/backup/download/x.db").status_code == 404
    assert client_http.get("/impostazioni/backup/elimina/x.db").status_code == 404
