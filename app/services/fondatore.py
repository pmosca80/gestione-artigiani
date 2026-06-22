from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Utente
from app.services.piani import get_stripe_coupon_fondatore_post
from app.services.scheduler_lock import con_lock
from app.logger import get_logger

logger = get_logger("fondatore")


@con_lock("fondatore_sconto_post_anno")
def applica_sconto_post_anno_gratuito():
    logger.info("Controllo coupon post-anno-gratuito fondatori in corso...")
    db: Session = SessionLocal()
    try:
        _esegui(db)
    except Exception as e:
        logger.error(f"Errore durante applicazione sconto post anno gratuito: {e}")
    finally:
        db.close()


def _esegui(db: Session) -> int:
    """Nucleo testabile: restituisce il numero di sconti 50% applicati.

    Un fondatore ottiene il 100% di sconto per i primi 12 mesi al
    checkout (coupon "repeating"); Stripe lo rimuove automaticamente
    dalla subscription una volta scaduto. Qui controlliamo chi non ha
    più nessun discount attivo e gli applichiamo il secondo coupon
    (50% a vita), una sola volta per utente.
    """
    coupon_post = get_stripe_coupon_fondatore_post()
    if not coupon_post:
        return 0

    import stripe

    candidati = (
        db.query(Utente)
        .filter(
            Utente.piano_fondatore == True,
            Utente.fondatore_sconto_applicato == False,
            Utente.stripe_subscription_id.isnot(None),
        )
        .all()
    )

    applicati = 0
    for utente in candidati:
        try:
            sub = stripe.Subscription.retrieve(utente.stripe_subscription_id)
        except Exception as e:
            logger.error(f"Errore lettura subscription {utente.stripe_subscription_id} (utente {utente.id}): {e}")
            continue

        if sub.get("discounts"):
            continue  # l'anno gratis è ancora attivo, non c'è nulla da fare

        try:
            stripe.Subscription.modify(
                utente.stripe_subscription_id,
                discounts=[{"coupon": coupon_post}],
            )
        except Exception as e:
            logger.error(f"Errore applicazione coupon post-anno a {utente.stripe_subscription_id} (utente {utente.id}): {e}")
            continue

        utente.fondatore_sconto_applicato = True
        db.commit()
        applicati += 1
        logger.info(f"Sconto post-anno-gratuito applicato a utente {utente.id}")

    return applicati
