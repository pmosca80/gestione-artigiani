from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud

BASE_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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
    if nome_cliente.strip():
        lavoro.firma_nome_cliente = nome_cliente.strip()
    try:
        lavoro.firma_ip = request.client.host
    except Exception:
        pass
    db.commit()
    return RedirectResponse(f"/firma/{token}/ok", status_code=303)


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
