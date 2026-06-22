"""
Test sul pulsante "Condividi" — landing pubblica (sempre visibile) e
navbar dell'app (solo utenti loggati).

Per la navbar serve una sessione di login reale: la home "/" decide se
mostrare landing.html o la dashboard leggendo request.session.get("user_id")
direttamente, non tramite la dependency get_current_user (che client_http
sovrascrive ma che qui non basterebbe).
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.main import app
from app.security import hash_password

oggi_str = str(date.today())


@pytest.fixture(autouse=True)
def patch_bcrypt(monkeypatch):
    from passlib.context import CryptContext
    import app.security
    ctx = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    monkeypatch.setattr(app.security, "pwd_context", ctx)


@pytest.fixture
def client_sessione(db):
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _utente(db, username="titolare@test.it", password="password123"):
    u = models.Utente(
        username=username, password=hash_password(password),
        data_registrazione=oggi_str, attivo=2, piano="free",
        email_verificato=True, onboarding_done=True, ruolo="titolare",
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _login(client, username, password="password123"):
    resp = client.post(
        "/login", data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 303, f"login fallito: {resp.text[:300]}"
    return resp


def test_landing_mostra_pulsante_condividi(client_sessione):
    """Il pulsante di condivisione è visibile anche senza essere loggati."""
    resp = client_sessione.get("/")
    assert resp.status_code == 200
    assert 'id="link-condividi-landing"' in resp.text
    assert "navigator.share" in resp.text


def test_dashboard_mostra_pulsante_condividi_in_navbar(client_sessione, db):
    """Regressione: il pulsante condividi deve apparire anche per chi è
    già loggato, nella navbar dell'app (non solo sulla landing pubblica)."""
    _utente(db, "fondotest@test.it")
    _login(client_sessione, "fondotest@test.it")

    resp = client_sessione.get("/")
    assert resp.status_code == 200
    assert 'id="btn-condividi-app"' in resp.text
    assert "_condividiApp" in resp.text
