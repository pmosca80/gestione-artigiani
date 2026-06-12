from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, to_float
from app import crud

router = APIRouter(prefix="/preventivi/template", tags=["preventivi_template"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def lista_template(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    tmpl = crud.get_template_preventivi(db, user_id)
    return templates.TemplateResponse(
        request=request,
        name="preventivi_template_lista.html",
        context={"template_list": tmpl},
    )


@router.get("/nuovo", response_class=HTMLResponse)
def form_nuovo_template(
    request: Request,
    user_id: int = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request=request,
        name="preventivo_template_form.html",
        context={"tmpl": None},
    )


@router.post("/nuovo")
def salva_nuovo_template(
    request: Request,
    nome: str = Form(...),
    titolo: str = Form(""),
    descrizione: str = Form(""),
    importo_preventivato: str = Form("0"),
    aliquota_iva: str = Form("22"),
    sconto: str = Form("0"),
    note_consuntivo: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.crea_template_preventivo(
        db=db,
        utente_id=user_id,
        nome=nome,
        titolo=titolo,
        descrizione=descrizione,
        importo_preventivato=to_float(importo_preventivato),
        aliquota_iva=to_float(aliquota_iva, default=22),
        sconto=to_float(sconto),
        note_consuntivo=note_consuntivo,
    )
    return RedirectResponse(url="/preventivi/template/", status_code=303)


@router.get("/{template_id}/modifica", response_class=HTMLResponse)
def form_modifica_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    tmpl = crud.get_template_preventivo(db, template_id, user_id)
    if not tmpl:
        return RedirectResponse(url="/preventivi/template/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="preventivo_template_form.html",
        context={"tmpl": tmpl},
    )


@router.post("/{template_id}/modifica")
def salva_modifica_template(
    template_id: int,
    request: Request,
    nome: str = Form(...),
    titolo: str = Form(""),
    descrizione: str = Form(""),
    importo_preventivato: str = Form("0"),
    aliquota_iva: str = Form("22"),
    sconto: str = Form("0"),
    note_consuntivo: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.aggiorna_template_preventivo(
        db=db,
        template_id=template_id,
        utente_id=user_id,
        nome=nome,
        titolo=titolo,
        descrizione=descrizione,
        importo_preventivato=to_float(importo_preventivato),
        aliquota_iva=to_float(aliquota_iva, default=22),
        sconto=to_float(sconto),
        note_consuntivo=note_consuntivo,
    )
    return RedirectResponse(url="/preventivi/template/", status_code=303)


@router.post("/{template_id}/elimina")
def elimina_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.elimina_template_preventivo(db, template_id, user_id)
    return RedirectResponse(url="/preventivi/template/", status_code=303)
