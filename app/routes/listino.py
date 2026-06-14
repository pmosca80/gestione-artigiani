from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, to_float
from app import crud
from app.templates_config import templates

router = APIRouter(prefix="/listino", tags=["listino"])


@router.get("/", response_class=HTMLResponse)
def lista_listino(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    voci = crud.get_listino(db, user_id)
    return templates.TemplateResponse(
        request=request,
        name="listino.html",
        context={"voci": voci},
    )


@router.get("/api/json")
def listino_json(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    voci = crud.get_listino(db, user_id)
    return [
        {
            "id": v.id,
            "descrizione": v.descrizione,
            "unita_misura": v.unita_misura or "",
            "prezzo_unitario": v.prezzo_unitario,
            "categoria": v.categoria or "",
        }
        for v in voci
    ]


@router.post("/nuovo")
def nuova_voce(
    request: Request,
    descrizione: str = Form(...),
    unita_misura: str = Form(""),
    prezzo_unitario: str = Form("0"),
    categoria: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.crea_listino_voce(
        db=db,
        utente_id=user_id,
        descrizione=descrizione.strip(),
        unita_misura=unita_misura.strip(),
        prezzo_unitario=to_float(prezzo_unitario),
        categoria=categoria.strip(),
    )
    return RedirectResponse(url="/listino/", status_code=303)


@router.post("/{voce_id}/modifica")
def modifica_voce(
    voce_id: int,
    request: Request,
    descrizione: str = Form(...),
    unita_misura: str = Form(""),
    prezzo_unitario: str = Form("0"),
    categoria: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.aggiorna_listino_voce(
        db=db,
        voce_id=voce_id,
        utente_id=user_id,
        descrizione=descrizione.strip(),
        unita_misura=unita_misura.strip(),
        prezzo_unitario=to_float(prezzo_unitario),
        categoria=categoria.strip(),
    )
    return RedirectResponse(url="/listino/", status_code=303)


@router.post("/{voce_id}/elimina")
def elimina_voce(
    voce_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.elimina_listino_voce(db, voce_id, user_id)
    return RedirectResponse(url="/listino/", status_code=303)
