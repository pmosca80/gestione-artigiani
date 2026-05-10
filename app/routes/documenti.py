from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import crud

router = APIRouter(prefix="/documenti", tags=["documenti"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def archivio_documenti(request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    documenti = crud.get_documenti_pdf(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="documenti_lista.html",
        context={"documenti": documenti}
    )


@router.get("/{documento_id}/apri")
def apri_documento(documento_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
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