from datetime import datetime, date

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, to_float, scope_collaboratore
from app import crud
from app.templates_config import templates
from app.validators import NOME_MAX, NOTE_MAX, clean

router = APIRouter(tags=["timesheet"])


@router.get("/lavori/{lavoro_id}/timesheet", response_class=HTMLResponse)
def lista_timesheet(lavoro_id: int, request: Request,
                    db: Session = Depends(get_db),
                    user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    if not lavoro:
        raise HTTPException(status_code=404)

    entries = crud.get_timesheet_lavoro(db, user_id, lavoro_id)
    collaboratori = crud.get_collaboratori_utente(db, user_id)

    # Aggregazione per operaio
    per_operaio: dict = {}
    for e in entries:
        nome = e.nome_operaio
        if nome not in per_operaio:
            per_operaio[nome] = {"ore": 0.0, "costo": 0.0}
        per_operaio[nome]["ore"] += e.ore or 0
        per_operaio[nome]["costo"] += (e.ore or 0) * (e.costo_orario or 0)

    totale_ore = sum(e.ore or 0 for e in entries)
    totale_costo = sum((e.ore or 0) * (e.costo_orario or 0) for e in entries)

    return templates.TemplateResponse(request=request, name="lavoro_timesheet.html", context={
        "lavoro": lavoro,
        "entries": entries,
        "collaboratori": collaboratori,
        "per_operaio": per_operaio,
        "totale_ore": round(totale_ore, 2),
        "totale_costo": round(totale_costo, 2),
        "oggi": date.today(),
    })


@router.post("/lavori/{lavoro_id}/timesheet/nuovo")
def nuovo_timesheet(lavoro_id: int, request: Request,
                    nome_operaio: str = Form(...),
                    data: str = Form(...),
                    ore: str = Form("0"),
                    costo_orario: str = Form("0"),
                    note: str = Form(""),
                    db: Session = Depends(get_db),
                    user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    if not lavoro:
        raise HTTPException(status_code=404)
    crud.crea_timesheet_entry(
        db=db, utente_id=user_id, lavoro_id=lavoro_id,
        nome_operaio=clean(nome_operaio, NOME_MAX),
        data=data,
        ore=to_float(ore),
        costo_orario=to_float(costo_orario),
        note=clean(note, NOTE_MAX),
    )
    return RedirectResponse(url=f"/lavori/{lavoro_id}/timesheet", status_code=303)


@router.post("/lavori/{lavoro_id}/timesheet/{entry_id}/elimina")
def elimina_timesheet(lavoro_id: int, entry_id: int, request: Request,
                      db: Session = Depends(get_db),
                      user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    if not lavoro:
        raise HTTPException(status_code=404)
    crud.elimina_timesheet_entry(db, entry_id, user_id)
    return RedirectResponse(url=f"/lavori/{lavoro_id}/timesheet", status_code=303)
