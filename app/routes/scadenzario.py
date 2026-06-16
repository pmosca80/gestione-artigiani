from datetime import datetime, date, timedelta

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.templates_config import templates

router = APIRouter(prefix="/scadenzario", tags=["scadenzario"])

TIPI = ["manutenzione", "revisione", "chiamata", "ispezione", "altro"]


@router.get("/manutenzioni", response_class=HTMLResponse)
def lista_promemoria(
    request: Request,
    filtro: str = "attivi",
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    solo_attivi = filtro != "tutti"
    promemoria = crud.get_promemoria(db, user_id, solo_attivi=solo_attivi)
    clienti = crud.get_clienti(db, "", user_id, pagina=1)["items"]
    oggi = date.today()
    tra_30 = oggi + timedelta(days=30)

    return templates.TemplateResponse(request=request, name="scadenzario.html", context={
        "promemoria": promemoria,
        "clienti": clienti,
        "filtro": filtro,
        "oggi": oggi,
        "tra_30": tra_30,
        "tipi": TIPI,
    })


@router.post("/manutenzioni/nuovo")
def nuovo_promemoria(
    request: Request,
    titolo: str = Form(...),
    data_promemoria: str = Form(...),
    tipo: str = Form("manutenzione"),
    note: str = Form(""),
    cliente_id: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    cid = int(cliente_id) if cliente_id.isdigit() else None
    crud.crea_promemoria(
        db=db, utente_id=user_id, titolo=titolo.strip(),
        data_promemoria=data_promemoria, tipo=tipo,
        note=note.strip(), cliente_id=cid,
    )
    return RedirectResponse(url="/scadenzario/manutenzioni", status_code=303)


@router.post("/manutenzioni/{promemoria_id}/completa")
def completa_promemoria(
    promemoria_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.completa_promemoria(db, promemoria_id, user_id)
    return RedirectResponse(url="/scadenzario/manutenzioni", status_code=303)


@router.post("/manutenzioni/{promemoria_id}/elimina")
def elimina_promemoria(
    promemoria_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.elimina_promemoria(db, promemoria_id, user_id)
    return RedirectResponse(url="/scadenzario/manutenzioni", status_code=303)
