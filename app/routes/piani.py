import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import richiedi_titolare
from app.services.piani import (
    LIMITE_CLIENTI_FREE,
    conta_clienti,
    get_piano,
    get_limite_clienti,
    stripe_configurato,
    get_stripe_price_id,
    get_base_url,
)
from app.templates_config import templates

router = APIRouter(tags=["piani"], dependencies=[Depends(richiedi_titolare)])


def _get_user_id(request: Request) -> int | None:
    return request.session.get("user_id")


def _effective_id(request: Request, db: Session) -> int | None:
    """Restituisce l'ID effettivo del titolare (anche per collaboratori)."""
    uid = request.session.get("user_id")
    if not uid:
        return None
    from app.models import Utente
    u = db.query(Utente).filter(Utente.id == uid).first()
    return (getattr(u, "titolare_id", None) or uid) if u else uid


def _is_collaboratore(request: Request, db: Session) -> bool:
    uid = request.session.get("user_id")
    if not uid:
        return False
    from app.models import Utente
    u = db.query(Utente).filter(Utente.id == uid).first()
    return bool(u and getattr(u, "titolare_id", None))


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

    eff_id = _effective_id(request, db)
    is_collab = _is_collaboratore(request, db)

    piano_corrente = get_piano(db, eff_id)
    n_clienti = conta_clienti(db, eff_id)
    stripe_ok = stripe_configurato()

    from app.models import Utente
    _u = db.query(Utente).filter(Utente.id == eff_id).first()
    pro_scadenza = getattr(_u, "pro_scadenza", None) if _u else None

    return templates.TemplateResponse(
        request=request,
        name="piani.html",
        context={
            "piano_corrente": piano_corrente,
            "n_clienti": n_clienti,
            "limite_free": LIMITE_CLIENTI_FREE,
            "limite_corrente": get_limite_clienti(piano_corrente),
            "stripe_ok": stripe_ok,
            "price_id_starter":  get_stripe_price_id("starter"),
            "price_id_pro":      get_stripe_price_id("pro"),
            "price_id_business": get_stripe_price_id("business"),
            "trial_scaduto": trial_scaduto,
            "successo": successo,
            "is_collaboratore": is_collab,
            "pro_scadenza": pro_scadenza,
        },
    )


_PIANI_VALIDI = {"starter", "pro", "business"}

@router.post("/piani/checkout")
def crea_checkout(
    request: Request,
    piano: str = Form("pro"),
    db: Session = Depends(get_db),
):
    import stripe as _stripe

    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    if _is_collaboratore(request, db):
        return RedirectResponse("/piani?errore=solo_titolare", status_code=303)

    if piano not in _PIANI_VALIDI:
        piano = "pro"

    if not stripe_configurato():
        return RedirectResponse("/piani?errore=stripe_non_configurato", status_code=303)

    price_id = get_stripe_price_id(piano)
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
            metadata={"piano": piano},
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


@router.get("/piani/portale")
def portale_stripe(
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=303)
    if _is_collaboratore(request, db):
        return RedirectResponse("/piani?errore=solo_titolare", status_code=303)

    if not stripe_configurato():
        return RedirectResponse("/piani?errore=stripe_non_configurato", status_code=303)

    from app.models import Utente
    import stripe as _stripe
    _stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

    utente = db.query(Utente).filter(Utente.id == user_id).first()
    if not utente or not utente.stripe_customer_id:
        return RedirectResponse("/piani?errore=nessun_abbonamento_trovato", status_code=303)

    base_url = get_base_url(request)
    try:
        portal = _stripe.billing_portal.Session.create(
            customer=utente.stripe_customer_id,
            return_url=f"{base_url}/piani",
        )
        return RedirectResponse(portal.url, status_code=303)
    except Exception as exc:
        import urllib.parse
        msg = urllib.parse.quote(str(exc)[:120])
        return RedirectResponse(f"/piani?errore={msg}", status_code=303)


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
            piano_acquistato = (obj.get("metadata") or {}).get("piano", "pro")
            if piano_acquistato not in _PIANI_VALIDI:
                piano_acquistato = "pro"
            _attiva_pro(db, user_id, obj.get("customer"), obj.get("subscription"), piano_acquistato)

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


def _attiva_pro(db: Session, user_id: int, customer_id: str | None, subscription_id: str | None, piano: str = "pro"):
    from app.models import Utente
    u = db.query(Utente).filter(Utente.id == user_id).first()
    if u:
        era_gia_pro = u.piano != "free"
        u.piano = piano
        u.attivo = 2
        if customer_id:
            u.stripe_customer_id = customer_id
        if subscription_id:
            u.stripe_subscription_id = subscription_id
        db.commit()
        if not era_gia_pro:
            from app.services.email import invia_conferma_pro
            import threading
            threading.Thread(
                target=invia_conferma_pro,
                args=(u.username,),
                daemon=True,
            ).start()


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
