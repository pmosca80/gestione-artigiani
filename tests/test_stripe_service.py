"""Test per app/services/stripe_service.py. Nessuna chiamata di rete reale:
stripe.Price.create/stripe.PaymentLink.create sono mockate."""
from unittest.mock import MagicMock, patch

import pytest

from app.services import stripe_service as svc


def test_non_configurato_se_env_assente(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert svc.stripe_configurato() is False


def test_configurato_se_env_presente(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xxx")
    assert svc.stripe_configurato() is True


def test_crea_payment_link_senza_chiave_solleva_errore(monkeypatch):
    """Senza STRIPE_SECRET_KEY non deve mai arrivare a chiamare l'API Stripe
    (fallirebbe in modo confuso): deve fallire subito con un errore chiaro."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        svc.crea_payment_link("001/2026", 100.0, fattura_id=1, utente_id=1)


def test_crea_payment_link_ok(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xxx")

    price_mock = MagicMock(id="price_abc")
    link_mock = MagicMock(id="plink_abc", url="https://buy.stripe.com/plink_abc")

    with patch("stripe.Price.create", return_value=price_mock) as price_create, \
         patch("stripe.PaymentLink.create", return_value=link_mock) as link_create:
        link_id, link_url = svc.crea_payment_link("007/2026", 123.45, fattura_id=42, utente_id=9)

    assert link_id == "plink_abc"
    assert link_url == "https://buy.stripe.com/plink_abc"

    # importo in centesimi, arrotondato, valuta EUR
    _, kwargs = price_create.call_args
    assert kwargs["unit_amount"] == 12345
    assert kwargs["currency"] == "eur"
    assert "007/2026" in kwargs["product_data"]["name"]

    # collega il payment link alla fattura/utente corretti per il webhook
    _, kwargs = link_create.call_args
    assert kwargs["line_items"] == [{"price": "price_abc", "quantity": 1}]
    assert kwargs["metadata"] == {"fattura_id": "42", "utente_id": "9"}


def test_crea_payment_link_arrotonda_importo_decimale(monkeypatch):
    """0.005 di differenza non deve far divergere unit_amount dall'importo reale."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xxx")
    price_mock = MagicMock(id="price_x")
    link_mock = MagicMock(id="plink_x", url="https://buy.stripe.com/x")

    with patch("stripe.Price.create", return_value=price_mock) as price_create, \
         patch("stripe.PaymentLink.create", return_value=link_mock):
        svc.crea_payment_link("001/2026", 10.999, fattura_id=1, utente_id=1)

    _, kwargs = price_create.call_args
    assert kwargs["unit_amount"] == 1100  # round(10.999 * 100) = 1100, non 1099
