"""Test per POST /webhook/stripe in app/routes/piani.py.

Regressione: senza STRIPE_WEBHOOK_SECRET configurata, il codice si fidava
del payload senza verificarne la firma (stripe.Event.construct_from invece
di stripe.Webhook.construct_event) — chiunque poteva POSTare un evento
"checkout.session.completed" falso con client_reference_id di un account a
piacere e attivarsi un piano a pagamento gratis. Ora senza secret il
webhook rifiuta subito, senza elaborare nulla.
"""
from datetime import date

from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.main import app

oggi_str = str(date.today())


def _client(db):
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app, raise_server_exceptions=True)
    return client


def _utente_free(db):
    u = models.Utente(
        username="webhook@t.it", password="x", piano="free",
        attivo=1, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_webhook_senza_secret_rifiuta_e_non_attiva_piano(db, monkeypatch):
    """Il caso che ha causato il bug: nessun secret configurato, payload
    falsificato che dichiara un upgrade a pagamento per un utente free.

    stripe.Event.construct_from è mockato per restituire un evento "pulito"
    (un dict semplice, .get() funziona) — isola la verifica dalla logica di
    sicurezza vera e propria, senza dipendere da come la libreria stripe
    installata si comporta internamente con un evento non firmato."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    utente = _utente_free(db)

    def _evento_falso(*a, **kw):
        return {
            "type": "checkout.session.completed",
            "data": {"object": {
                "client_reference_id": str(utente.id),
                "payment_status": "paid",
                "metadata": {"piano": "business"},
            }},
        }

    monkeypatch.setattr("stripe.Event.construct_from", _evento_falso)

    client = _client(db)
    try:
        resp = client.post(
            "/webhook/stripe",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400

    db.refresh(utente)
    assert utente.piano == "free"  # non attivato: il payload non era firmato


def test_webhook_firma_invalida_400(db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    import stripe as stripe_lib

    def _bad_sig(*a, **kw):
        raise stripe_lib.error.SignatureVerificationError("bad sig", "header")

    monkeypatch.setattr("stripe.Webhook.construct_event", _bad_sig)

    client = _client(db)
    try:
        resp = client.post(
            "/webhook/stripe",
            content=b"payload",
            headers={"stripe-signature": "t=1,v1=bad"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400


def test_webhook_checkout_completato_con_firma_valida_attiva_piano(db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    utente = _utente_free(db)

    def _evento_valido(*a, **kw):
        return {
            "type": "checkout.session.completed",
            "data": {"object": {
                "client_reference_id": str(utente.id),
                "payment_status": "paid",
                "customer": "cus_123",
                "subscription": "sub_123",
                "metadata": {"piano": "pro"},
            }},
        }

    monkeypatch.setattr("stripe.Webhook.construct_event", _evento_valido)

    client = _client(db)
    try:
        resp = client.post(
            "/webhook/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=x"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200

    db.refresh(utente)
    assert utente.piano == "pro"
