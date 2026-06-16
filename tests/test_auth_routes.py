"""
Test HTTP per le route di autenticazione (login, register, verifica email,
password dimenticata, reset password, logout).

Usa un fixture auth_client dedicato (solo get_db override, nessun utente
preesistente) per non interferire con client_http.
"""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.main import app
from app.security import hash_password, verify_password

oggi_str = str(date.today())


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_bcrypt(monkeypatch):
    """Sostituisce bcrypt (rotto su Python 3.14 + bcrypt≥4) con sha256_crypt puro-Python."""
    from passlib.context import CryptContext
    import app.security
    ctx = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    monkeypatch.setattr(app.security, "pwd_context", ctx)


@pytest.fixture
def auth_client(db):
    """TestClient con solo get_db override — nessun utente preesistente in DB."""
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _utente(db, email="user@test.it", password="password123", email_verificato=True,
            token_verifica=None):
    u = models.Utente(
        username=email,
        email=email,
        password=hash_password(password),
        data_registrazione=oggi_str,
        attivo=2 if email_verificato else 0,
        email_verificato=email_verificato,
        token_verifica=token_verifica,
        onboarding_done=True,
        piano="free",
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


# ── GET /login ────────────────────────────────────────────────────────────────

def test_login_page_ok(auth_client):
    """GET /login → 200."""
    resp = auth_client.get("/login")
    assert resp.status_code == 200


# ── POST /login ───────────────────────────────────────────────────────────────

def test_login_credenziali_corrette(auth_client, db):
    """POST /login con credenziali corrette → redirect a /."""
    _utente(db, "login_ok@test.it", "mia_password")

    resp = auth_client.post(
        "/login",
        data={"username": "login_ok@test.it", "password": "mia_password"},
        headers={"X-Forwarded-For": "10.0.0.1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_login_password_errata(auth_client, db):
    """POST /login con password sbagliata → 200 con messaggio errore."""
    _utente(db, "login_fail@test.it", "giusta_password")

    resp = auth_client.post(
        "/login",
        data={"username": "login_fail@test.it", "password": "sbagliata"},
        headers={"X-Forwarded-For": "10.0.0.2"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "Credenziali errate" in resp.text


def test_login_utente_non_trovato(auth_client):
    """POST /login con username inesistente → 200 con errore."""
    resp = auth_client.post(
        "/login",
        data={"username": "nessuno@nessuno.it", "password": "qualcosa"},
        headers={"X-Forwarded-For": "10.0.0.3"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "Credenziali errate" in resp.text


def test_login_email_non_verificata(auth_client, db):
    """POST /login con email non verificata → 200 con errore 'verifica email'."""
    _utente(db, "unverified@test.it", "password123",
            email_verificato=False, token_verifica="some-token")

    resp = auth_client.post(
        "/login",
        data={"username": "unverified@test.it", "password": "password123"},
        headers={"X-Forwarded-For": "10.0.0.4"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "verifica" in resp.text.lower()


# ── GET /register ─────────────────────────────────────────────────────────────

def test_register_page_ok(auth_client):
    """GET /register → 200."""
    resp = auth_client.get("/register")
    assert resp.status_code == 200


# ── POST /register ────────────────────────────────────────────────────────────

def _reg(**overrides):
    base = {
        "email": "nuovo@test.it",
        "username": "nuovoutente",
        "password": "password123",
        "conferma_password": "password123",
        "accetta_termini": "on",
        "codice_promo": "",
    }
    base.update(overrides)
    return base


def test_register_success_no_smtp(auth_client, db, monkeypatch):
    """POST /register senza SMTP → utente creato con email già verificata, redirect /login?verificato=1."""
    monkeypatch.setattr("app.services.email.smtp_configurato", lambda: False)

    resp = auth_client.post(
        "/register",
        data=_reg(email="newuser@test.it", username="newuser"),
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "verificato=1" in resp.headers["location"]

    u = db.query(models.Utente).filter(models.Utente.username == "newuser").first()
    assert u is not None
    assert u.email_verificato is True
    assert u.piano == "free"


def test_register_success_con_smtp(auth_client, db, monkeypatch):
    """POST /register con SMTP → utente non verificato, token_verifica impostato, redirect /register?pendente=1."""
    monkeypatch.setattr("app.services.email.smtp_configurato", lambda: True)
    monkeypatch.setattr("app.services.email.invia_verifica_email", lambda *a: None)

    resp = auth_client.post(
        "/register",
        data=_reg(email="newuser2@test.it", username="newuser2"),
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "pendente=1" in resp.headers["location"]

    u = db.query(models.Utente).filter(models.Utente.username == "newuser2").first()
    assert u is not None
    assert u.email_verificato is False
    assert u.token_verifica is not None


def test_register_senza_accetta_termini(auth_client):
    """POST /register senza spuntare i termini → 200 con errore."""
    resp = auth_client.post("/register", data=_reg(accetta_termini=""), follow_redirects=False)
    assert resp.status_code == 200
    assert "Termini" in resp.text


def test_register_email_invalida(auth_client):
    """POST /register con email senza @ → 200 con errore."""
    resp = auth_client.post("/register", data=_reg(email="nonemail"), follow_redirects=False)
    assert resp.status_code == 200
    assert "email" in resp.text.lower()


def test_register_password_troppo_corta(auth_client):
    """POST /register con password < 8 caratteri → 200 con errore."""
    resp = auth_client.post(
        "/register",
        data=_reg(password="short", conferma_password="short"),
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "8 caratteri" in resp.text


def test_register_password_non_coincidono(auth_client):
    """POST /register con password diverse → 200 con errore."""
    resp = auth_client.post(
        "/register",
        data=_reg(conferma_password="diversa12345"),
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "coincid" in resp.text.lower()


def test_register_email_duplicata(auth_client, db):
    """POST /register con email già in uso → 200 con errore."""
    _utente(db, "esistente@test.it", "password123")

    resp = auth_client.post(
        "/register",
        data=_reg(email="esistente@test.it", username="altrouser"),
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "già registrat" in resp.text.lower()


def test_register_username_caratteri_invalidi(auth_client):
    """POST /register con username contenente spazi → 200 con errore."""
    resp = auth_client.post(
        "/register",
        data=_reg(email="valid@test.it", username="user name"),
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "username" in resp.text.lower()


# ── GET /verifica-email/{token} ───────────────────────────────────────────────

def test_verifica_email_token_valido(auth_client, db):
    """GET /verifica-email/{token} con token valido → redirect /login?verificato=1, utente attivato."""
    u = models.Utente(
        username="unverf@test.it",
        email="unverf@test.it",
        password=hash_password("pass1234"),
        data_registrazione=oggi_str,
        attivo=0,
        email_verificato=False,
        token_verifica="valid-token-abc",
        piano="free",
    )
    db.add(u); db.commit(); db.refresh(u)

    resp = auth_client.get("/verifica-email/valid-token-abc", follow_redirects=False)
    assert resp.status_code == 303
    assert "verificato=1" in resp.headers["location"]

    db.refresh(u)
    assert u.email_verificato is True
    assert u.attivo == 1
    assert u.token_verifica is None


def test_verifica_email_token_invalido(auth_client):
    """GET /verifica-email/{token} con token inesistente → 200 con errore."""
    resp = auth_client.get("/verifica-email/token-non-esiste", follow_redirects=False)
    assert resp.status_code == 200
    assert "non valido" in resp.text.lower()


# ── GET /password-dimenticata ─────────────────────────────────────────────────

def test_forgot_password_page_ok(auth_client):
    """GET /password-dimenticata → 200."""
    resp = auth_client.get("/password-dimenticata")
    assert resp.status_code == 200


def test_forgot_password_sempre_redirect(auth_client):
    """POST /password-dimenticata → redirect con inviato=1 (anti-enumeration)."""
    resp = auth_client.post(
        "/password-dimenticata",
        data={"email": "chiunque@example.com"},
        headers={"X-Forwarded-For": "10.0.1.1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "inviato=1" in resp.headers["location"]


def test_forgot_password_utente_esistente_salva_token(auth_client, db):
    """POST /password-dimenticata con utente esistente → token_reset salvato in DB."""
    u = _utente(db, "reset_me@test.it", "password123")

    auth_client.post(
        "/password-dimenticata",
        data={"email": "reset_me@test.it"},
        headers={"X-Forwarded-For": "10.0.1.2"},
        follow_redirects=False,
    )

    db.refresh(u)
    assert u.token_reset is not None
    assert len(u.token_reset) > 10


# ── GET/POST /reset-password/{token} ─────────────────────────────────────────

def _utente_con_token_reset(db, email="resetok@test.it", token="reset-tok"):
    u = _utente(db, email, "vecchia123")
    u.token_reset = token
    u.token_reset_scadenza = (datetime.now() + timedelta(hours=2)).isoformat()
    db.commit()
    return u


def test_reset_password_page_token_valido(auth_client, db):
    """GET /reset-password/{token} con token non scaduto → 200."""
    _utente_con_token_reset(db, "reset2@test.it", "tok-valido")

    resp = auth_client.get("/reset-password/tok-valido")
    assert resp.status_code == 200


def test_reset_password_page_token_invalido(auth_client):
    """GET /reset-password/{token} con token inesistente → 200 con errore."""
    resp = auth_client.get("/reset-password/token-invalido-xyz")
    assert resp.status_code == 200
    assert "non valido" in resp.text.lower()


def test_reset_password_success(auth_client, db):
    """POST /reset-password/{token} con nuova password valida → redirect, password aggiornata."""
    u = _utente_con_token_reset(db, "reset3@test.it", "tok-ok")

    resp = auth_client.post(
        "/reset-password/tok-ok",
        data={"nuova_password": "nuova12345", "conferma_password": "nuova12345"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "reset=1" in resp.headers["location"]

    db.refresh(u)
    assert u.token_reset is None
    assert verify_password("nuova12345", u.password)


def test_reset_password_mismatch(auth_client, db):
    """POST /reset-password/{token} con password diverse → 200 con errore."""
    _utente_con_token_reset(db, "mismatch@test.it", "tok-mismatch")

    resp = auth_client.post(
        "/reset-password/tok-mismatch",
        data={"nuova_password": "pass1234", "conferma_password": "diversa12345"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "coincid" in resp.text.lower()


def test_reset_password_troppo_corta(auth_client, db):
    """POST /reset-password/{token} con password < 8 caratteri → 200 con errore."""
    _utente_con_token_reset(db, "short@test.it", "tok-short")

    resp = auth_client.post(
        "/reset-password/tok-short",
        data={"nuova_password": "abc", "conferma_password": "abc"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "8 caratteri" in resp.text


# ── GET /logout ───────────────────────────────────────────────────────────────

def test_logout_redirect_a_login(auth_client):
    """GET /logout → redirect a /login."""
    resp = auth_client.get("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


# ── Invalidazione sessione al cambio password (pw_sig) ────────────────────────

class _FakeRequest:
    """Request minimale per testare verifica_account senza HTTP."""
    def __init__(self, session: dict):
        self.session = dict(session)


def test_pw_sig_vecchio_invalida_sessione(db, utente_test):
    """Sessione con pw_sig dell'hash precedente → NotAuthenticated."""
    from app.dependencies import verifica_account, NotAuthenticated
    from app.security import hash_password

    vecchio_sig = utente_test.password[-12:]

    utente_test.password = hash_password("nuova_password_sicura")
    db.commit()
    db.refresh(utente_test)

    req = _FakeRequest({
        "user_id": utente_test.id,
        "last_activity": datetime.now().isoformat(),
        "pw_sig": vecchio_sig,
    })

    with pytest.raises(NotAuthenticated):
        verifica_account(req, db)


def test_pw_sig_assente_viene_popolato(db, utente_test):
    """Sessioni pre-feature senza pw_sig: vengono accettate e pw_sig viene scritto."""
    from app.dependencies import verifica_account

    req = _FakeRequest({
        "user_id": utente_test.id,
        "last_activity": datetime.now().isoformat(),
        # pw_sig assente: sessione vecchia
    })

    uid = verifica_account(req, db)

    assert uid == utente_test.id
    assert req.session.get("pw_sig") == utente_test.password[-12:]


def test_pw_sig_corretto_accetta_sessione(db, utente_test):
    """Sessione con pw_sig aggiornato → accesso consentito."""
    from app.dependencies import verifica_account

    req = _FakeRequest({
        "user_id": utente_test.id,
        "last_activity": datetime.now().isoformat(),
        "pw_sig": utente_test.password[-12:],
    })

    uid = verifica_account(req, db)

    assert uid == utente_test.id
