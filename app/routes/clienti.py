from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud

router = APIRouter(prefix="/clienti", tags=["clienti"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/", response_class=HTMLResponse)
def lista_clienti(
    request: Request,
    cerca: str = "",
    pagina: int = 1,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    risultato = crud.get_clienti(db, cerca, user_id, pagina=pagina)

    return templates.TemplateResponse(
        request=request,
        name="clienti_lista.html",
        context={
            "clienti": risultato["items"],
            "pagina": risultato["pagina"],
            "pagine_totali": risultato["pagine_totali"],
            "totale": risultato["totale"],
            "cerca": cerca,
        }
    )


@router.get("/nuovo", response_class=HTMLResponse)
def form_cliente(
    request: Request,
    user_id: int = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request=request,
        name="cliente_nuovo.html",
        context={
            "request": request
        }
    )


@router.post("/nuovo")
def crea_cliente_form(
    request: Request,
    nome: str = Form(...),
    cognome: str = Form(...),
    telefono: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.services.piani import puo_aggiungere_cliente
    if not puo_aggiungere_cliente(db, user_id):
        return RedirectResponse(url="/piani?limite=clienti", status_code=303)

    crud.crea_cliente(db, nome, cognome, telefono, user_id)

    return RedirectResponse(url="/clienti", status_code=303)


@router.get("/{cliente_id}", response_class=HTMLResponse)
def dettaglio_cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    cliente = crud.get_cliente_by_id(db, cliente_id, user_id)

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    lavori = crud.get_lavori_by_cliente(db, cliente_id, user_id)

    riepilogo = crud.get_riepilogo_cliente(
        db,
        cliente_id,
        user_id
    )

    documenti_pdf = crud.get_documenti_pdf_by_cliente(
        db,
        user_id,
        cliente_id
    )

    pagamenti_cliente = crud.get_pagamenti_by_cliente(
        db,
        user_id,
        cliente_id
    )

    return templates.TemplateResponse(
        request=request,
        name="cliente_dettaglio.html",
        context={
            "cliente": cliente,
            "lavori": lavori,
            "riepilogo": riepilogo,
            "documenti_pdf": documenti_pdf,
            "pagamenti_cliente": pagamenti_cliente
        }
    )



@router.get("/{cliente_id}/modifica", response_class=HTMLResponse)
def form_modifica_cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    cliente = crud.get_cliente_by_id(db, cliente_id, user_id)

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    return templates.TemplateResponse(
        request=request,
        name="cliente_modifica.html",
        context={"cliente": cliente}
    )


@router.post("/{cliente_id}/modifica")
def modifica_cliente(
    request: Request,
    cliente_id: int,
    tipo_cliente: str = Form("privato"),
    nome: str = Form(""),
    cognome: str = Form(""),
    ragione_sociale: str = Form(""),
    telefono: str = Form(""),
    email: str = Form(""),
    indirizzo: str = Form(""),
    citta: str = Form(""),
    provincia: str = Form(""),
    cap: str = Form(""),
    partita_iva: str = Form(""),
    codice_fiscale: str = Form(""),
    codice_destinatario: str = Form(""),
    pec_destinatario: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    cliente = crud.aggiorna_cliente(
        db=db,
        cliente_id=cliente_id,
        utente_id=user_id,
        tipo_cliente=tipo_cliente,
        nome=nome,
        cognome=cognome,
        ragione_sociale=ragione_sociale,
        telefono=telefono,
        email=email,
        indirizzo=indirizzo,
        citta=citta,
        provincia=provincia,
        cap=cap,
        partita_iva=partita_iva,
        codice_fiscale=codice_fiscale,
        codice_destinatario=codice_destinatario,
        pec_destinatario=pec_destinatario,
        note=note,
    )

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    return RedirectResponse(url=f"/clienti/{cliente_id}", status_code=303)


@router.post("/{cliente_id}/elimina")
def elimina_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    risultato = crud.elimina_cliente(db, cliente_id, user_id)

    if risultato is None:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    if risultato == "bloccato":
        return RedirectResponse(
            url=f"/clienti/{cliente_id}?errore=ha_lavori",
            status_code=303
        )

    return RedirectResponse(url="/clienti", status_code=303)