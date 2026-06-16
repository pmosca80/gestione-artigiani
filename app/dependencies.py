from fastapi import Request, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.database import get_db

SESSION_TIMEOUT_ORE = 8  # logout automatico dopo 8h di inattività


class NotAuthenticated(Exception):
    pass


class AccountScaduto(Exception):
    pass


class AccountDisattivato(Exception):
    pass


def _check_piano_trial(utente, db: Session) -> None:
    """Verifica piano Pro e scadenza trial. Lancia AccountScaduto se trial finito."""
    piano = getattr(utente, "piano", None) or "free"

    if piano in ("starter", "pro", "business"):
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
        if piano in ("starter", "pro", "business"):
            return

    # Piano free: verifica trial 30 giorni
    if utente.data_registrazione:
        try:
            data_reg = datetime.strptime(utente.data_registrazione, "%Y-%m-%d")
            giorni_passati = (datetime.now() - data_reg).days
            if giorni_passati > 15 and utente.attivo != 2:
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

    # Timeout inattività: se l'ultima attività è > SESSION_TIMEOUT_ORE, fa logout
    last_activity = request.session.get("last_activity")
    if last_activity:
        try:
            if datetime.now() - datetime.fromisoformat(last_activity) > timedelta(hours=SESSION_TIMEOUT_ORE):
                request.session.clear()
                raise NotAuthenticated()
        except NotAuthenticated:
            raise
        except Exception:
            pass
    request.session["last_activity"] = datetime.now().isoformat()

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
        return float(str(valore).replace(",", "."))
    except (ValueError, TypeError):
        return default
