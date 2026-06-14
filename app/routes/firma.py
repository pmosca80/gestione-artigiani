import threading
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud
from app.models import Utente
from app.templates_config import templates

router = APIRouter(prefix="/firma", tags=["firma"])


@router.get("/{token}", response_class=HTMLResponse)
def firma_page(token: str, request: Request, db: Session = Depends(get_db)):
    lavoro = crud.get_lavoro_by_token_firma(db, token)
    if not lavoro:
        return HTMLResponse("<h2>Link non valido o scaduto.</h2>", status_code=404)
    impostazioni = crud.get_impostazioni_azienda(db, lavoro.utente_id)
    voci = crud.get_voci_preventivo(db, lavoro.utente_id, lavoro.id)
    return templates.TemplateResponse(
        request=request,
        name="firma_preventivo.html",
        context={
            "lavoro": lavoro,
            "impostazioni": impostazioni,
            "voci": voci,
        },
    )


@router.post("/{token}/accetta")
def firma_accetta(
    token: str,
    request: Request,
    nome_cliente: str = Form(""),
    db: Session = Depends(get_db),
):
    lavoro = crud.get_lavoro_by_token_firma(db, token)
    if not lavoro:
        return HTMLResponse("<h2>Link non valido.</h2>", status_code=404)
    if lavoro.stato not in ("preventivo", "preventivo_inviato", "preventivo_accettato"):
        return RedirectResponse(f"/firma/{token}/ok", status_code=303)
    if lavoro.stato != "preventivo_accettato":
        lavoro.stato = "preventivo_accettato"
        lavoro.data_accettazione_preventivo = datetime.now().strftime("%Y-%m-%d")
    nome_firmato = nome_cliente.strip() or "il cliente"
    if nome_cliente.strip():
        lavoro.firma_nome_cliente = nome_firmato
    try:
        lavoro.firma_ip = request.client.host
    except Exception:
        pass
    db.commit()

    # Notifica email all'artigiano (fire-and-forget)
    artigiano = db.query(Utente).filter(Utente.id == lavoro.utente_id).first()
    artigiano_email = artigiano.email or artigiano.username if artigiano else None
    if artigiano_email and "@" in artigiano_email:
        impostazioni = crud.get_impostazioni_azienda(db, lavoro.utente_id)
        nome_azienda = (impostazioni.nome_azienda if impostazioni else None) or artigiano.username
        base_url = str(request.base_url).rstrip("/")
        threading.Thread(
            target=_notifica_firma,
            args=(artigiano_email, nome_azienda, lavoro.titolo, nome_firmato,
                  lavoro.importo_preventivato, f"{base_url}/lavori/{lavoro.id}"),
            daemon=True,
        ).start()

    return RedirectResponse(f"/firma/{token}/ok", status_code=303)


def _notifica_firma(artigiano_email, nome_azienda, titolo, nome_cliente_firma, importo, link_lavoro):
    from app.services.email import invia_notifica_firma_preventivo
    invia_notifica_firma_preventivo(
        artigiano_email=artigiano_email,
        nome_azienda=nome_azienda,
        titolo_lavoro=titolo,
        nome_cliente_firma=nome_cliente_firma,
        importo=importo,
        link_lavoro=link_lavoro,
    )


@router.get("/{token}/ok", response_class=HTMLResponse)
def firma_ok(token: str, request: Request, db: Session = Depends(get_db)):
    lavoro = crud.get_lavoro_by_token_firma(db, token)
    if not lavoro:
        return HTMLResponse("<h2>Link non valido.</h2>", status_code=404)
    impostazioni = crud.get_impostazioni_azienda(db, lavoro.utente_id)
    return templates.TemplateResponse(
        request=request,
        name="firma_accettata.html",
        context={"lavoro": lavoro, "impostazioni": impostazioni},
    )
