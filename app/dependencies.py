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

    piano = getattr(utente, "piano", None) or "free"
    if piano == "pro":
        return user_id

    if utente.data_registrazione:
        try:
            data_reg = datetime.strptime(utente.data_registrazione, "%Y-%m-%d")
            giorni_passati = (datetime.now() - data_reg).days
            if giorni_passati > 30 and utente.attivo != 2:
                raise AccountScaduto()
        except AccountScaduto:
            raise
        except:
            pass

    return user_id


def get_current_user(request: Request, db: Session = Depends(get_db)) -> int:
    return verifica_account(request, db)


def to_float(valore, default=0.0):
    try:
        return float(valore)
    except (ValueError, TypeError):
        return default