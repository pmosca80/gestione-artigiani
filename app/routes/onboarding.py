from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Utente

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def onboarding_page(
    request: Request,
    _: int = Depends(get_current_user),
):
    step = request.session.get("onboarding_step", 1)
    return templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={"step": step},
    )


@router.post("/azienda")
def onboarding_azienda(
    request: Request,
    nome_azienda: str = Form(""),
    partita_iva: str = Form(""),
    telefono: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    if nome_azienda.strip() or partita_iva.strip():
        crud.salva_impostazioni_azienda(
            db=db,
            utente_id=user_id,
            nome_azienda=nome_azienda.strip(),
            partita_iva=partita_iva.strip(),
            telefono=telefono.strip(),
            email="",
            indirizzo="",
        )
    request.session["onboarding_step"] = 2
    return RedirectResponse(url="/onboarding", status_code=303)


@router.post("/cliente")
def onboarding_cliente(
    request: Request,
    nome: str = Form(""),
    cognome: str = Form(""),
    telefono: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    if nome.strip():
        cliente = crud.crea_cliente(db, nome.strip(), cognome.strip(), telefono.strip(), user_id)
        request.session["onboarding_cliente_id"] = cliente.id
    request.session["onboarding_step"] = 3
    return RedirectResponse(url="/onboarding", status_code=303)


@router.post("/lavoro")
def onboarding_lavoro(
    request: Request,
    titolo: str = Form(""),
    descrizione: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    cliente_id = request.session.get("onboarding_cliente_id")
    if titolo.strip() and cliente_id:
        crud.crea_lavoro(
            db=db,
            cliente_id=cliente_id,
            data_lavoro=datetime.now().strftime("%Y-%m-%d"),
            titolo=titolo.strip(),
            descrizione=descrizione.strip(),
            stato="da_fare",
            importo_preventivato=None,
            importo_consuntivo=None,
            aliquota_iva=22.0,
            sconto=0.0,
            note_consuntivo="",
            utente_id=user_id,
        )
    _mark_done(db, user_id)
    _clear_onboarding(request)
    return RedirectResponse(url="/", status_code=303)


@router.get("/salta")
def onboarding_salta(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    _mark_done(db, user_id)
    _clear_onboarding(request)
    return RedirectResponse(url="/", status_code=303)


def _mark_done(db: Session, user_id: int):
    db.query(Utente).filter(Utente.id == user_id).update({"onboarding_done": True})
    db.commit()


def _clear_onboarding(request: Request):
    request.session.pop("onboarding_step", None)
    request.session.pop("onboarding_cliente_id", None)
