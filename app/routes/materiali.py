from urllib.parse import quote

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.models import Materiale
from app.dependencies import to_float
from app.templates_config import templates
from app.validators import NOME_MAX, CATEGORIA_MAX, UNITA_MISURA_MAX, NOTE_MAX, clean

router = APIRouter(prefix="/materiali", tags=["materiali"])


@router.get("/", response_class=HTMLResponse)
def lista_materiali(request: Request, cerca: str = "", db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):
    
    materiali = crud.get_materiali(db, user_id, cerca)

    return templates.TemplateResponse(
        request=request,
        name="materiali_lista.html",
        context={"materiali": materiali, "cerca": cerca}
    )


@router.get("/nuovo", response_class=HTMLResponse)
def form_materiale(request: Request, user_id: int = Depends(get_current_user)):
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
    prezzo_acquisto_pieno: str = Form("0"),
    prezzo_acquisto_scontato: str = Form("0"),
    prezzo_vendita_default: str = Form("0"),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    crud.crea_materiale(
        db=db,
        utente_id=user_id,
        nome=clean(nome, NOME_MAX),
        categoria=clean(categoria, CATEGORIA_MAX),
        unita_misura=clean(unita_misura, UNITA_MISURA_MAX),
        quantita=to_float(quantita),
        scorta_minima=to_float(scorta_minima),
        prezzo_acquisto_pieno=to_float(prezzo_acquisto_pieno),
        prezzo_acquisto_scontato=to_float(prezzo_acquisto_scontato),
        prezzo_vendita_default=to_float(prezzo_vendita_default),
        note=clean(note, NOTE_MAX),
    )

    return RedirectResponse(url=f"/materiali/?toast={quote('Materiale salvato')}", status_code=303)


@router.get("/lista-acquisti", response_class=HTMLResponse)
def lista_acquisti(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from datetime import date
    tutti = crud.get_materiali(db, user_id, "")
    da_riordinare = []
    for m in tutti:
        if (m.scorta_minima or 0) > 0 and (m.quantita or 0) <= (m.scorta_minima or 0):
            da_ordinare = max(0, (m.scorta_minima or 0) - (m.quantita or 0))
            da_riordinare.append({"m": m, "da_ordinare": da_ordinare})
    da_riordinare.sort(key=lambda x: (x["m"].quantita or 0))
    impostazioni = crud.get_impostazioni_azienda(db, user_id)
    return templates.TemplateResponse(
        request=request,
        name="lista_acquisti.html",
        context={
            "da_riordinare": da_riordinare,
            "impostazioni": impostazioni,
            "oggi": date.today().strftime("%d/%m/%Y"),
        },
    )


@router.get("/{materiale_id}/movimento", response_class=HTMLResponse)
def form_movimento(materiale_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    materiale = db.query(Materiale).filter(
        Materiale.id == materiale_id,
        Materiale.utente_id == user_id
    ).first()

    if not materiale:
        return RedirectResponse(url="/materiali/", status_code=303)

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
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    if tipo not in ("carico", "scarico") or to_float(quantita) <= 0:
        return RedirectResponse(
            url=f"/materiali/{materiale_id}/movimento?errore=quantita",
            status_code=303
        )

    crud.aggiungi_movimento(
        db,
        utente_id=user_id,
        materiale_id=materiale_id,
        tipo=tipo,
        quantita=to_float(quantita),
        note=clean(note, NOTE_MAX),
    )

    return RedirectResponse(url="/materiali", status_code=303)

@router.get("/movimenti/storico", response_class=HTMLResponse)
def storico_movimenti(request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

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
def storico_movimenti_materiale(materiale_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    materiale = db.query(Materiale).filter(
        Materiale.id == materiale_id,
        Materiale.utente_id == user_id
    ).first()

    if not materiale:
        return RedirectResponse(url="/materiali", status_code=303)

    movimenti = crud.get_movimenti_by_materiale(db, user_id, materiale_id)

    carichi = crud.get_tutti_carichi_materiale(db, user_id, materiale_id)

    return templates.TemplateResponse(
        request=request,
        name="movimenti_materiale.html",
        context={
            "materiale": materiale,
            "movimenti": movimenti
        }
    )

@router.get("/{materiale_id}/carico", response_class=HTMLResponse)
def form_carico_materiale(materiale_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    materiale = db.query(Materiale).filter(
        Materiale.id == materiale_id,
        Materiale.utente_id == user_id
    ).first()

    if not materiale:
        return RedirectResponse(url="/materiali/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="materiale_carico.html",
        context={"materiale": materiale}
    )


@router.post("/{materiale_id}/carico")
def salva_carico_materiale(
    materiale_id: int,
    request: Request,
    quantita: str = Form(...),
    prezzo_acquisto: str = Form("0"),
    prezzo_vendita_default: str = Form("0"),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    materiale = db.query(Materiale).filter(
        Materiale.id == materiale_id, Materiale.utente_id == user_id
    ).first()
    if not materiale:
        return RedirectResponse(url="/materiali/", status_code=303)

    if to_float(quantita) <= 0 or to_float(prezzo_acquisto) < 0 or to_float(prezzo_vendita_default) < 0:
        return RedirectResponse(
            url=f"/materiali/{materiale_id}/carico?errore=quantita",
            status_code=303
        )

    pa = to_float(prezzo_acquisto)
    pv = to_float(prezzo_vendita_default)
    # Se il form semplificato non ha inviato i prezzi, usa quelli già salvati sul materiale
    if pa == 0:
        pa = materiale.prezzo_acquisto_scontato or materiale.prezzo_acquisto_pieno or 0
    if pv == 0:
        pv = materiale.prezzo_vendita_default or 0

    crud.crea_carico_materiale(
        db=db,
        utente_id=user_id,
        materiale_id=materiale_id,
        quantita=to_float(quantita),
        prezzo_acquisto=pa,
        prezzo_vendita_default=pv,
        note=note
    )

    return RedirectResponse(url="/materiali/", status_code=303)