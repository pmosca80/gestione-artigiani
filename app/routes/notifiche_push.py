import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import PushSubscription

router = APIRouter(prefix="/notifiche/push", tags=["push"])


@router.post("/subscribe")
async def subscribe(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    body = await request.json()
    endpoint = body.get("endpoint", "")
    if not endpoint:
        return JSONResponse({"ok": False, "error": "endpoint mancante"}, status_code=400)

    # Evita duplicati sullo stesso endpoint
    existing = db.query(PushSubscription).filter(
        PushSubscription.utente_id == user_id,
        PushSubscription.endpoint == endpoint,
    ).first()
    if existing:
        existing.subscription_json = json.dumps(body)
        db.commit()
        return {"ok": True, "nuovo": False}

    sub = PushSubscription(
        utente_id=user_id,
        endpoint=endpoint,
        subscription_json=json.dumps(body),
        creata_il=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(sub)
    db.commit()
    return {"ok": True, "nuovo": True}


@router.post("/unsubscribe")
async def unsubscribe(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    body = await request.json()
    endpoint = body.get("endpoint", "")
    deleted = (
        db.query(PushSubscription)
        .filter(PushSubscription.utente_id == user_id, PushSubscription.endpoint == endpoint)
        .delete()
    )
    db.commit()
    return {"ok": True, "rimossi": deleted}
