"""
Test HTTP per le route /notifiche/push/*.

Copre: subscribe (nuovo endpoint → creato in DB, endpoint mancante → 400,
stesso endpoint → aggiorna JSON senza duplicati), unsubscribe (rimuove subscription,
endpoint non registrato → rimossi=0).
"""
import json
from datetime import date

import pytest

from app import models

oggi_str = str(date.today())


# ── POST /notifiche/push/subscribe ────────────────────────────────────────────

def test_subscribe_nuovo_endpoint(client_http, db, utente_test):
    """POST /subscribe con endpoint valido → {"ok": True, "nuovo": True}, subscription in DB."""
    payload = {
        "endpoint": "https://push.example.com/sub/abc123",
        "keys": {"p256dh": "chiave_pub", "auth": "auth_secret"},
    }

    resp = client_http.post("/notifiche/push/subscribe", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "nuovo": True}

    subs = (
        db.query(models.PushSubscription)
        .filter(models.PushSubscription.utente_id == utente_test.id)
        .all()
    )
    assert len(subs) == 1
    assert subs[0].endpoint == payload["endpoint"]
    stored = json.loads(subs[0].subscription_json)
    assert stored["keys"]["p256dh"] == "chiave_pub"


def test_subscribe_endpoint_mancante_400(client_http):
    """POST /subscribe senza campo endpoint → 400."""
    resp = client_http.post("/notifiche/push/subscribe", json={"keys": {}})
    assert resp.status_code == 400
    assert resp.json()["ok"] is False


def test_subscribe_stesso_endpoint_non_duplica(client_http, db, utente_test):
    """Secondo POST con stesso endpoint → {"ok": True, "nuovo": False}, una sola subscription in DB."""
    payload = {"endpoint": "https://push.example.com/sub/dup"}

    client_http.post("/notifiche/push/subscribe", json=payload)
    resp = client_http.post("/notifiche/push/subscribe", json=payload)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "nuovo": False}

    count = (
        db.query(models.PushSubscription)
        .filter(
            models.PushSubscription.utente_id == utente_test.id,
            models.PushSubscription.endpoint == payload["endpoint"],
        )
        .count()
    )
    assert count == 1


def test_subscribe_stesso_endpoint_aggiorna_json(client_http, db, utente_test):
    """Secondo POST con stesso endpoint e payload diverso → subscription_json aggiornato."""
    ep = "https://push.example.com/sub/update"
    client_http.post("/notifiche/push/subscribe", json={"endpoint": ep, "version": 1})

    payload_v2 = {"endpoint": ep, "version": 2, "keys": {"p256dh": "nuova_chiave"}}
    client_http.post("/notifiche/push/subscribe", json=payload_v2)

    sub = (
        db.query(models.PushSubscription)
        .filter(models.PushSubscription.endpoint == ep)
        .first()
    )
    assert json.loads(sub.subscription_json)["version"] == 2


# ── POST /notifiche/push/unsubscribe ─────────────────────────────────────────

def test_unsubscribe_ok(client_http, db, utente_test):
    """POST /unsubscribe dopo subscribe → rimossi=1, subscription eliminata."""
    ep = "https://push.example.com/sub/remove"
    client_http.post("/notifiche/push/subscribe", json={"endpoint": ep})

    resp = client_http.post("/notifiche/push/unsubscribe", json={"endpoint": ep})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["rimossi"] == 1

    count = (
        db.query(models.PushSubscription)
        .filter(models.PushSubscription.endpoint == ep)
        .count()
    )
    assert count == 0


def test_unsubscribe_endpoint_non_registrato(client_http):
    """POST /unsubscribe con endpoint non registrato → rimossi=0."""
    resp = client_http.post(
        "/notifiche/push/unsubscribe",
        json={"endpoint": "https://push.example.com/sub/inesistente"},
    )
    assert resp.status_code == 200
    assert resp.json()["rimossi"] == 0
