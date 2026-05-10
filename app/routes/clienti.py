from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud

router = APIRouter(prefix="/clienti", tags=["clienti"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def lista_clienti(request: Request, cerca: str = "", db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    clienti = crud.get_clienti(db, cerca, user_id)

    return templates.TemplateResponse(
        request=request,
        name="clienti_lista.html",
        context={"clienti": clienti, "cerca": cerca}
    )


@router.get("/nuovo", response_class=HTMLResponse)
def form_cliente(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="cliente_nuovo.html",
        context={}
    )


@router.post("/nuovo")
def crea_cliente_form(
    request: Request,
    nome: str = Form(...),
    cognome: str = Form(...),
    telefono: str = Form(""),
    db: Session = Depends(get_db)
):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    crud.crea_cliente(db, nome, cognome, telefono, user_id)

    return RedirectResponse(url="/clienti", status_code=303)


@router.get("/{cliente_id}", response_class=HTMLResponse)
def dettaglio_cliente(cliente_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    cliente = crud.get_cliente_by_id(db, cliente_id, user_id)

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    lavori = crud.get_lavori_by_cliente(db, cliente_id, user_id)

    return templates.TemplateResponse(
        request=request,
        name="cliente_dettaglio.html",
        context={"cliente": cliente, "lavori": lavori}
    )


@router.get("/{cliente_id}/modifica", response_class=HTMLResponse)
def form_modifica_cliente(cliente_id: int, request: Request, db: Session = Depends(get_db)):
    cliente = crud.get_cliente_by_id(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    return templates.TemplateResponse(
        request=request,
        name="cliente_modifica.html",
        context={"cliente": cliente}
    )


@router.post("/{cliente_id}/modifica")
def modifica_cliente(
    cliente_id: int,
    nome: str = Form(...),
    cognome: str = Form(...),
    telefono: str = Form(""),
    db: Session = Depends(get_db)
):
    cliente = crud.aggiorna_cliente(db, cliente_id, nome, cognome, telefono)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    return RedirectResponse(url=f"/clienti/{cliente_id}", status_code=303)


@router.post("/{cliente_id}/elimina")
def elimina_cliente(cliente_id: int, db: Session = Depends(get_db)):
    risultato = crud.elimina_cliente(db, cliente_id)

    if risultato is None:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    if risultato == "bloccato":
        return RedirectResponse(url=f"/clienti/{cliente_id}?errore=ha_lavori", status_code=303)

    return RedirectResponse(url="/clienti", status_code=303)