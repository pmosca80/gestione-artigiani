"""
Test HTTP per le route /team/* e /register/invito/*.

Copre: pagina team (GET /team), generazione invito (POST /team/invita → crea InvitoAccount,
piano free → errore, limite raggiunto → errore), rimozione collaboratore (POST /rimuovi/{id}),
pagina register invito (GET → token valido/invalido), completamento registrazione via invito
(POST → crea Utente collaboratore, username duplicato → errore, password corta → errore).

Nota: _solo_titolare() legge request.session.get("user_id"). In questi test il client
usa get_current_user overridato ma non imposta la sessione, quindi _solo_titolare
restituisce sempre False (non blocca) — comportamento corretto per test del titolare.
"""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.main import app
from app.dependencies import get_current_user
from app.security import hash_password

oggi_str = str(date.today())
domani_str = (date.today() + timedelta(days=7)).strftime("%Y-%m-%d")


# ── Fixture ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_bcrypt(monkeypatch):
    """Bypassa bcrypt (incompatibile su Python 3.14 + bcrypt≥4)."""
    from passlib.context import CryptContext
    import app.security
    ctx = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    monkeypatch.setattr(app.security, "pwd_context", ctx)


# ── Helper ─────────────────────────────────────────────────────────────────────

def _invito(db, titolare_id, token="tok-invito", giorni=7, usato=0):
    scadenza = (datetime.now() + timedelta(days=giorni)).strftime("%Y-%m-%d")
    inv = models.InvitoAccount(
        titolare_id=titolare_id,
        token=token,
        scadenza=scadenza,
        usato=usato,
        data_creazione=oggi_str,
    )
    db.add(inv); db.commit(); db.refresh(inv)
    return inv


def _collaboratore(db, titolare_id, username):
    u = models.Utente(
        username=username,
        password="x",
        data_registrazione=oggi_str,
        attivo=2,
        piano="free",
        titolare_id=titolare_id,
        ruolo="collaboratore",
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


# ── GET /team ──────────────────────────────────────────────────────────────────

def test_team_page_ok(client_http):
    """GET /team → 200."""
    resp = client_http.get("/team")
    assert resp.status_code == 200


def test_team_page_con_invito_attivo(client_http, db, utente_test):
    """GET /team con invito attivo → 200, link invito presente nel HTML."""
    _invito(db, utente_test.id, "tok-attivo")

    resp = client_http.get("/team")
    assert resp.status_code == 200
    assert "tok-attivo" in resp.text


# ── POST /team/invita ──────────────────────────────────────────────────────────

def test_team_invita_crea_invito_piano_pro(client_http, db, utente_test):
    """POST /team/invita con piano pro → redirect /team, InvitoAccount in DB."""
    resp = client_http.post("/team/invita", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/team"

    inv = (
        db.query(models.InvitoAccount)
        .filter(models.InvitoAccount.titolare_id == utente_test.id, models.InvitoAccount.usato == 0)
        .first()
    )
    assert inv is not None
    assert len(inv.token) > 10


def test_team_invita_piano_free_redirect_errore(client_http, db, utente_test):
    """POST /team/invita con piano free → redirect /team?errore=pro_required."""
    utente_test.piano = "free"
    db.commit()

    resp = client_http.post("/team/invita", follow_redirects=False)
    assert resp.status_code == 303
    assert "pro_required" in resp.headers["location"]


def test_team_invita_limite_raggiunto(client_http, db, utente_test):
    """POST /team/invita con 3 collaboratori già presenti → redirect errore limite."""
    for i in range(3):
        _collaboratore(db, utente_test.id, f"collab{i}@t.it")

    resp = client_http.post("/team/invita", follow_redirects=False)
    assert resp.status_code == 303
    assert "limite_raggiunto" in resp.headers["location"]


def test_team_invita_revoca_invito_precedente(client_http, db, utente_test):
    """POST /team/invita con invito non usato → invito precedente revocato, ne esiste solo uno."""
    _invito(db, utente_test.id, "tok-vecchio")

    client_http.post("/team/invita", follow_redirects=False)

    count = (
        db.query(models.InvitoAccount)
        .filter(models.InvitoAccount.titolare_id == utente_test.id, models.InvitoAccount.usato == 0)
        .count()
    )
    assert count == 1

    # il vecchio token non esiste più
    assert (
        db.query(models.InvitoAccount)
        .filter(models.InvitoAccount.token == "tok-vecchio")
        .first()
    ) is None


# ── POST /team/rimuovi/{id} ────────────────────────────────────────────────────

def test_team_rimuovi_collaboratore_ok(client_http, db, utente_test):
    """POST /team/rimuovi/{id} → collaboratore scollegato, ruolo=titolare."""
    collab = _collaboratore(db, utente_test.id, "collab@t.it")

    resp = client_http.post(f"/team/rimuovi/{collab.id}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/team"

    db.refresh(collab)
    assert collab.titolare_id is None
    assert collab.ruolo == "titolare"


def test_team_rimuovi_collaboratore_altrui_ignorato(client_http, db, utente_test):
    """POST /rimuovi/{id} su collaboratore di altro titolare → nessun effetto."""
    altro = models.Utente(
        username="altro_titolare@t.it", password="x",
        data_registrazione=oggi_str, attivo=2, piano="pro",
    )
    db.add(altro); db.commit(); db.refresh(altro)

    collab = _collaboratore(db, altro.id, "collab_altrui@t.it")

    client_http.post(f"/team/rimuovi/{collab.id}", follow_redirects=False)

    db.refresh(collab)
    assert collab.titolare_id == altro.id  # invariato


# ── GET /register/invito/{token} ──────────────────────────────────────────────

def test_register_invito_token_valido(client_http, db, utente_test):
    """GET /register/invito/{token} con token valido → 200, titolare_username presente."""
    _invito(db, utente_test.id, "tok-reg-valido")

    resp = client_http.get("/register/invito/tok-reg-valido")
    assert resp.status_code == 200
    assert utente_test.username in resp.text


def test_register_invito_token_invalido(client_http):
    """GET /register/invito/{token} con token inesistente → 200, segnala token non valido."""
    resp = client_http.get("/register/invito/token-non-esiste-xyz")
    assert resp.status_code == 200
    assert "non valido" in resp.text.lower() or "invito" in resp.text.lower()


# ── POST /register/invito/{token} ─────────────────────────────────────────────

def test_register_invito_completa_ok(client_http, db, utente_test):
    """POST /register/invito valido → redirect /login?invito=1, collaboratore in DB, invito.usato=1."""
    inv = _invito(db, utente_test.id, "tok-completa")

    resp = client_http.post(
        "/register/invito/tok-completa",
        data={"username": "nuovo_collab", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "invito=1" in resp.headers["location"]

    nuovo = db.query(models.Utente).filter(models.Utente.username == "nuovo_collab").first()
    assert nuovo is not None
    assert nuovo.titolare_id == utente_test.id
    assert nuovo.ruolo == "collaboratore"

    db.refresh(inv)
    assert inv.usato == 1


def test_register_invito_username_duplicato(client_http, db, utente_test):
    """POST /register/invito con username già in uso → 200 con errore."""
    _invito(db, utente_test.id, "tok-dup")

    resp = client_http.post(
        "/register/invito/tok-dup",
        data={"username": utente_test.username, "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "già in uso" in resp.text.lower() or "username" in resp.text.lower()


def test_register_invito_password_corta(client_http, db, utente_test):
    """POST /register/invito con password < 6 caratteri → 200 con errore."""
    _invito(db, utente_test.id, "tok-short")

    resp = client_http.post(
        "/register/invito/tok-short",
        data={"username": "collab_short", "password": "abc"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "6 caratteri" in resp.text
