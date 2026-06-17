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


class AccessoNegato(Exception):
    """Area riservata al titolare: il collaboratore loggato non può accedervi."""
    pass


def _check_piano_trial(utente, db: Session) -> None:
    """Verifica piano Pro e scadenza trial. Lancia AccountScaduto se trial finito."""
    piano = getattr(utente, "piano", None) or "free"

    if piano in ("starter", "pro", "business"):
        pro_scadenza = getattr(utente, "pro_scadenza", None)
        stripe_sub = getattr(utente, "stripe_subscription_id", None)
        if pro_scadenza and not stripe_sub:
            try:
                scad = pro_scadenza if not isinstance(pro_scadenza, str) else datetime.strptime(pro_scadenza, "%Y-%m-%d").date()
                if datetime.now().date() > scad:
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
            dr = utente.data_registrazione
            reg = dr if not isinstance(dr, str) else datetime.strptime(dr, "%Y-%m-%d").date()
            giorni_passati = (datetime.now().date() - reg).days
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

    # Invalida sessioni dopo cambio password confrontando la firma dell'hash
    if utente.password:
        expected_sig = utente.password[-12:]
        stored_sig = request.session.get("pw_sig")
        if stored_sig is None:
            request.session["pw_sig"] = expected_sig  # popola sessioni pre-feature
        elif stored_sig != expected_sig:
            request.session.clear()
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


def get_attore(request: Request, db: Session):
    """Utente effettivamente loggato (non risolto al titolare). None se non autenticato."""
    from app.models import Utente
    uid = request.session.get("user_id")
    if not uid:
        return None
    return db.query(Utente).filter(Utente.id == uid).first()


def is_collaboratore(request: Request, db: Session) -> bool:
    """True se l'utente loggato è un collaboratore (non il titolare dell'account)."""
    u = get_attore(request, db)
    return bool(u and getattr(u, "titolare_id", None))


def scope_collaboratore(request: Request, db: Session) -> int | None:
    """ID del collaboratore loggato per filtrare i dati visibili, o None se titolare (vede tutto)."""
    u = get_attore(request, db)
    if u and getattr(u, "titolare_id", None):
        return u.id
    return None


def lavoro_consentito(lavoro, request: Request, db: Session) -> bool:
    """True se il lavoro esiste ed è visibile/modificabile dall'utente loggato."""
    if lavoro is None:
        return False
    scope = scope_collaboratore(request, db)
    if scope is None:
        return True
    return lavoro.assegnato_a_id == scope


def blocca_collaboratore(request: Request, db: Session) -> bool:
    """True se l'utente loggato è un collaboratore e l'area richiesta deve essergli negata."""
    return is_collaboratore(request, db)


def richiedi_titolare(request: Request, db: Session = Depends(get_db)) -> None:
    """Dependency per router riservati al titolare (impostazioni, contabilità, billing).
    Da usare come APIRouter(dependencies=[Depends(richiedi_titolare)])."""
    if is_collaboratore(request, db):
        raise AccessoNegato()


def to_float(valore, default=0.0):
    try:
        return float(str(valore).replace(",", "."))
    except (ValueError, TypeError):
        return default
