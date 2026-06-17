from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, scope_collaboratore
from app import crud
from app.limiter import user_limiter
from app.templates_config import templates
from app.validators import (
    NOME_MAX, RAGIONE_SOCIALE_MAX, TELEFONO_MAX, EMAIL_MAX,
    INDIRIZZO_MAX, CITTA_MAX, PROVINCIA_MAX, CAP_MAX,
    PARTITA_IVA_MAX, CODICE_FISCALE_MAX, CODICE_DEST_MAX, PEC_MAX, NOTE_MAX, clean,
)

router = APIRouter(prefix="/clienti", tags=["clienti"])

@router.get("/", response_class=HTMLResponse)
def lista_clienti(
    request: Request,
    cerca: str = "",
    pagina: int = 1,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    risultato = crud.get_clienti(db, cerca, user_id, pagina=pagina, assegnato_a_id=scope_collaboratore(request, db))

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
@user_limiter.limit("20/minute")
def crea_cliente_form(
    request: Request,
    nome: str = Form(..., max_length=NOME_MAX),
    cognome: str = Form(..., max_length=NOME_MAX),
    telefono: str = Form("", max_length=TELEFONO_MAX),
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

    cliente = crud.get_cliente_by_id(db, cliente_id, user_id, assegnato_a_id=scope_collaboratore(request, db))

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
    cliente = crud.get_cliente_by_id(db, cliente_id, user_id, assegnato_a_id=scope_collaboratore(request, db))

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
    tipo_cliente: str = Form("privato", max_length=20),
    nome: str = Form("", max_length=NOME_MAX),
    cognome: str = Form("", max_length=NOME_MAX),
    ragione_sociale: str = Form("", max_length=RAGIONE_SOCIALE_MAX),
    telefono: str = Form("", max_length=TELEFONO_MAX),
    email: str = Form("", max_length=EMAIL_MAX),
    indirizzo: str = Form("", max_length=INDIRIZZO_MAX),
    citta: str = Form("", max_length=CITTA_MAX),
    provincia: str = Form("", max_length=PROVINCIA_MAX),
    cap: str = Form("", max_length=CAP_MAX),
    partita_iva: str = Form("", max_length=PARTITA_IVA_MAX),
    codice_fiscale: str = Form("", max_length=CODICE_FISCALE_MAX),
    codice_destinatario: str = Form("", max_length=CODICE_DEST_MAX),
    pec_destinatario: str = Form("", max_length=PEC_MAX),
    note: str = Form("", max_length=NOTE_MAX),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    esistente = crud.get_cliente_by_id(db, cliente_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    if not esistente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

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
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    esistente = crud.get_cliente_by_id(db, cliente_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    if not esistente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    risultato = crud.elimina_cliente(db, cliente_id, user_id)

    if risultato is None:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    if risultato == "bloccato":
        return RedirectResponse(
            url=f"/clienti/{cliente_id}?errore=ha_lavori",
            status_code=303
        )

    return RedirectResponse(url="/clienti", status_code=303)