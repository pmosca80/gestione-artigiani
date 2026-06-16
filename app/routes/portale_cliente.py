from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.templates_config import templates

router = APIRouter(tags=["portale_cliente"])


@router.get("/portale/{token}", response_class=HTMLResponse)
def portale_pubblico(token: str, request: Request, db: Session = Depends(get_db)):
    """Pagina pubblica per il cliente — non richiede autenticazione."""
    if crud.is_token_portale_scaduto(db, token):
        return templates.TemplateResponse(
            request=request,
            name="portale_scaduto.html",
            context={},
            status_code=410,
        )
    cliente = crud.get_cliente_by_token_portale(db, token)
    if not cliente:
        raise HTTPException(status_code=404, detail="Portale non trovato o link non valido.")

    azienda = crud.get_impostazioni_azienda(db, cliente.utente_id)

    # Lavori del cliente visibili al portale (solo non annullati)
    from app.models import Lavoro
    lavori = (
        db.query(Lavoro)
        .filter(Lavoro.cliente_id == cliente.id, Lavoro.stato != "annullato")
        .order_by(Lavoro.data_lavoro.desc())
        .all()
    )

    # Rapportini recenti per ogni lavoro (ultimi 5 per lavoro)
    from app.models import RapportinoLavoro, FotoLavoro
    rapportini_per_lavoro = {}
    foto_per_lavoro = {}
    for l in lavori:
        rapp = (
            db.query(RapportinoLavoro)
            .filter(RapportinoLavoro.lavoro_id == l.id)
            .order_by(RapportinoLavoro.data.desc())
            .limit(5)
            .all()
        )
        rapportini_per_lavoro[l.id] = rapp
        foto = (
            db.query(FotoLavoro)
            .filter(FotoLavoro.lavoro_id == l.id)
            .order_by(FotoLavoro.data_creazione.desc())
            .limit(6)
            .all()
        )
        foto_per_lavoro[l.id] = foto

    nome_cliente = (
        cliente.ragione_sociale
        or f"{cliente.nome or ''} {cliente.cognome or ''}".strip()
    )

    return templates.TemplateResponse(request=request, name="portale_cliente.html", context={
        "cliente": cliente,
        "nome_cliente": nome_cliente,
        "azienda": azienda,
        "lavori": lavori,
        "rapportini_per_lavoro": rapportini_per_lavoro,
        "foto_per_lavoro": foto_per_lavoro,
    })


@router.post("/clienti/{cliente_id}/genera-portale")
def genera_portale(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    cliente = crud.genera_token_portale_cliente(db, cliente_id, user_id)
    if not cliente:
        raise HTTPException(status_code=404)
    return RedirectResponse(url=f"/clienti/{cliente_id}", status_code=303)
