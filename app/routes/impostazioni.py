from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud

router = APIRouter(prefix="/impostazioni", tags=["impostazioni"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/azienda", response_class=HTMLResponse)
def form_impostazioni_azienda(request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    azienda = crud.get_impostazioni_azienda(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="impostazioni_azienda.html",
        context={"azienda": azienda}
    )


@router.post("/azienda")
def salva_impostazioni_azienda(
    request: Request,
    nome_azienda: str = Form(""),
    partita_iva: str = Form(""),
    indirizzo: str = Form(""),
    telefono: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db)
):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    azienda = crud.get_impostazioni_azienda(db, user_id)

    azienda.nome_azienda = nome_azienda
    azienda.partita_iva = partita_iva
    azienda.indirizzo = indirizzo
    azienda.telefono = telefono
    azienda.email = email

    db.commit()

    return RedirectResponse(url="/impostazioni/azienda?salvato=1", status_code=303)