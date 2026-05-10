from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud
from app.models import Materiale

router = APIRouter(prefix="/materiali", tags=["materiali"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def lista_materiali(request: Request, cerca: str = "", db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    materiali = crud.get_materiali(db, user_id, cerca)

    return templates.TemplateResponse(
        request=request,
        name="materiali_lista.html",
        context={"materiali": materiali, "cerca": cerca}
    )


@router.get("/nuovo", response_class=HTMLResponse)
def form_materiale(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="materiale_nuovo.html",
        context={}
    )


@router.post("/nuovo")
def crea_materiale_form(
    request: Request,
    nome: str = Form(...),
    categoria: str = Form(""),
    unita_misura: str = Form("pz"),
    quantita: str = Form("0"),
    scorta_minima: str = Form("0"),
    note: str = Form(""),
    db: Session = Depends(get_db)
):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]

    crud.crea_materiale(
        db=db,
        utente_id=user_id,
        nome=nome,
        categoria=categoria,
        unita_misura=unita_misura,
        quantita=float(quantita) if quantita else 0,
        scorta_minima=float(scorta_minima) if scorta_minima else 0,
        note=note
    )

    return RedirectResponse(url="/materiali", status_code=303)

@router.get("/{materiale_id}/movimento", response_class=HTMLResponse)
def form_movimento(materiale_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    materiale = db.query(Materiale).filter(Materiale.id == materiale_id).first()

    return templates.TemplateResponse(
        request=request,
        name="movimento.html",
        context={"materiale": materiale}
    )


@router.post("/{materiale_id}/movimento")
def salva_movimento(
    request: Request,
    materiale_id: int,
    tipo: str = Form(...),
    quantita: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db)
):
    user_id = request.session["user_id"]

    crud.aggiungi_movimento(
        db,
        utente_id=user_id,
        materiale_id=materiale_id,
        tipo=tipo,
        quantita=float(quantita),
        note=note
    )

    return RedirectResponse(url="/materiali", status_code=303)

@router.get("/movimenti/storico", response_class=HTMLResponse)
def storico_movimenti(request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    movimenti = crud.get_movimenti_magazzino(db, user_id)

    materiali = {
        m.id: m for m in crud.get_materiali(db, user_id)
    }

    return templates.TemplateResponse(
        request=request,
        name="movimenti_storico.html",
        context={
            "movimenti": movimenti,
            "materiali": materiali
        }
    )


@router.get("/{materiale_id}/movimenti", response_class=HTMLResponse)
def storico_movimenti_materiale(materiale_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]

    materiale = db.query(Materiale).filter(
        Materiale.id == materiale_id,
        Materiale.utente_id == user_id
    ).first()

    if not materiale:
        return RedirectResponse(url="/materiali", status_code=303)

    movimenti = crud.get_movimenti_by_materiale(db, user_id, materiale_id)

    return templates.TemplateResponse(
        request=request,
        name="movimenti_materiale.html",
        context={
            "materiale": materiale,
            "movimenti": movimenti
        }
    )