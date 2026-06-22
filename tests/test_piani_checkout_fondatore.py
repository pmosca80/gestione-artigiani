"""
Test sull'applicazione automatica del coupon "piano fondatore" al checkout
Stripe.

Usa sessioni reali (login HTTP) perché /piani/checkout legge
request.session.get("user_id") direttamente, non la dependency
get_current_user (che in client_http è overridata e non rifletterebbe
quindi lo stato reale della sessione).
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
    """Bypassa bcrypt (incompatibile su Python 3.14 + bcrypt>=4)."""
    from passlib.context import CryptContext
    import app.security
    ctx = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    monkeypatch.setattr(app.security, "pwd_context", ctx)


@pytest.fixture
def client_sessione(db):
    """TestClient con sessioni reali (nessun override di get_current_user)."""
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _utente(db, username="titolare@test.it", password="password123", piano_fondatore=False):
    u = models.Utente(
        username=username, password=hash_password(password),
        data_registrazione=oggi_str, attivo=2, piano="free",
        email_verificato=True, onboarding_done=True, ruolo="titolare",
        piano_fondatore=piano_fondatore,
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


class _FakeSession:
    """Stand-in minimale per l'oggetto restituito da stripe.checkout.Session.create."""
    url = "https://checkout.stripe.com/fake-session"


def test_checkout_fondatore_applica_coupon(client_sessione, db, monkeypatch):
    """Utente con piano_fondatore=True e coupon configurato → la Checkout
    Session Stripe deve includere il discount automaticamente."""
    _utente(db, "fondatore@test.it", piano_fondatore=True)
    _login(client_sessione, "fondatore@test.it")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_fake")
    monkeypatch.setenv("STRIPE_COUPON_FONDATORE", "FONDATORE50")

    catturato = {}

    def _fake_create(**kwargs):
        catturato.update(kwargs)
        return _FakeSession()

    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_fake_create))

    resp = client_sessione.post("/piani/checkout", data={"piano": "pro"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == _FakeSession.url

    assert catturato.get("discounts") == [{"coupon": "FONDATORE50"}]


def test_checkout_non_fondatore_nessun_coupon(client_sessione, db, monkeypatch):
    """Regressione: un utente normale (piano_fondatore=False) non deve
    ricevere lo sconto, anche se il coupon è configurato a livello globale."""
    _utente(db, "normale@test.it", piano_fondatore=False)
    _login(client_sessione, "normale@test.it")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_fake")
    monkeypatch.setenv("STRIPE_COUPON_FONDATORE", "FONDATORE50")

    catturato = {}

    def _fake_create(**kwargs):
        catturato.update(kwargs)
        return _FakeSession()

    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_fake_create))

    resp = client_sessione.post("/piani/checkout", data={"piano": "pro"}, follow_redirects=False)
    assert resp.status_code == 303

    assert "discounts" not in catturato


def test_checkout_fondatore_senza_coupon_configurato(client_sessione, db, monkeypatch):
    """Se il coupon non è ancora stato creato/configurato (env var assente),
    il checkout deve funzionare comunque, senza sconto."""
    _utente(db, "fondatore2@test.it", piano_fondatore=True)
    _login(client_sessione, "fondatore2@test.it")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_fake")
    monkeypatch.delenv("STRIPE_COUPON_FONDATORE", raising=False)

    catturato = {}

    def _fake_create(**kwargs):
        catturato.update(kwargs)
        return _FakeSession()

    import stripe
    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_fake_create))

    resp = client_sessione.post("/piani/checkout", data={"piano": "pro"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "discounts" not in catturato
