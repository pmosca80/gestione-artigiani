from fastapi import Request, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db


class NotAuthenticated(Exception):
    pass


class AccountScaduto(Exception):
    pass


class AccountDisattivato(Exception):
    pass


def _check_piano_trial(utente, db: Session) -> None:
    """Verifica piano Pro e scadenza trial. Lancia AccountScaduto se trial finito."""
    piano = getattr(utente, "piano", None) or "free"

    if piano == "pro":
        pro_scadenza = getattr(utente, "pro_scadenza", None)
        stripe_sub = getattr(utente, "stripe_subscription_id", None)
        if pro_scadenza and not stripe_sub:
            try:
                if datetime.now() > datetime.strptime(pro_scadenza, "%Y-%m-%d"):
                    utente.piano = "free"
                    utente.attivo = 1
                    utente.pro_scadenza = None
                    db.commit()
                    piano = "free"
            except AccountScaduto:
                raise
            except Exception:
                pass
        if piano == "pro":
            return

    # Piano free: verifica trial 30 giorni
    if utente.data_registrazione:
        try:
            data_reg = datetime.strptime(utente.data_registrazione, "%Y-%m-%d")
            giorni_passati = (datetime.now() - data_reg).days
            if giorni_passati > 30 and utente.attivo != 2:
                raise AccountScaduto()
        except AccountScaduto:
            raise
        except Exception:
            pass


def verifica_account(request: Request, db: Session) -> int:
    from app.models import Utente

    user_id = request.session.get("user_id")
    if not user_id:
        raise NotAuthenticated()

    utente = db.query(Utente).filter(Utente.id == user_id).first()
    if not utente:
        raise NotAuthenticated()

    if utente.attivo == 0:
        raise AccountDisattivato()

    if utente.username == "admin":
        return user_id

    titolare_id = getattr(utente, "titolare_id", None)
    if titolare_id:
        # Collaboratore: verifica e usa l'account del titolare
        titolare = db.query(Utente).filter(Utente.id == titolare_id).first()
        if not titolare or titolare.attivo == 0:
            raise AccountDisattivato()
        _check_piano_trial(titolare, db)
        return titolare_id

    _check_piano_trial(utente, db)
    return user_id


def get_current_user(request: Request, db: Session = Depends(get_db)) -> int:
    return verifica_account(request, db)


def to_float(valore, default=0.0):
    try:
        return float(valore)
    except (ValueError, TypeError):
        return default
