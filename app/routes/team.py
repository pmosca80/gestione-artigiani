import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_collaboratore as _solo_titolare
from app.services.piani import get_base_url, get_piano, ha_team, max_collaboratori
from app.templates_config import templates
from app.validators import USERNAME_MAX, PASSWORD_MAX

router = APIRouter(tags=["team"])

# Limite collaboratori del piano Pro, usato solo nel testo promozionale
# mostrato a chi non ha (ancora) accesso al team (free/starter).
LIMITE_COLLABORATORI_PRO = 3


@router.get("/team", response_class=HTMLResponse)
def pagina_team(
    request: Request,
    errore: str = "",
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    if _solo_titolare(request, db):
        return RedirectResponse("/", status_code=303)

    from app.models import Utente, InvitoAccount

    piano = get_piano(db, user_id)
    collaboratori = db.query(Utente).filter(Utente.titolare_id == user_id).all()

    oggi = datetime.now().strftime("%Y-%m-%d")
    db.query(InvitoAccount).filter(
        InvitoAccount.titolare_id == user_id,
        InvitoAccount.scadenza < oggi,
        InvitoAccount.usato == 0,
    ).delete()
    db.commit()

    invito_attivo = (
        db.query(InvitoAccount)
        .filter(
            InvitoAccount.titolare_id == user_id,
            InvitoAccount.scadenza >= oggi,
            InvitoAccount.usato == 0,
        )
        .order_by(InvitoAccount.id.desc())
        .first()
    )

    base_url = get_base_url(request)
    link_invito = f"{base_url}/register/invito/{invito_attivo.token}" if invito_attivo else None

    return templates.TemplateResponse(
        request=request,
        name="team.html",
        context={
            "piano": piano,
            "ha_team_piano": ha_team(piano),
            "collaboratori": collaboratori,
            "max_collaboratori": max_collaboratori(piano),
            "limite_collaboratori_pro": LIMITE_COLLABORATORI_PRO,
            "link_invito": link_invito,
            "invito_scadenza": invito_attivo.scadenza if invito_attivo else None,
            "errore": errore,
        },
    )


@router.post("/team/invita")
def genera_invito(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    if _solo_titolare(request, db):
        return RedirectResponse("/", status_code=303)

    from app.models import Utente, InvitoAccount

    piano = get_piano(db, user_id)
    if not ha_team(piano):
        return RedirectResponse("/team?errore=pro_required", status_code=303)

    n_collab = db.query(Utente).filter(Utente.titolare_id == user_id).count()
    max_c = max_collaboratori(piano)
    if max_c is not None and n_collab >= max_c:
        return RedirectResponse("/team?errore=limite_raggiunto", status_code=303)

    # Revoca inviti precedenti non usati
    db.query(InvitoAccount).filter(
        InvitoAccount.titolare_id == user_id,
        InvitoAccount.usato == 0,
    ).delete()

    token = secrets.token_urlsafe(32)
    scadenza = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    db.add(InvitoAccount(
        titolare_id=user_id,
        token=token,
        scadenza=scadenza,
        usato=0,
        data_creazione=datetime.now().strftime("%Y-%m-%d"),
    ))
    db.commit()
    return RedirectResponse("/team", status_code=303)


@router.post("/team/rimuovi/{collaboratore_id}")
def rimuovi_collaboratore(
    collaboratore_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    if _solo_titolare(request, db):
        return RedirectResponse("/", status_code=303)

    from app.models import Utente

    collab = db.query(Utente).filter(
        Utente.id == collaboratore_id,
        Utente.titolare_id == user_id,
    ).first()
    if collab:
        collab.titolare_id = None
        collab.ruolo = "titolare"
        db.commit()
    return RedirectResponse("/team", status_code=303)


@router.get("/register/invito/{token}", response_class=HTMLResponse)
def pagina_register_invito(token: str, request: Request, db: Session = Depends(get_db)):
    from app.models import InvitoAccount, Utente

    oggi = datetime.now().strftime("%Y-%m-%d")
    invito = db.query(InvitoAccount).filter(
        InvitoAccount.token == token,
        InvitoAccount.usato == 0,
        InvitoAccount.scadenza >= oggi,
    ).first()

    titolare = db.query(Utente).filter(Utente.id == invito.titolare_id).first() if invito else None

    return templates.TemplateResponse(
        request=request,
        name="register_invito.html",
        context={
            "token": token,
            "titolare_username": titolare.username if titolare else "",
            "token_invalido": not invito,
            "errore": None,
        },
    )


@router.post("/register/invito/{token}")
def completa_register_invito(
    token: str,
    request: Request,
    username: str = Form(..., max_length=USERNAME_MAX),
    password: str = Form(..., max_length=PASSWORD_MAX),
    db: Session = Depends(get_db),
):
    from app.models import InvitoAccount, Utente
    from app.security import hash_password

    oggi = datetime.now().strftime("%Y-%m-%d")
    invito = db.query(InvitoAccount).filter(
        InvitoAccount.token == token,
        InvitoAccount.usato == 0,
        InvitoAccount.scadenza >= oggi,
    ).first()
    titolare = db.query(Utente).filter(Utente.id == invito.titolare_id).first() if invito else None

    def _errore(msg: str):
        return templates.TemplateResponse(
            request=request,
            name="register_invito.html",
            context={
                "token": token,
                "titolare_username": titolare.username if titolare else "",
                "token_invalido": not invito,
                "errore": msg,
            },
        )

    if not invito or not titolare:
        return _errore("Link di invito non valido o scaduto.")

    if db.query(Utente).filter(Utente.username == username).first():
        return _errore("Username già in uso. Scegline un altro.")

    if len(password) < 6:
        return _errore("La password deve essere di almeno 6 caratteri.")

    n_collab = db.query(Utente).filter(Utente.titolare_id == invito.titolare_id).count()
    max_c = max_collaboratori(get_piano(db, invito.titolare_id))
    if max_c is not None and n_collab >= max_c:
        return _errore("Il team ha raggiunto il numero massimo di collaboratori.")

    db.add(Utente(
        username=username,
        password=hash_password(password),
        data_registrazione=oggi,
        attivo=2,
        piano="free",
        titolare_id=invito.titolare_id,
        ruolo="collaboratore",
    ))
    invito.usato = 1
    db.commit()
    return RedirectResponse("/login?invito=1", status_code=303)
