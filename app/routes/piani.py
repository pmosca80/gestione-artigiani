import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.piani import (
    LIMITE_CLIENTI_FREE,
    conta_clienti,
    get_piano,
    stripe_configurato,
    get_stripe_price_id,
    get_base_url,
)

router = APIRouter(tags=["piani"])
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _get_user_id(request: Request) -> int | None:
    return request.session.get("user_id")


@router.get("/piani", response_class=HTMLResponse)
def pagina_piani(
    request: Request,
    trial_scaduto: bool = False,
    successo: bool = False,
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    piano_corrente = get_piano(db, user_id)
    n_clienti = conta_clienti(db, user_id)
    stripe_ok = stripe_configurato()
    price_id = get_stripe_price_id()

    return templates.TemplateResponse(
        request=request,
        name="piani.html",
        context={
            "piano_corrente": piano_corrente,
            "n_clienti": n_clienti,
            "limite_free": LIMITE_CLIENTI_FREE,
            "stripe_ok": stripe_ok,
            "price_id": price_id,
            "trial_scaduto": trial_scaduto,
            "successo": successo,
        },
    )


@router.post("/piani/checkout")
def crea_checkout(
    request: Request,
    db: Session = Depends(get_db),
):
    import stripe as _stripe

    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    if not stripe_configurato():
        return RedirectResponse("/piani?errore=stripe_non_configurato", status_code=303)

    price_id = get_stripe_price_id()
    if not price_id:
        return RedirectResponse("/piani?errore=price_non_configurato", status_code=303)

    _stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    base_url = get_base_url(request)

    from app.models import Utente
    utente = db.query(Utente).filter(Utente.id == user_id).first()
    email = utente.username if utente and "@" in (utente.username or "") else None

    try:
        session = _stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}/piani/successo?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/piani/annullato",
            client_reference_id=str(user_id),
            **({"customer_email": email} if email else {}),
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as exc:
        import urllib.parse
        msg = urllib.parse.quote(str(exc)[:120])
        return RedirectResponse(f"/piani?errore={msg}", status_code=303)


@router.get("/piani/successo", response_class=HTMLResponse)
def checkout_successo(
    request: Request,
    session_id: str = "",
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    if session_id and stripe_configurato():
        import stripe as _stripe
        _stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        try:
            cs = _stripe.checkout.Session.retrieve(session_id)
            if cs.payment_status == "paid":
                _attiva_pro(db, user_id, cs.customer, cs.subscription)
        except Exception:
            pass

    return RedirectResponse("/piani?successo=1", status_code=303)


@router.get("/piani/annullato", response_class=HTMLResponse)
def checkout_annullato(request: Request):
    return RedirectResponse("/piani", status_code=303)


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    import stripe as _stripe

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    _stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

    try:
        if webhook_secret:
            event = _stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            import json
            event = _stripe.Event.construct_from(json.loads(payload), _stripe.api_key)
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "invalid"}, status_code=400)

    evt_type = event["type"]
    obj = event["data"]["object"]

    if evt_type == "checkout.session.completed":
        user_id = _safe_int(obj.get("client_reference_id"))
        if user_id and obj.get("payment_status") == "paid":
            _attiva_pro(db, user_id, obj.get("customer"), obj.get("subscription"))

    elif evt_type in ("customer.subscription.deleted", "customer.subscription.paused"):
        customer_id = obj.get("customer")
        if customer_id:
            _revoca_pro(db, customer_id)

    elif evt_type == "invoice.payment_failed":
        subscription_id = obj.get("subscription")
        if subscription_id:
            _revoca_pro_by_subscription(db, subscription_id)

    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True})


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _attiva_pro(db: Session, user_id: int, customer_id: str | None, subscription_id: str | None):
    from app.models import Utente
    u = db.query(Utente).filter(Utente.id == user_id).first()
    if u:
        u.piano = "pro"
        u.attivo = 2
        if customer_id:
            u.stripe_customer_id = customer_id
        if subscription_id:
            u.stripe_subscription_id = subscription_id
        db.commit()


def _revoca_pro(db: Session, customer_id: str):
    from app.models import Utente
    u = db.query(Utente).filter(Utente.stripe_customer_id == customer_id).first()
    if u:
        u.piano = "free"
        db.commit()


def _revoca_pro_by_subscription(db: Session, subscription_id: str):
    from app.models import Utente
    u = db.query(Utente).filter(Utente.stripe_subscription_id == subscription_id).first()
    if u:
        u.piano = "free"
        db.commit()
