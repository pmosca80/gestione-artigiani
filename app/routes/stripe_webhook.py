import os
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["stripe"])


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        return {"ok": False, "reason": "STRIPE_WEBHOOK_SECRET non configurata"}

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Payload non valido")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Firma Stripe non valida")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        pl_id = session.get("payment_link")
        if pl_id:
            from app.models import FatturaEmessa
            fattura = db.query(FatturaEmessa).filter(
                FatturaEmessa.stripe_payment_link_id == pl_id
            ).first()
            if fattura and fattura.stato != "pagata":
                fattura.stato = "pagata"
                lav = fattura.lavoro
                if lav:
                    lav.stato_pagamento = "pagato"
                    importo = float(fattura.importo_totale or 0)
                    lav.importo_pagato = importo
                    lav.residuo_pagamento = 0
                db.commit()

    return {"ok": True}
