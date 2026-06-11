from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.services.fatturapa import genera_xml_fatturapa, nome_file_fatturapa

router = APIRouter(prefix="/documenti", tags=["documenti"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def archivio_documenti(request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    documenti = crud.get_documenti_pdf(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="documenti_lista.html",
        context={"documenti": documenti}
    )


@router.get("/lavori/{lavoro_id}/fattura-xml")
def scarica_fattura_xml(
    lavoro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app import crud as _crud

    lavoro = _crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    cliente = lavoro.cliente
    azienda = _crud.get_impostazioni_azienda(db, user_id)

    xml_bytes = genera_xml_fatturapa(lavoro, cliente, azienda)
    filename  = nome_file_fatturapa(azienda, lavoro)

    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{documento_id}/apri")
def apri_documento(documento_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    documento = crud.get_documento_pdf_by_id(db, user_id, documento_id)

    if not documento:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    percorso = Path(documento.percorso_file)

    if not percorso.exists():
        raise HTTPException(status_code=404, detail="File PDF non trovato")

    return FileResponse(
        path=str(percorso),
        media_type="application/pdf",
        filename=documento.nome_file
    )