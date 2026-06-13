import json
import os
from datetime import datetime

from sqlalchemy.orm import Session

from app.logger import get_logger

logger = get_logger("push")

_VAPID_CLAIMS = {"sub": "mailto:info@gestionale-artigiani.it"}


def _private_key() -> str:
    raw = os.getenv("VAPID_PRIVATE_KEY", "")
    return raw.replace("\\n", "\n")


def invia_push(db: Session, utente_id: int, titolo: str, corpo: str, url: str = "/") -> int:
    pk = _private_key()
    if not pk:
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush non installato — push saltata")
        return 0

    from app.models import PushSubscription

    subs = db.query(PushSubscription).filter(PushSubscription.utente_id == utente_id).all()
    if not subs:
        return 0

    payload = json.dumps({"titolo": titolo, "corpo": corpo, "url": url})
    inviate = 0
    da_eliminare = []

    for sub in subs:
        try:
            info = json.loads(sub.subscription_json)
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=pk,
                vapid_claims=_VAPID_CLAIMS,
            )
            inviate += 1
        except Exception as exc:
            # 404/410 = subscription scaduta, rimuovi
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                da_eliminare.append(sub.id)
            logger.warning(f"Push fallita utente {utente_id} sub {sub.id}: {exc}")

    if da_eliminare:
        for sid in da_eliminare:
            db.query(PushSubscription).filter(PushSubscription.id == sid).delete()
        db.commit()

    return inviate
