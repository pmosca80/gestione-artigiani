from pathlib import Path
from datetime import datetime
import io
import re

from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

from app.database import get_db
from app.dependencies import get_current_user, to_float
from app import crud
from app.services.calcoli import calcola_totali_lavoro
from app.models import Materiale, MaterialeUsatoLavoro
from app.logger import get_logger
logger = get_logger("lavori")

def to_float(valore, default=0.0):
    try:
        return float(valore)
    except (ValueError, TypeError):
        return default

router = APIRouter(prefix="/lavori", tags=["lavori"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def lista_lavori(
    request: Request,
    stato: str = "",
    pagamento: str = "",
    cliente_id: int | None = None,
    scaduti: str = "",
    ricerca: str = "",
    ordinamento: str = "recenti",
    pagina: int = 1,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    risultato = crud.get_lavori(
        db=db,
        stato=stato,
        pagamento=pagamento,
        cliente_id=cliente_id,
        scaduti=scaduti,
        ricerca=ricerca,
        ordinamento=ordinamento,
        utente_id=user_id,
        pagina=pagina,
    )

    totali = crud.get_totali_lavori(risultato["items"])

    return templates.TemplateResponse(
        request=request,
        name="lavori_lista.html",
        context={
            "lavori": risultato["items"],           # ← era solo lavori
            "pagina": risultato["pagina"],
            "pagine_totali": risultato["pagine_totali"],
            "totale": risultato["totale"],
            "stato": stato,
            "pagamento": pagamento,
            "scaduti": scaduti,
            "ricerca": ricerca,
            "ordinamento": ordinamento,
            "totali": totali,
            "oggi": datetime.now().strftime("%Y-%m-%d"),
            "cliente_id": cliente_id,
        }
    )


@router.get("/nuovo/{cliente_id}", response_class=HTMLResponse)
def form_lavoro(cliente_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    cliente = crud.get_cliente_by_id(db, cliente_id, user_id)

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    template_preventivi = crud.get_template_preventivi(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="lavoro_nuovo.html",
        context={"cliente": cliente, "template_preventivi": template_preventivi}
    )


@router.post("/nuovo/{cliente_id}")
def crea_lavoro_form(
    request: Request,
    cliente_id: int,
    data_lavoro: str = Form(...),
    titolo: str = Form(...),
    descrizione: str = Form(""),
    stato: str = Form("preventivo"),
    importo_preventivato: str = Form(""),
    importo_consuntivo: str = Form(""),
    note_consuntivo: str = Form(""),
    aliquota_iva: str = Form("22"),
    sconto: str = Form("0"),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    try:
        cliente = crud.get_cliente_by_id(db, cliente_id, user_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente non trovato")

        crud.crea_lavoro(
            db=db,
            cliente_id=cliente_id,
            data_lavoro=data_lavoro,
            titolo=titolo,
            descrizione=descrizione,
            stato=stato,
            importo_preventivato=to_float(importo_preventivato) if importo_preventivato else None,
            importo_consuntivo=to_float(importo_consuntivo) if importo_consuntivo else None,
            aliquota_iva=to_float(aliquota_iva, default=22),
            sconto=to_float(sconto, default=0),
            note_consuntivo=note_consuntivo,
            utente_id=user_id
        )

        return RedirectResponse(url=f"/clienti/{cliente_id}", status_code=303)
    except Exception as e:
        logger.error(f"Errore creazione lavoro | utente {user_id} | {e}")
        raise

@router.get("/nuovo-rapido", response_class=HTMLResponse)
def form_lavoro_rapido(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.models import Cliente
    clienti = (
        db.query(Cliente)
        .filter(Cliente.utente_id == user_id)
        .order_by(Cliente.ragione_sociale, Cliente.cognome, Cliente.nome)
        .all()
    )
    oggi = datetime.now().strftime("%Y-%m-%d")
    return templates.TemplateResponse(
        request=request,
        name="lavoro_nuovo_rapido.html",
        context={"clienti": clienti, "oggi": oggi},
    )


@router.post("/nuovo-rapido")
def crea_lavoro_rapido(
    request: Request,
    cliente_id: int = Form(...),
    titolo: str = Form(...),
    data_lavoro: str = Form(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.models import Cliente
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.utente_id == user_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")
    lavoro = crud.crea_lavoro(
        db=db,
        cliente_id=cliente_id,
        data_lavoro=data_lavoro,
        titolo=titolo,
        descrizione="",
        stato="da_fare",
        importo_preventivato=None,
        importo_consuntivo=None,
        aliquota_iva=22,
        sconto=0,
        note_consuntivo="",
        utente_id=user_id,
    )
    return RedirectResponse(url=f"/lavori/{lavoro.id}", status_code=303)


@router.get("/allegati/archivio", response_class=HTMLResponse)
def archivio_allegati(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    allegati = crud.get_tutti_allegati(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="allegati_archivio.html",
        context={
            "allegati": allegati
        }
    )

@router.get("/agenda/scadenzario", response_class=HTMLResponse)
def agenda_scadenzario(
    request: Request,
    filtro: str = "",
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    agenda = crud.get_agenda_scadenzario(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="agenda_scadenzario.html",
        context={
            "agenda": agenda,
            "filtro": filtro
        }
    )

@router.get("/analisi/economica", response_class=HTMLResponse)
def analisi_economica(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    
    analisi = crud.get_analisi_economica(
        db,
        user_id
    )

    return templates.TemplateResponse(
        request=request,
        name="analisi_economica.html",
        context={
            "analisi": analisi
        }
    )

@router.get("/preventivi/dashboard", response_class=HTMLResponse)
def dashboard_preventivi(
    request: Request,
    filtro: str = "",
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    preventivi = crud.get_dashboard_preventivi(
        db,
        user_id
    )

    lista_preventivi = preventivi["preventivi"]

    if filtro == "creati":
        lista_preventivi = [
            p for p in lista_preventivi
            if p.stato == "preventivo"
        ]

    elif filtro == "inviati":
        lista_preventivi = [
            p for p in lista_preventivi
            if p.stato == "preventivo_inviato"
        ]

    elif filtro == "accettati":
        lista_preventivi = [
            p for p in lista_preventivi
            if p.stato == "preventivo_accettato"
        ]

    totale_filtro = sum(
        p.importo_preventivato or 0
        for p in lista_preventivi
    )

    return templates.TemplateResponse(
        request=request,
        name="preventivi_dashboard.html",
        context={
            "preventivi": preventivi,
            "filtro": filtro,
            "lista_preventivi": lista_preventivi,
            "totale_filtro": totale_filtro,
        }
    )

@router.get("/{lavoro_id}", response_class=HTMLResponse)
def dettaglio_lavoro(
    lavoro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)

    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    materiali_usati = crud.get_materiali_usati_lavoro(
        db,
        user_id,
        lavoro_id
    )

    materiali = crud.get_materiali(db, user_id)
    materiali_dict = {m.id: m for m in materiali}

    pagamenti = crud.get_pagamenti_lavoro(
        db,
        user_id,
        lavoro_id
    )

    foto_lavoro = crud.get_foto_lavoro(
        db,
        user_id,
        lavoro_id
    )

    percentuale_incassata = 0

    if (lavoro.totale_documento or 0) > 0:
        percentuale_incassata = round(
            ((lavoro.importo_pagato or 0) / lavoro.totale_documento) * 100,
            1
        )

    documenti_pdf = crud.get_documenti_pdf_by_lavoro(
        db,
        user_id,
        lavoro_id
    )

    costo_materiali = lavoro.totale_materiali or 0
    costo_manodopera = lavoro.totale_manodopera or 0

    costo_totale = costo_materiali + costo_manodopera

    totale_documento = lavoro.totale_documento or 0

    utile_lordo = lavoro.margine or 0

    margine_percentuale = 0

    if totale_documento > 0:
        margine_percentuale = round(
            (utile_lordo / totale_documento) * 100,
            1
        )

    allegati_lavoro = crud.get_allegati_lavoro(
        db,
        user_id,
        lavoro_id
    )

    fattura_emessa = (
        lavoro.fatture_emesse[0]
        if lavoro.fatture_emesse else None
    )

    voci_preventivo = crud.get_voci_preventivo(db, user_id, lavoro_id)

    return templates.TemplateResponse(
        request=request,
        name="lavoro_dettaglio.html",
        context={
            "lavoro": lavoro,
            "materiali_usati": materiali_usati,
            "materiali_dict": materiali_dict,
            "pagamenti": pagamenti,
            "percentuale_incassata": percentuale_incassata,
            "foto_lavoro": foto_lavoro,
            "documenti_pdf": documenti_pdf,
            "costo_materiali": costo_materiali,
            "costo_manodopera": costo_manodopera,
            "costo_totale": costo_totale,
            "utile_lordo": utile_lordo,
            "margine_percentuale": margine_percentuale,
            "today": datetime.now().strftime("%Y-%m-%d"),
            "allegati_lavoro": allegati_lavoro,
            "fattura_emessa": fattura_emessa,
            "voci_preventivo": voci_preventivo,
        }
    )

@router.get("/{lavoro_id}/modifica", response_class=HTMLResponse)
def form_modifica_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):
   
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)

    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    foto_lavoro = crud.get_foto_lavoro(db, user_id, lavoro_id)

    return templates.TemplateResponse(
        request=request,
        name="lavoro_modifica.html",
        context={
            "lavoro": lavoro,
            "foto_lavoro": foto_lavoro
    }
)

@router.post("/{lavoro_id}/foto")
async def carica_foto_lavoro(
    lavoro_id: int,
    request: Request,
    foto: UploadFile = File(...),
    descrizione: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    uploads_dir = Path("uploads") / "lavori" / str(lavoro_id)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    nome_originale = foto.filename or "foto.jpg"
    estensione = Path(nome_originale).suffix.lower()

    if estensione not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Formato immagine non valido")

    nome_file = f"lavoro_{lavoro_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{estensione}"
    percorso_file = uploads_dir / nome_file

    contenuto = await foto.read()

    with open(percorso_file, "wb") as f:
        f.write(contenuto)

    crud.salva_foto_lavoro(
        db=db,
        utente_id=user_id,
        lavoro_id=lavoro_id,
        nome_file=nome_file,
        percorso_file=str(percorso_file),
        descrizione=descrizione
    )



    return RedirectResponse(url=f"/lavori/{lavoro_id}", status_code=303)


@router.post("/{lavoro_id}/foto/{foto_id}/elimina")
def elimina_foto(
    lavoro_id: int,
    foto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.elimina_foto_lavoro(db, foto_id, user_id)
    return RedirectResponse(url=f"/lavori/{lavoro_id}", status_code=303)


@router.post("/{lavoro_id}/allegati")
async def carica_allegato_lavoro(
    lavoro_id: int,
    request: Request,
    allegato: UploadFile = File(...),
    descrizione: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    uploads_dir = Path("uploads") / "allegati" / str(lavoro_id)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    nome_originale = allegato.filename or "allegato"
    estensione = Path(nome_originale).suffix.lower()

    estensioni_permesse = [
        ".pdf", ".jpg", ".jpeg", ".png", ".webp",
        ".doc", ".docx", ".xls", ".xlsx"
    ]

    if estensione not in estensioni_permesse:
        raise HTTPException(status_code=400, detail="Formato allegato non valido")

    nome_file = f"allegato_{lavoro_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{estensione}"
    percorso_file = uploads_dir / nome_file

    contenuto = await allegato.read()

    with open(percorso_file, "wb") as f:
        f.write(contenuto)

    crud.salva_allegato_lavoro(
        db=db,
        utente_id=user_id,
        lavoro_id=lavoro_id,
        nome_file=nome_file,
        percorso_file=str(percorso_file),
        tipo_file=estensione,
        descrizione=descrizione
    )

    return RedirectResponse(url=f"/lavori/{lavoro_id}", status_code=303)

@router.post("/{lavoro_id}/modifica")
def modifica_lavoro(
    request: Request,
    lavoro_id: int,
    data_lavoro: str = Form(...),
    titolo: str = Form(...),
    descrizione: str = Form(""),
    stato: str = Form(...),
    importo_preventivato: str = Form(""),
    importo_consuntivo: str = Form(""),
    ore_lavoro: str = Form("0"),
    costo_orario: str = Form("0"),
    aliquota_iva: str = Form("22"),
    sconto: str = Form("0"),
    data_scadenza_pagamento: str = Form(""),
    note_consuntivo: str = Form(""),
    numero_fattura: str = Form(""),
    data_fattura: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    try:
        lavoro_esistente = crud.get_lavoro_by_id(db, lavoro_id, user_id)
        if not lavoro_esistente:
            raise HTTPException(status_code=404, detail="Lavoro non trovato")

        lavoro = crud.aggiorna_lavoro(
            db=db,
            lavoro_id=lavoro_id,
            data_lavoro=data_lavoro,
            titolo=titolo,
            descrizione=descrizione,
            stato=stato,
            importo_preventivato=to_float(importo_preventivato) if importo_preventivato else None,
            importo_consuntivo=to_float(importo_consuntivo) if importo_consuntivo else None,
            ore_lavoro=to_float(ore_lavoro),
            costo_orario=to_float(costo_orario),
            aliquota_iva=to_float(aliquota_iva, default=22),
            sconto=to_float(sconto),
            utente_id=user_id,
            data_scadenza_pagamento=data_scadenza_pagamento,
            note_consuntivo=note_consuntivo,
            numero_fattura=int(numero_fattura) if numero_fattura.strip() else None,
            data_fattura=data_fattura,
        )

        calcola_totali_lavoro(db, lavoro_id)

        return RedirectResponse(url=f"/clienti/{lavoro.cliente_id}", status_code=303)

    except Exception as e:
        logger.error(f"Errore creazione lavoro | utente {user_id} | {e}")
        raise

@router.post("/{lavoro_id}/elimina")
def elimina_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):
    
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)

    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    cliente_id = lavoro.cliente_id
    crud.elimina_lavoro(db, lavoro_id)

    return RedirectResponse(url=f"/clienti/{cliente_id}", status_code=303)


@router.get("/{lavoro_id}/voci", response_class=HTMLResponse)
def form_voci_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")
    voci = crud.get_voci_preventivo(db, user_id, lavoro_id)
    totale_voci = sum((v.quantita or 0) * (v.prezzo_unitario or 0) for v in voci)
    return templates.TemplateResponse(request=request, name="lavoro_voci.html", context={
        "lavoro": lavoro, "voci": voci, "totale_voci": totale_voci,
    })

@router.post("/{lavoro_id}/voci")
def aggiungi_voce_lavoro(
    lavoro_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
    descrizione: str = Form(...),
    quantita: float = Form(1),
    unita_misura: str = Form(""),
    prezzo_unitario: float = Form(0),
):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")
    crud.crea_voce_preventivo(db, user_id, lavoro_id, descrizione, quantita, unita_misura, prezzo_unitario)
    return RedirectResponse(url=f"/lavori/{lavoro_id}/voci", status_code=303)

@router.post("/voci-preventivo/{voce_id}/elimina")
def elimina_voce_preventivo(voce_id: int, db: Session = Depends(get_db), user_id: int = Depends(get_current_user)):
    voce = crud.get_voce_preventivo(db, voce_id, user_id)
    lavoro_id = voce.lavoro_id if voce else None
    crud.elimina_voce_preventivo(db, voce_id, user_id)
    if lavoro_id:
        return RedirectResponse(url=f"/lavori/{lavoro_id}/voci", status_code=303)
    return RedirectResponse(url="/lavori/", status_code=303)


@router.get("/{lavoro_id}/materiali", response_class=HTMLResponse)
def form_materiali_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    materiali = crud.get_materiali(db, user_id)
    materiali_usati = crud.get_materiali_usati_lavoro(db, user_id, lavoro_id)
    materiali_dict = {m.id: m for m in materiali}

    totale_materiali = crud.calcola_totale_materiali_lavoro(db, user_id, lavoro_id)
    carichi_disponibili = crud.get_tutti_carichi_disponibili(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="lavoro_materiali.html",
        context={
            "lavoro": lavoro,
            "materiali": materiali,
            "materiali_usati": materiali_usati,
            "materiali_dict": materiali_dict,
            "totale_materiali": totale_materiali,
            "carichi_disponibili": carichi_disponibili,
        }
    )

def get_carico_by_id(db: Session, utente_id: int, carico_id: int):
    return (
        db.query(CaricoMateriale)
        .filter(
            CaricoMateriale.id == carico_id,
            CaricoMateriale.utente_id == utente_id
        )
        .first()
    )

@router.post("/{lavoro_id}/materiali")
def aggiungi_materiale_lavoro(
    lavoro_id: int,
    request: Request,
    materiale_id: int = Form(...),
    quantita: str = Form(...),
    prezzo_unitario_cliente: str = Form("0"),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    risultato = crud.aggiungi_materiale_a_lavoro(
        db=db,
        utente_id=user_id,
        lavoro_id=lavoro_id,
        materiale_id=materiale_id,
        quantita=to_float(quantita),
        costo_unitario=0,
        prezzo_unitario_cliente=to_float(prezzo_unitario_cliente),
        note=note
    )

    if risultato == "scorta_insufficiente":
        return RedirectResponse(
            url=f"/lavori/{lavoro_id}/materiali?errore=scorta",
            status_code=303
        )

    if risultato is None:
        raise HTTPException(status_code=404, detail="Lavoro o materiale non trovato")

    calcola_totali_lavoro(db, lavoro_id)

    return RedirectResponse(url=f"/lavori/{lavoro_id}/materiali", status_code=303)

@router.post("/materiali-usati/{usato_id}/elimina")
def elimina_materiale_usato(
    usato_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    
    lavoro_id = crud.elimina_materiale_usato_lavoro(
        db=db,
        utente_id=user_id,
        usato_id=usato_id
    )

    if lavoro_id is None:
        raise HTTPException(status_code=404, detail="Materiale usato non trovato")

    calcola_totali_lavoro(db, lavoro_id)

    return RedirectResponse(
        url=f"/lavori/{lavoro_id}/materiali",
        status_code=303
    )

@router.get("/materiali-usati/{usato_id}/modifica", response_class=HTMLResponse)
def modifica_materiale_usato_form(
    usato_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    usato = db.query(MaterialeUsatoLavoro).filter(
        MaterialeUsatoLavoro.id == usato_id,
        MaterialeUsatoLavoro.utente_id == user_id
    ).first()

    if not usato:
        raise HTTPException(status_code=404, detail="Materiale non trovato")

    materiale = db.query(Materiale).filter(
        Materiale.id == usato.materiale_id
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="materiale_usato_modifica.html",
        context={
            "usato": usato,
            "materiale": materiale
        }
    )

@router.post("/materiali-usati/{usato_id}/modifica")
def modifica_materiale_usato(
    usato_id: int,
    request: Request,
    quantita: str = Form(...),
    prezzo_unitario_cliente: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro_id = crud.modifica_materiale_usato_lavoro(
        db=db,
        utente_id=user_id,
        usato_id=usato_id,
        quantita=to_float(quantita),
        prezzo_unitario_cliente=to_float(prezzo_unitario_cliente),
        note=note
    )

    if lavoro_id is None:
        raise HTTPException(status_code=404, detail="Materiale non trovato")

    calcola_totali_lavoro(db, lavoro_id)

    return RedirectResponse(
        url=f"/lavori/{lavoro_id}/materiali",
        status_code=303
    )

@router.get("/{lavoro_id}/pagamenti", response_class=HTMLResponse)
def pagina_pagamenti_lavoro(
    lavoro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    pagamenti = crud.get_pagamenti_lavoro(db, user_id, lavoro_id)

    return templates.TemplateResponse(
        request=request,
        name="lavoro_pagamenti.html",
        context={
            "lavoro": lavoro,
            "pagamenti": pagamenti,
            "today": datetime.now().strftime("%Y-%m-%d")
        }
    )


@router.post("/{lavoro_id}/pagamenti")
def aggiungi_pagamento_lavoro(
    lavoro_id: int,
    request: Request,
    data_pagamento: str = Form(...),
    importo: str = Form(...),
    metodo: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    risultato = crud.aggiungi_pagamento_lavoro(
        db=db,
        utente_id=user_id,
        lavoro_id=lavoro_id,
        data_pagamento=data_pagamento,
        importo=to_float(importo),
        metodo=metodo,
        note=note
    )

    if risultato is None:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    return RedirectResponse(
        url=f"/lavori/{lavoro_id}/pagamenti",
        status_code=303
    )
@router.post("/pagamenti/{pagamento_id}/elimina")
def elimina_pagamento(
    pagamento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro_id = crud.elimina_pagamento_lavoro(
        db,
        user_id,
        pagamento_id
    )

    if not lavoro_id:
        raise HTTPException(status_code=404, detail="Pagamento non trovato")

    return RedirectResponse(
        url=f"/lavori/{lavoro_id}/pagamenti",
        status_code=303
    )
@router.get("/pagamenti/{pagamento_id}/ricevuta")
def genera_ricevuta_pagamento(
    pagamento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    pagamento = crud.get_pagamento_lavoro_by_id(db, user_id, pagamento_id)
    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento non trovato")

    lavoro = crud.get_lavoro_by_id(db, pagamento.lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    cliente = lavoro.cliente
    azienda = crud.get_impostazioni_azienda(db, user_id)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"<b>{azienda.nome_azienda or 'La tua azienda'}</b>", styles["Title"]))
    elements.append(Paragraph(f"P.IVA: {azienda.partita_iva or ''}", styles["Normal"]))
    elements.append(Paragraph(f"Indirizzo: {azienda.indirizzo or ''}", styles["Normal"]))
    elements.append(Paragraph(f"Telefono: {azienda.telefono or ''} - Email: {azienda.email or ''}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    numero_ricevuta = pagamento.numero_ricevuta or pagamento.id

    elements.append(
        Paragraph(
            f"<b>RICEVUTA DI PAGAMENTO N. {numero_ricevuta:04d}</b>",
            styles["Heading1"]
        )
    )
    elements.append(Spacer(1, 16))

    elements.append(
        Paragraph(
            f"Ricevuta relativa al lavoro/documento: <b>{lavoro.titolo}</b>",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"ID lavoro: {lavoro.id}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Dati cliente</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Cliente: {cliente.nome} {cliente.cognome}", styles["Normal"]))
    elements.append(Paragraph(f"Telefono: {cliente.telefono or ''}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Dati lavoro</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Lavoro: {lavoro.titolo}", styles["Normal"]))
    elements.append(Paragraph(f"Data lavoro: {lavoro.data_lavoro}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    tabella = Table(
        [
            ["Voce", "Dettaglio"],
            ["Data pagamento", pagamento.data_pagamento],
            ["Importo pagato", f"EUR {(pagamento.importo or 0):.2f}"],
            ["Metodo", pagamento.metodo or "-"],
            ["Note", pagamento.note or "-"],
            ["Totale documento", f"EUR {(lavoro.totale_documento or 0):.2f}"],
            ["Totale pagato", f"EUR {(lavoro.importo_pagato or 0):.2f}"],
            ["Residuo", f"EUR {(lavoro.residuo_pagamento or 0):.2f}"],
            ["Stato pagamento", lavoro.stato_pagamento or "-"],
        ],
        colWidths=[180, 300]
    )

    tabella.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    elements.append(tabella)

    elements.append(Spacer(1, 18))

    elements.append(
        Paragraph(
            "La presente ricevuta attesta il pagamento indicato e non sostituisce il documento completo del lavoro.",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Firma cliente: ________________________________", styles["Normal"]))
    elements.append(Spacer(1, 14))
    elements.append(Paragraph("Firma operatore: ______________________________", styles["Normal"]))

    doc.build(elements)

    pdf_bytes = buffer.getvalue()

    filename = f"ricevuta_{numero_ricevuta:04d}_lavoro_{lavoro.id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )

@router.get("/{lavoro_id}/pdf")
def genera_pdf_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user),):

    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    cliente = lavoro.cliente
    azienda = crud.get_impostazioni_azienda(db, user_id)
    numero_pdf = crud.genera_numero_pdf(db, user_id)

    materiali_usati = crud.get_materiali_usati_lavoro(db, user_id, lavoro_id)
    materiali_magazzino = crud.get_materiali(db, user_id)
    materiali_dict = {m.id: m for m in materiali_magazzino}
    foto_lavoro = crud.get_foto_lavoro(db, user_id, lavoro_id)
    pagamenti_lavoro = crud.get_pagamenti_lavoro(db, user_id, lavoro_id)
    voci_preventivo = crud.get_voci_preventivo(db, user_id, lavoro_id)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    elements = []

    from reportlab.platypus import Image as RLImage
    from pathlib import Path

    if azienda and azienda.logo_path:
        logo_file = Path(azienda.logo_path)
        if logo_file.exists():
            logo = RLImage(str(logo_file), width=120, height=60)
            logo.hAlign = "LEFT"
            elements.append(logo)
            elements.append(Spacer(1, 8))

    # AZIENDA
    elements.append(Paragraph(f"<b>{azienda.nome_azienda or 'La tua azienda'}</b>", styles["Title"]))
    elements.append(Paragraph(f"P.IVA: {azienda.partita_iva or ''}", styles["Normal"]))
    elements.append(Paragraph(f"Indirizzo: {azienda.indirizzo or ''}", styles["Normal"]))
    elements.append(Paragraph(f"Telefono: {azienda.telefono or ''} - Email: {azienda.email or ''}", styles["Normal"]))
    elements.append(Spacer(1, 18))

    # TITOLO DOCUMENTO
    tipo_documento = "DOCUMENTO"

    if lavoro.stato in [
        "preventivo",
        "preventivo_inviato",
        "preventivo_accettato"
    ]:
        tipo_documento = "PREVENTIVO"

    elif lavoro.stato == "completato":
        tipo_documento = "CONSUNTIVO"

    elements.append(
        Paragraph(
            f"{tipo_documento} N. {numero_pdf:04d}",
            styles["Heading1"]
        )
    )

    # CLIENTE
    elements.append(Paragraph("<b>Dati cliente</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Cliente: {cliente.nome} {cliente.cognome}", styles["Normal"]))
    elements.append(Paragraph(f"Telefono: {cliente.telefono or ''}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # LAVORO
    elements.append(Paragraph("<b>Dati lavoro</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Titolo: {lavoro.titolo}", styles["Normal"]))
    elements.append(Paragraph(f"Data lavoro: {lavoro.data_lavoro}", styles["Normal"]))
    elements.append(Paragraph(f"Stato: {lavoro.stato}", styles["Normal"]))
    elements.append(Spacer(1, 8))

    if lavoro.descrizione:
        elements.append(Paragraph(f"<b>Descrizione:</b> {lavoro.descrizione}", styles["Normal"]))
        elements.append(Spacer(1, 12))

    # VOCI PREVENTIVO (se presenti)
    if voci_preventivo:
        elements.append(Paragraph("<b>Voci preventivo</b>", styles["Heading2"]))
        righe_voci = [["Descrizione", "Qtà", "U.M.", "Prezzo unit.", "Totale"]]
        totale_voci_pdf = 0
        for v in voci_preventivo:
            tot_riga = (v.quantita or 0) * (v.prezzo_unitario or 0)
            totale_voci_pdf += tot_riga
            righe_voci.append([
                v.descrizione,
                f"{v.quantita:g}",
                v.unita_misura or "",
                f"EUR {(v.prezzo_unitario or 0):.2f}",
                f"EUR {tot_riga:.2f}",
            ])
        righe_voci.append(["", "", "", "<b>Totale voci</b>", f"<b>EUR {totale_voci_pdf:.2f}</b>"])
        tabella_voci = Table(righe_voci, colWidths=[200, 40, 40, 90, 80])
        tabella_voci.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 1), (-1, -2), colors.whitesmoke),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f9ff")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))
        elements.append(tabella_voci)
        elements.append(Spacer(1, 16))

    # PARTE ECONOMICA
    preventivo = lavoro.importo_preventivato or 0
    consuntivo = lavoro.importo_consuntivo or 0
    aliquota_iva = lavoro.aliquota_iva or 0
    sconto = lavoro.sconto or 0
    totale_iva = lavoro.totale_iva or 0
    totale_documento = lavoro.totale_documento or 0
    importo_pagato = lavoro.importo_pagato or 0
    residuo = lavoro.residuo_pagamento or 0

    elements.append(Paragraph("<b>Parte economica</b>", styles["Heading2"]))

    economica = [
        ["Voce", "Importo"],
        ["Preventivo", f"EUR {preventivo:.2f}"],
        ["Imponibile / consuntivo", f"EUR {consuntivo:.2f}"],
        [f"IVA {aliquota_iva:.2f}%", f"EUR {totale_iva:.2f}"],
        ["Sconto", f"EUR {sconto:.2f}"],
        ["Totale documento", f"EUR {totale_documento:.2f}"],
        ["Importo pagato", f"EUR {importo_pagato:.2f}"],
        ["Residuo pagamento", f"EUR {residuo:.2f}"],
    ]

    tabella_economica = Table(economica, colWidths=[250, 180])
    tabella_economica.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    elements.append(tabella_economica)
    elements.append(Spacer(1, 16))

    if lavoro.numero_preventivo:
        elements.append(
            Paragraph(
                f"<b>Numero preventivo:</b> {lavoro.numero_preventivo}",
                styles["Normal"]
            )
        )

        elements.append(Spacer(1, 8))

    if lavoro.data_accettazione_preventivo:
        elements.append(
            Paragraph(
                f"<b>Data accettazione preventivo:</b> {lavoro.data_accettazione_preventivo}",
                styles["Normal"]
            )
        )

        elements.append(Spacer(1, 8))

    if lavoro.stato_pagamento == "pagato":
        stato_pagamento_testo = "PAGATO"
    elif lavoro.stato_pagamento == "acconto":
        stato_pagamento_testo = "PAGAMENTO PARZIALE"
    else:
        stato_pagamento_testo = "DA PAGARE"

    elements.append(
        Paragraph(
            f"<b>Stato pagamento:</b> {stato_pagamento_testo}",
            styles["Normal"]
        )
    )

    if lavoro.data_scadenza_pagamento:
        elements.append(
            Paragraph(
                f"<b>Scadenza pagamento:</b> {lavoro.data_scadenza_pagamento}",
                styles["Normal"]
            )
        )

    elements.append(Spacer(1, 16))

    # MATERIALI USATI
    elements.append(Paragraph("<b>Materiali usati</b>", styles["Heading2"]))

    if materiali_usati:
        righe_materiali = [["Materiale", "Quantità", "Prezzo unitario", "Totale", "Note"]]

        totale_materiali_cliente = 0

        for usato in materiali_usati:
            materiale = materiali_dict.get(usato.materiale_id)

            nome_materiale = materiale.nome if materiale else "Materiale non trovato"
            unita = materiale.unita_misura if materiale else ""

            prezzo_cliente = usato.prezzo_unitario_cliente or 0
            totale_riga = (usato.quantita or 0) * prezzo_cliente
            totale_materiali_cliente += totale_riga

            righe_materiali.append([
                nome_materiale,
                f"{usato.quantita} {unita}",
                f"EUR {prezzo_cliente:.2f}",
                f"EUR {totale_riga:.2f}",
                usato.note or ""
            ])

        tabella_materiali = Table(
            righe_materiali,
            colWidths=[150, 80, 90, 90, 120]
        )

        tabella_materiali.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (2, 1), (3, -1), "RIGHT"),
        ]))

        elements.append(tabella_materiali)
        elements.append(Spacer(1, 10))

        elements.append(Paragraph(f"<b>Totale materiali: EUR {totale_materiali_cliente:.2f}</b>", styles["Normal"]))
        elements.append(Paragraph(f"<b>Totale manodopera: EUR {(lavoro.totale_manodopera or 0):.2f}</b>", styles["Normal"]))
        elements.append(Paragraph(f"<b>Imponibile totale: EUR {(lavoro.importo_consuntivo or 0):.2f}</b>", styles["Normal"]))

    else:
        elements.append(Paragraph("Nessun materiale associato al lavoro.", styles["Normal"]))

    elements.append(Spacer(1, 16))

    # STORICO PAGAMENTI
    elements.append(Paragraph("<b>Storico pagamenti</b>", styles["Heading2"]))

    if pagamenti_lavoro:
        righe_pagamenti = [["Data", "Importo", "Metodo", "Note"]]

        for pagamento in pagamenti_lavoro:
            righe_pagamenti.append([
                pagamento.data_pagamento,
                f"EUR {(pagamento.importo or 0):.2f}",
                pagamento.metodo or "",
                pagamento.note or ""
            ])

        tabella_pagamenti = Table(
            righe_pagamenti,
            colWidths=[90, 90, 90, 230]
        )

        tabella_pagamenti.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ]))

        elements.append(tabella_pagamenti)

    else:
        elements.append(Paragraph("Nessun pagamento registrato.", styles["Normal"]))

    elements.append(Spacer(1, 18))

    # NOTE FINALI
    if lavoro.note_consuntivo:
        elements.append(Paragraph("<b>Note finali</b>", styles["Heading2"]))
        elements.append(Paragraph(lavoro.note_consuntivo, styles["Normal"]))
        elements.append(Spacer(1, 18))

    # FOTO
    if foto_lavoro:
        elements.append(Paragraph("<b>Foto lavoro</b>", styles["Heading2"]))
        elements.append(Spacer(1, 8))

        for foto in foto_lavoro:
            percorso = Path(foto.percorso_file)

            if percorso.exists():
                if foto.descrizione:
                    elements.append(Paragraph(f"<b>{foto.descrizione}</b>", styles["Normal"]))
                    elements.append(Spacer(1, 4))

                img = Image(str(percorso))
                img._restrictSize(420, 300)
                elements.append(img)
                elements.append(Spacer(1, 12))

    # FIRME
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Firma cliente: ________________________________", styles["Normal"]))
    elements.append(Spacer(1, 14))
    elements.append(Paragraph("Firma operatore: ______________________________", styles["Normal"]))

    doc.build(elements)

    pdf_bytes = buffer.getvalue()

    pdf_dir = Path("pdf")
    pdf_dir.mkdir(exist_ok=True)

    nome_azienda = azienda.nome_azienda or "azienda"
    nome_azienda = re.sub(r"[^a-zA-Z0-9_-]", "_", nome_azienda)

    filename = f"{nome_azienda}_{numero_pdf:04d}_lavoro_{lavoro.id}.pdf"
    filepath = pdf_dir / filename

    with open(filepath, "wb") as f:
        f.write(pdf_bytes)

    crud.salva_documento_pdf(
        db=db,
        utente_id=user_id,
        lavoro_id=lavoro.id,
        numero=numero_pdf,
        nome_file=filename,
        percorso_file=str(filepath)
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )
@router.post("/allegati/{allegato_id}/elimina")
def elimina_allegato_lavoro(
    allegato_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    allegato = crud.get_allegato_by_id(
        db,
        allegato_id,
        user_id
    )

    if not allegato:
        raise HTTPException(
            status_code=404,
            detail="Allegato non trovato"
        )

    lavoro_id = allegato.lavoro_id

    crud.elimina_allegato(
        db,
        allegato_id,
        user_id
    )

    return RedirectResponse(
        url=f"/lavori/{lavoro_id}",
        status_code=303
    )
@router.post("/{lavoro_id}/converti")
def converti_preventivo(
    lavoro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro = crud.get_lavoro_by_id(
        db,
        lavoro_id,
        user_id
    )

    if not lavoro:
        raise HTTPException(
            status_code=404,
            detail="Lavoro non trovato"
        )

    lavoro.stato = "da_fare"
    lavoro.data_accettazione_preventivo = datetime.now().strftime("%Y-%m-%d")

    db.commit()

    return RedirectResponse(
        url=f"/lavori/{lavoro_id}",
        status_code=303
    )
@router.post("/{lavoro_id}/invia-preventivo")
def invia_preventivo(
    lavoro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro = crud.get_lavoro_by_id(
        db,
        lavoro_id,
        user_id
    )

    if not lavoro:
        raise HTTPException(404)

    lavoro.stato = "preventivo_inviato"

    lavoro.data_invio_preventivo = datetime.now().strftime("%Y-%m-%d")

    db.commit()

    return RedirectResponse(
        f"/lavori/{lavoro_id}",
        status_code=303
    )


@router.post("/{lavoro_id}/accetta-preventivo")
def accetta_preventivo(
    lavoro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):

    lavoro = crud.get_lavoro_by_id(
        db,
        lavoro_id,
        user_id
    )

    if not lavoro:
        raise HTTPException(404)

    lavoro.stato = "preventivo_accettato"

    lavoro.data_accettazione_preventivo = datetime.now().strftime("%Y-%m-%d")

    db.commit()

    return RedirectResponse(
        f"/lavori/{lavoro_id}",
        status_code=303
    )