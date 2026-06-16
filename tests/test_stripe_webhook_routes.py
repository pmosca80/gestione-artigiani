"""
Test HTTP per POST /stripe/webhook.

Copre: secret non configurata → {"ok": False}, firma Stripe invalida → 400,
payload non valido → 400, evento non-checkout → {"ok": True} senza modifiche DB,
evento checkout.session.completed → fattura aggiornata a "pagata" e lavoro "pagato".

Strategia di mock: stripe.Webhook.construct_event è patchata via monkeypatch
per evitare dipendenza da chiavi Stripe reali e dalla firma HMAC.
"""
from datetime import date

import pytest

from app import models

oggi_str = str(date.today())


# ── Fixture base (solo get_db) ────────────────────────────────────────────────

@pytest.fixture
def stripe_client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helper DB ──────────────────────────────────────────────────────────────────

def _utente_e_lavoro(db):
    u = models.Utente(
        username="stripe@t.it", password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)

    c = models.Cliente(
        utente_id=u.id, tipo_cliente="privato",
        nome="Test", cognome="Stripe", data_creazione=oggi_str,
    )
    db.add(c); db.commit(); db.refresh(c)

    l = models.Lavoro(
        utente_id=u.id, cliente_id=c.id, titolo="Lavoro Stripe",
        data_lavoro=date.today(), stato="in_corso", priorita="normale",
        importo_preventivato=1000.0, aliquota_iva=22.0, sconto=0.0,
        importo_pagato=0.0, residuo_pagamento=1000.0, data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return u, l


def _fattura(db, utente_id, lavoro_id, pl_id="pl_test123", stato="emessa"):
    f = models.FatturaEmessa(
        utente_id=utente_id,
        lavoro_id=lavoro_id,
        numero=1,
        anno=date.today().year,
        data_emissione=date.today(),
        importo_imponibile=1000.0,
        importo_iva=220.0,
        importo_totale=1220.0,
        stato=stato,
        stripe_payment_link_id=pl_id,
        data_creazione=oggi_str,
    )
    db.add(f); db.commit(); db.refresh(f)
    return f


# ── Test ───────────────────────────────────────────────────────────────────────

def test_webhook_senza_secret_configurato(stripe_client, monkeypatch):
    """POST /stripe/webhook senza STRIPE_WEBHOOK_SECRET → {"ok": False}."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)

    resp = stripe_client.post(
        "/stripe/webhook",
        content=b'{"type":"test"}',
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_webhook_firma_invalida_400(stripe_client, monkeypatch):
    """POST /stripe/webhook con firma invalida → 400."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    import stripe as stripe_lib

    def _bad_sig(*a, **kw):
        raise stripe_lib.error.SignatureVerificationError("bad sig", "header")

    monkeypatch.setattr("stripe.Webhook.construct_event", _bad_sig)

    resp = stripe_client.post(
        "/stripe/webhook",
        content=b"payload",
        headers={"stripe-signature": "t=1,v1=bad"},
    )
    assert resp.status_code == 400


def test_webhook_payload_non_valido_400(stripe_client, monkeypatch):
    """POST /stripe/webhook con payload non valido → 400."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    def _bad_payload(*a, **kw):
        raise ValueError("payload non valido")

    monkeypatch.setattr("stripe.Webhook.construct_event", _bad_payload)

    resp = stripe_client.post(
        "/stripe/webhook",
        content=b"garbage",
        headers={"stripe-signature": "t=1,v1=x"},
    )
    assert resp.status_code == 400


def test_webhook_evento_non_checkout(stripe_client, db, monkeypatch):
    """Evento di tipo diverso da checkout.session.completed → {"ok": True}, DB invariato."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    u, l = _utente_e_lavoro(db)
    f = _fattura(db, u.id, l.id, stato="emessa")

    def _other_event(*a, **kw):
        return {"type": "payment_intent.succeeded", "data": {"object": {}}}

    monkeypatch.setattr("stripe.Webhook.construct_event", _other_event)

    resp = stripe_client.post(
        "/stripe/webhook",
        content=b'{}',
        headers={"stripe-signature": "t=1,v1=x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    db.refresh(f)
    assert f.stato == "emessa"  # invariato


def test_webhook_checkout_completato_aggiorna_fattura(stripe_client, db, monkeypatch):
    """Evento checkout.session.completed → fattura.stato='pagata', lavoro.stato_pagamento='pagato'."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    u, l = _utente_e_lavoro(db)
    f = _fattura(db, u.id, l.id, pl_id="pl_stripe_ok", stato="emessa")

    def _checkout_event(*a, **kw):
        return {
            "type": "checkout.session.completed",
            "data": {"object": {"payment_link": "pl_stripe_ok"}},
        }

    monkeypatch.setattr("stripe.Webhook.construct_event", _checkout_event)

    resp = stripe_client.post(
        "/stripe/webhook",
        content=b'{}',
        headers={"stripe-signature": "t=1,v1=x"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    db.refresh(f)
    assert f.stato == "pagata"

    db.refresh(l)
    assert l.stato_pagamento == "pagato"
    assert l.importo_pagato == 1220.0
    assert l.residuo_pagamento == 0
