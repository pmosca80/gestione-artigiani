"""
Test per app/services/fondatore.py::_esegui — il job che applica il
secondo coupon (50% a vita) ai fondatori quando scade il primo anno
gratuito (100% per 12 mesi, applicato al checkout).

Stripe rimuove da solo la subscription.discounts quando il coupon
"repeating" scade: qui simuliamo le due situazioni (discount ancora
attivo / discount scaduto) mockando stripe.Subscription.retrieve.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from app import models
from app.services.fondatore import _esegui

oggi_str = str(date.today())


def _fondatore(db, username, *, sub_id="sub_123", sconto_applicato=False):
    u = models.Utente(
        username=username, password="x",
        data_registrazione=oggi_str, attivo=2, piano="pro",
        onboarding_done=True, piano_fondatore=True,
        fondatore_sconto_applicato=sconto_applicato,
        stripe_subscription_id=sub_id,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


@patch("stripe.Subscription.modify")
@patch("stripe.Subscription.retrieve")
def test_applica_coupon_post_quando_anno_gratis_scaduto(mock_retrieve, mock_modify, db, monkeypatch):
    """Subscription senza discount attivo (anno gratis scaduto) → applica
    il coupon 50% e marca fondatore_sconto_applicato."""
    monkeypatch.setenv("STRIPE_COUPON_FONDATORE_POST", "FONDATORE50POST")
    u = _fondatore(db, "scaduto@test.it")
    mock_retrieve.return_value = {"discounts": []}

    n = _esegui(db)

    assert n == 1
    mock_modify.assert_called_once_with("sub_123", discounts=[{"coupon": "FONDATORE50POST"}])
    db.refresh(u)
    assert u.fondatore_sconto_applicato is True


@patch("stripe.Subscription.modify")
@patch("stripe.Subscription.retrieve")
def test_non_applica_se_anno_gratis_ancora_attivo(mock_retrieve, mock_modify, db, monkeypatch):
    """Regressione: se la subscription ha ancora un discount attivo (anno
    gratis in corso), il coupon 50% non deve essere toccato."""
    monkeypatch.setenv("STRIPE_COUPON_FONDATORE_POST", "FONDATORE50POST")
    u = _fondatore(db, "incorso@test.it")
    mock_retrieve.return_value = {"discounts": [{"coupon": "FONDATORE-ANNOGRATIS"}]}

    n = _esegui(db)

    assert n == 0
    mock_modify.assert_not_called()
    db.refresh(u)
    assert u.fondatore_sconto_applicato is False


@patch("stripe.Subscription.modify")
@patch("stripe.Subscription.retrieve")
def test_non_richiama_stripe_se_sconto_gia_applicato(mock_retrieve, mock_modify, db, monkeypatch):
    """Idempotenza: un utente con fondatore_sconto_applicato=True non deve
    generare nessuna chiamata Stripe (evita richieste ripetute ogni giorno)."""
    monkeypatch.setenv("STRIPE_COUPON_FONDATORE_POST", "FONDATORE50POST")
    _fondatore(db, "gia_fatto@test.it", sconto_applicato=True)

    n = _esegui(db)

    assert n == 0
    mock_retrieve.assert_not_called()
    mock_modify.assert_not_called()


@patch("stripe.Subscription.modify")
@patch("stripe.Subscription.retrieve")
def test_non_tocca_utente_non_fondatore(mock_retrieve, mock_modify, db, monkeypatch):
    """Un utente normale (piano_fondatore=False) non deve mai essere
    considerato, anche se ha una subscription Stripe attiva."""
    monkeypatch.setenv("STRIPE_COUPON_FONDATORE_POST", "FONDATORE50POST")
    u = models.Utente(
        username="normale@test.it", password="x",
        data_registrazione=oggi_str, attivo=2, piano="pro",
        onboarding_done=True, piano_fondatore=False,
        stripe_subscription_id="sub_999",
    )
    db.add(u); db.commit()

    n = _esegui(db)

    assert n == 0
    mock_retrieve.assert_not_called()


@patch("stripe.Subscription.modify")
@patch("stripe.Subscription.retrieve")
def test_senza_coupon_post_configurato_non_fa_nulla(mock_retrieve, mock_modify, db, monkeypatch):
    """Se STRIPE_COUPON_FONDATORE_POST non è ancora configurato, il job
    non deve interrogare Stripe (evita errori finché il coupon non esiste)."""
    monkeypatch.delenv("STRIPE_COUPON_FONDATORE_POST", raising=False)
    _fondatore(db, "senzacoupon@test.it")

    n = _esegui(db)

    assert n == 0
    mock_retrieve.assert_not_called()
