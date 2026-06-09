from fastapi.responses import FileResponse
from pathlib import Path
from fastapi import UploadFile, File
import shutil
from datetime import datetime
import shutil

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from openpyxl import Workbook

import zipfile

from fastapi import HTTPException
from app.models import Utente

router = APIRouter(prefix="/impostazioni", tags=["impostazioni"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/azienda", response_class=HTMLResponse)
def form_impostazioni_azienda(request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    azienda = crud.get_impostazioni_azienda(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="impostazioni_azienda.html",
        context={"azienda": azienda}
    )


@router.post("/azienda")
def salva_impostazioni_azienda(
    request: Request,
    nome_azienda: str = Form(""),
    partita_iva: str = Form(""),
    indirizzo: str = Form(""),
    telefono: str = Form(""),
    email: str = Form(""),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    logo_path = None

    if logo and logo.filename:
        estensione = Path(logo.filename).suffix.lower()
        if estensione in [".png", ".jpg", ".jpeg"]:
            cartella = Path(f"uploads/loghi/{user_id}")
            cartella.mkdir(parents=True, exist_ok=True)
            percorso = cartella / f"logo{estensione}"
            with open(percorso, "wb") as f:
                shutil.copyfileobj(logo.file, f)
            logo_path = str(percorso)

    crud.salva_impostazioni_azienda(
        db, user_id, nome_azienda, partita_iva, indirizzo, telefono, email, logo_path
    )
    return RedirectResponse(url="/impostazioni/azienda", status_code=303)

@router.get("/backup")
def crea_backup_database(request: Request, user_id: int = Depends(get_current_user)):

    db_path = Path("artigiani.db")

    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database non trovato")

    backup_dir = Path("backup")
    backup_dir.mkdir(exist_ok=True)

    nome_backup = f"backup_artigiani_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = backup_dir / nome_backup

    shutil.copy(db_path, backup_path)

    return FileResponse(
        path=backup_path,
        filename=nome_backup,
        media_type="application/octet-stream"
    )
@router.get("/backup/pagina", response_class=HTMLResponse)
def pagina_backup(request: Request, user_id: int = Depends(get_current_user)):

    backup_dir = Path("backup")

    backup_files = []

    if backup_dir.exists():

        for file in backup_dir.glob("*.db"):

            backup_files.append({
                "nome": file.name,
                "dimensione": round(
                    file.stat().st_size / 1024 / 1024,
                    2
                ),
                "data": datetime.fromtimestamp(
                    file.stat().st_mtime
                )
            })

    backup_files.sort(
        key=lambda x: x["data"],
        reverse=True
    )

    ultimo_backup = None

    if backup_dir.exists():

        files = list(backup_dir.glob("*.db"))

        if files:

            ultimo_file = max(
                files,
                key=lambda f: f.stat().st_mtime
            )

            ultimo_backup = datetime.fromtimestamp(
                ultimo_file.stat().st_mtime
            )

    return templates.TemplateResponse(
        request=request,
        name="backup.html",
        context={
            "ultimo_backup": ultimo_backup,
            "backup_files": backup_files,
        }
    )
@router.get("/backup/completo")
def crea_backup_completo(request: Request, user_id: int = Depends(get_current_user)):

    backup_dir = Path("backup")
    backup_dir.mkdir(exist_ok=True)

    nome_zip = f"backup_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = backup_dir / nome_zip

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:

        db_path = Path("artigiani.db")
        if db_path.exists():
            zipf.write(db_path, arcname="artigiani.db")

        for cartella in ["uploads", "pdf"]:
            cartella_path = Path(cartella)

            if cartella_path.exists():
                for file in cartella_path.rglob("*"):
                    if file.is_file():
                        zipf.write(
                            file,
                            arcname=str(file)
                        )

    return FileResponse(
        path=zip_path,
        filename=nome_zip,
        media_type="application/zip"
    )
@router.get("/export/clienti")
def esporta_clienti_excel(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    clienti = crud.get_clienti(db, utente_id=user_id)["items"]

    export_dir = Path("export")
    export_dir.mkdir(exist_ok=True)

    nome_file = f"clienti_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    file_path = export_dir / nome_file

    wb = Workbook()
    ws = wb.active
    ws.title = "Clienti"

    ws.append([
        "ID",
        "Tipo",
        "Nome",
        "Cognome",
        "Ragione sociale",
        "Telefono",
        "Email",
        "Indirizzo",
        "Città",
        "Provincia",
        "CAP",
        "Residuo"
    ])

    for cliente in clienti:
        ws.append([
            cliente.id,
            cliente.tipo_cliente,
            cliente.nome,
            cliente.cognome,
            cliente.ragione_sociale,
            cliente.telefono,
            cliente.email,
            cliente.indirizzo,
            cliente.citta,
            cliente.provincia,
            cliente.cap,
            cliente.totale_residuo or 0
        ])

    wb.save(file_path)

    return FileResponse(
        path=file_path,
        filename=nome_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
@router.get("/export/lavori")
def esporta_lavori_excel(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavori = crud.get_lavori(db=db, utente_id=user_id)["items"]

    export_dir = Path("export")
    export_dir.mkdir(exist_ok=True)

    nome_file = f"lavori_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    file_path = export_dir / nome_file

    wb = Workbook()
    ws = wb.active
    ws.title = "Lavori"

    ws.append([
        "ID",
        "Data lavoro",
        "Cliente",
        "Titolo",
        "Stato",
        "Priorità",
        "Preventivo",
        "Totale documento",
        "Pagato",
        "Residuo",
        "Margine",
        "Stato pagamento",
        "Scadenza pagamento"
    ])

    for lavoro in lavori:
        cliente = "-"
        if lavoro.cliente:
            cliente = f"{lavoro.cliente.nome or ''} {lavoro.cliente.cognome or ''}".strip()

        ws.append([
            lavoro.id,
            lavoro.data_lavoro,
            cliente,
            lavoro.titolo,
            lavoro.stato,
            lavoro.priorita,
            lavoro.importo_preventivato or 0,
            lavoro.totale_documento or 0,
            lavoro.importo_pagato or 0,
            lavoro.residuo_pagamento or 0,
            lavoro.margine or 0,
            lavoro.stato_pagamento,
            lavoro.data_scadenza_pagamento or ""
        ])

    wb.save(file_path)

    return FileResponse(
        path=file_path,
        filename=nome_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
@router.get("/export/materiali")
def esporta_materiali_excel(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    materiali = crud.get_materiali(db, user_id)

    export_dir = Path("export")
    export_dir.mkdir(exist_ok=True)

    nome_file = f"materiali_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    file_path = export_dir / nome_file

    wb = Workbook()
    ws = wb.active
    ws.title = "Materiali"

    ws.append([
        "ID",
        "Nome",
        "Categoria",
        "Unità misura",
        "Quantità",
        "Scorta minima",
        "Prezzo acquisto pieno",
        "Prezzo acquisto scontato",
        "Prezzo vendita",
        "Valore magazzino",
        "Note"
    ])

    for materiale in materiali:
        valore_magazzino = (
            (materiale.quantita or 0)
            * (materiale.prezzo_acquisto_scontato or materiale.prezzo_acquisto_pieno or 0)
        )

        ws.append([
            materiale.id,
            materiale.nome,
            materiale.categoria,
            materiale.unita_misura,
            materiale.quantita or 0,
            materiale.scorta_minima or 0,
            materiale.prezzo_acquisto_pieno or 0,
            materiale.prezzo_acquisto_scontato or 0,
            materiale.prezzo_vendita_default or 0,
            valore_magazzino,
            materiale.note or ""
        ])

    wb.save(file_path)

    return FileResponse(
        path=file_path,
        filename=nome_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@router.post("/backup/ripristina")
def ripristina_backup(
    request: Request,
    backup_file: UploadFile = File(...),
    user_id: int = Depends(get_current_user),
):

    if not backup_file.filename.endswith(".db"):
        raise HTTPException(
            status_code=400,
            detail="File non valido"
        )

    db_path = Path("artigiani.db")

    sicurezza_dir = Path("backup")
    sicurezza_dir.mkdir(exist_ok=True)

    # backup automatico prima del ripristino

    backup_sicurezza = (
        sicurezza_dir /
        f"pre_ripristino_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )

    if db_path.exists():
        shutil.copy2(
            db_path,
            backup_sicurezza
        )

    # sostituzione database

    with open(db_path, "wb") as buffer:
        shutil.copyfileobj(
            backup_file.file,
            buffer
        )

    return RedirectResponse(
        url="/impostazioni/backup/pagina",
        status_code=303
    )

@router.get("/backup/download/{filename}")
def download_backup(
    filename: str,
    request: Request,
    user_id: int = Depends(get_current_user),
):
    file_path = Path("backup") / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File non trovato")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )
    
@router.get("/backup/elimina/{filename}")
def elimina_backup(
    filename: str,
    request: Request,
    user_id: int = Depends(get_current_user),
):

    file_path = Path("backup") / filename

    if file_path.exists():
        file_path.unlink()

    return RedirectResponse(
        "/impostazioni/backup/pagina",
        status_code=303
    )

@router.get("/admin", response_class=HTMLResponse)
def pagina_admin(request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user)):
    utente_corrente = db.query(Utente).filter(Utente.id == user_id).first()

    if not utente_corrente or utente_corrente.username != "admin":
        raise HTTPException(status_code=403, detail="Accesso negato")

    utenti = db.query(Utente).all()

    oggi = datetime.now()

    for utente in utenti:
        if utente.data_registrazione:
            try:
                data_reg = datetime.strptime(utente.data_registrazione, "%Y-%m-%d")
                utente.giorni_rimasti = 30 - (oggi - data_reg).days
            except:
                utente.giorni_rimasti = None
        else:
            utente.giorni_rimasti = None

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"utenti": utenti}
    )


@router.post("/admin/attiva/{utente_id}")
def attiva_utente(utente_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user)):
    utente_corrente = db.query(Utente).filter(Utente.id == user_id).first()

    if not utente_corrente or utente_corrente.username != "admin":
        raise HTTPException(status_code=403, detail="Accesso negato")

    utente = db.query(Utente).filter(Utente.id == utente_id).first()
    if utente:
        utente.attivo = 2
        db.commit()

    return RedirectResponse(url="/impostazioni/admin", status_code=303)


@router.post("/admin/disattiva/{utente_id}")
def disattiva_utente(utente_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user)):
    utente_corrente = db.query(Utente).filter(Utente.id == user_id).first()

    if not utente_corrente or utente_corrente.username != "admin":
        raise HTTPException(status_code=403, detail="Accesso negato")

    utente = db.query(Utente).filter(Utente.id == utente_id).first()
    if utente:
        utente.attivo = 0
        db.commit()

    return RedirectResponse(url="/impostazioni/admin", status_code=303)


@router.post("/admin/elimina/{utente_id}")
def elimina_utente(utente_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user)):
    utente_corrente = db.query(Utente).filter(Utente.id == user_id).first()

    if not utente_corrente or utente_corrente.username != "admin":
        raise HTTPException(status_code=403, detail="Accesso negato")

    if utente_id == user_id:
        raise HTTPException(status_code=400, detail="Non puoi eliminare te stesso")

    utente = db.query(Utente).filter(Utente.id == utente_id).first()
    if utente:
        db.delete(utente)
        db.commit()

    return RedirectResponse(url="/impostazioni/admin", status_code=303)
@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={}
    )

@router.post("/onboarding")
def onboarding_salva(
    request: Request,
    nome_azienda: str = Form(...),
    partita_iva: str = Form(""),
    indirizzo: str = Form(""),
    telefono: str = Form(""),
    email: str = Form(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.salva_impostazioni_azienda(
        db, user_id, nome_azienda, partita_iva, indirizzo, telefono, email, None
    )
    return RedirectResponse(url="/", status_code=303)