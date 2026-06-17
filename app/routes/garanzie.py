from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.validators import DESCRIZIONE_MAX, NOTE_MAX, clean

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.models import Lavoro
from app.templates_config import templates

router = APIRouter(prefix="/garanzie", tags=["garanzie"])

DURATE = [6, 12, 24, 36, 48, 60]


def _arricchisci(garanzie):
    oggi = date.today()
    tra_30 = oggi + timedelta(days=30)
    risultati = []
    for g in garanzie:
        try:
            giorni = (g.data_scadenza - oggi).days
        except Exception:
            giorni = None
        risultati.append({"g": g, "giorni": giorni})
    return risultati


@router.get("/", response_class=HTMLResponse)
def lista_garanzie(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    garanzie = crud.get_garanzie(db, user_id)
    dati = _arricchisci(garanzie)
    oggi = date.today()
    tra_30 = oggi + timedelta(days=30)

    n_scadute = sum(1 for d in dati if d["giorni"] is not None and d["giorni"] < 0)
    n_in_scadenza = sum(1 for d in dati if d["giorni"] is not None and 0 <= d["giorni"] <= 30)
    n_attive = sum(1 for d in dati if d["giorni"] is not None and d["giorni"] > 30)

    return templates.TemplateResponse(
        request=request,
        name="garanzie_lista.html",
        context={
            "dati": dati,
            "n_scadute": n_scadute,
            "n_in_scadenza": n_in_scadenza,
            "n_attive": n_attive,
        },
    )


@router.get("/nuova", response_class=HTMLResponse)
def form_nuova_garanzia(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    result = crud.get_clienti(db, utente_id=user_id, per_pagina=500)
    clienti = result.get("items", []) if isinstance(result, dict) else result
    from datetime import date
    return templates.TemplateResponse(
        request=request,
        name="garanzia_form.html",
        context={"clienti": clienti, "durate": DURATE, "oggi": date.today()},
    )


@router.post("/nuova")
def crea_garanzia(
    request: Request,
    cliente_id: int = Form(...),
    lavoro_id: str = Form(""),
    descrizione: str = Form(...),
    data_installazione: str = Form(...),
    durata_mesi: int = Form(24),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    lid = int(lavoro_id) if lavoro_id.strip() else None
    crud.crea_garanzia(
        db=db,
        utente_id=user_id,
        cliente_id=cliente_id,
        lavoro_id=lid,
        descrizione=clean(descrizione, DESCRIZIONE_MAX),
        data_installazione=data_installazione,
        durata_mesi=durata_mesi,
        note=clean(note, NOTE_MAX),
    )
    return RedirectResponse(url="/garanzie/", status_code=303)


@router.post("/{garanzia_id}/elimina")
def elimina_garanzia(
    garanzia_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.elimina_garanzia(db, garanzia_id, user_id)
    return RedirectResponse(url="/garanzie/", status_code=303)


@router.post("/{garanzia_id}/crea-lavoro")
def crea_lavoro_da_garanzia(
    garanzia_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    g = crud.get_garanzia(db, garanzia_id, user_id)
    if not g:
        raise HTTPException(status_code=404)
    lavoro = Lavoro(
        cliente_id=g.cliente_id,
        utente_id=user_id,
        titolo=f"Manutenzione: {g.descrizione}",
        descrizione=f"Manutenzione programmata.\nGaranzia in scadenza: {g.data_scadenza}",
        stato="da_fare",
        priorita="normale",
        data_lavoro=date.today(),
        data_creazione=datetime.now().strftime("%Y-%m-%d"),
    )
    db.add(lavoro)
    db.commit()
    db.refresh(lavoro)
    return RedirectResponse(url=f"/lavori/{lavoro.id}", status_code=303)
