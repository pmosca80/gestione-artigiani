from pathlib import Path
import io
import re

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

from app.database import get_db
from app import crud
from app.services.calcoli import calcola_totali_lavoro

router = APIRouter(prefix="/lavori", tags=["lavori"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def lista_lavori(request: Request, stato: str = "", db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    lavori = crud.get_lavori(db, stato, user_id)

    return templates.TemplateResponse(
        request=request,
        name="lavori_lista.html",
        context={"lavori": lavori, "stato": stato}
    )


@router.get("/nuovo/{cliente_id}", response_class=HTMLResponse)
def form_lavoro(cliente_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    cliente = crud.get_cliente_by_id(db, cliente_id, user_id)

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    return templates.TemplateResponse(
        request=request,
        name="lavoro_nuovo.html",
        context={"cliente": cliente}
    )


@router.post("/nuovo/{cliente_id}")
def crea_lavoro_form(
    request: Request,
    cliente_id: int,
    data_lavoro: str = Form(...),
    titolo: str = Form(...),
    descrizione: str = Form(""),
    importo_preventivato: str = Form(""),
    importo_consuntivo: str = Form(""),
    note_consuntivo: str = Form(""),
    db: Session = Depends(get_db)
):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]

    cliente = crud.get_cliente_by_id(db, cliente_id, user_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente non trovato")

    crud.crea_lavoro(
        db=db,
        cliente_id=cliente_id,
        data_lavoro=data_lavoro,
        titolo=titolo,
        descrizione=descrizione,
        importo_preventivato=float(importo_preventivato) if importo_preventivato else None,
        importo_consuntivo=float(importo_consuntivo) if importo_consuntivo else None,
        note_consuntivo=note_consuntivo,
        utente_id=user_id
    )

    return RedirectResponse(url=f"/clienti/{cliente_id}", status_code=303)


@router.get("/{lavoro_id}/modifica", response_class=HTMLResponse)
def form_modifica_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)

    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    return templates.TemplateResponse(
        request=request,
        name="lavoro_modifica.html",
        context={"lavoro": lavoro}
    )


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
    note_consuntivo: str = Form(""),
    db: Session = Depends(get_db)
):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]

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
        importo_preventivato=float(importo_preventivato) if importo_preventivato else None,
        importo_consuntivo=float(importo_consuntivo) if importo_consuntivo else None,
        ore_lavoro=float(ore_lavoro) if ore_lavoro else 0,
        costo_orario=float(costo_orario) if costo_orario else 0,
        note_consuntivo=note_consuntivo
    )

    return RedirectResponse(url=f"/clienti/{lavoro.cliente_id}", status_code=303)

@router.post("/{lavoro_id}/elimina")
def elimina_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)

    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    cliente_id = lavoro.cliente_id
    crud.elimina_lavoro(db, lavoro_id)

    return RedirectResponse(url=f"/clienti/{cliente_id}", status_code=303)


@router.get("/{lavoro_id}/materiali", response_class=HTMLResponse)
def form_materiali_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db)):

    # 🔐 controllo login
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]

    # 📌 recupero lavoro
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    # 📦 materiali disponibili
    materiali = crud.get_materiali(db, user_id)

    # 🧾 materiali usati nel lavoro
    materiali_usati = crud.get_materiali_usati_lavoro(db, user_id, lavoro_id)

    # 🧠 dizionario materiali (per nome/unita)
    materiali_dict = {m.id: m for m in materiali}

    # 💰 totale materiali
    totale_materiali = crud.calcola_totale_materiali_lavoro(db, user_id, lavoro_id)

    return templates.TemplateResponse(
        request=request,
        name="lavoro_materiali.html",
        context={
            "lavoro": lavoro,
            "materiali": materiali,
            "materiali_usati": materiali_usati,
            "materiali_dict": materiali_dict,
            "totale_materiali": totale_materiali
        }
    )


@router.post("/{lavoro_id}/materiali")
def aggiungi_materiale_lavoro(
    lavoro_id: int,
    request: Request,
    materiale_id: int = Form(...),
    quantita: str = Form(...),
    costo_unitario: str = Form("0"),
    note: str = Form(""),
    db: Session = Depends(get_db)
):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]

    risultato = crud.aggiungi_materiale_a_lavoro(
        db=db,
        utente_id=user_id,
        lavoro_id=lavoro_id,
        materiale_id=materiale_id,
        quantita=float(quantita),
        costo_unitario=float(costo_unitario) if costo_unitario else 0,
        note=note
    )

    if risultato == "scorta_insufficiente":
        return RedirectResponse(
            url=f"/lavori/{lavoro_id}/materiali?errore=scorta",
            status_code=303
        )

    if risultato is None:
        raise HTTPException(status_code=404, detail="Lavoro o materiale non trovato")

    # aggiorna automaticamente totale materiali, consuntivo e margine
    calcola_totali_lavoro(db, lavoro_id)

    return RedirectResponse(url=f"/lavori/{lavoro_id}/materiali", status_code=303)

@router.get("/{lavoro_id}/pdf")
def genera_pdf_lavoro(lavoro_id: int, request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]

    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404, detail="Lavoro non trovato")

    cliente = lavoro.cliente

    azienda = crud.get_impostazioni_azienda(db, user_id)
    numero_pdf = crud.genera_numero_pdf(db, user_id)

    materiali_usati = crud.get_materiali_usati_lavoro(db, user_id, lavoro_id)
    materiali_magazzino = crud.get_materiali(db, user_id)
    materiali_dict = {m.id: m for m in materiali_magazzino}
    totale_materiali = crud.calcola_totale_materiali_lavoro(db, user_id, lavoro_id)

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

    # intestazione azienda
    elements.append(Paragraph(f"<b>{azienda.nome_azienda or 'La tua azienda'}</b>", styles["Title"]))
    elements.append(Paragraph(f"P.IVA: {azienda.partita_iva or ''}", styles["Normal"]))
    elements.append(Paragraph(f"Indirizzo: {azienda.indirizzo or ''}", styles["Normal"]))
    elements.append(Paragraph(f"Telefono: {azienda.telefono or ''} - Email: {azienda.email or ''}", styles["Normal"]))
    elements.append(Spacer(1, 18))

    # titolo documento
    elements.append(Paragraph(f"PREVENTIVO / CONSUNTIVO N. {numero_pdf:04d}", styles["Heading1"]))
    elements.append(Spacer(1, 16))

    # dati cliente
    elements.append(Paragraph("<b>Dati cliente</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Cliente: {cliente.nome} {cliente.cognome}", styles["Normal"]))
    elements.append(Paragraph(f"Telefono: {cliente.telefono or ''}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # dati lavoro
    elements.append(Paragraph("<b>Dati lavoro</b>", styles["Heading2"]))
    elements.append(Paragraph(f"Titolo: {lavoro.titolo}", styles["Normal"]))
    elements.append(Paragraph(f"Data lavoro: {lavoro.data_lavoro}", styles["Normal"]))
    elements.append(Paragraph(f"Stato: {lavoro.stato}", styles["Normal"]))
    elements.append(Spacer(1, 8))

    if lavoro.descrizione:
        elements.append(Paragraph(f"<b>Descrizione:</b> {lavoro.descrizione}", styles["Normal"]))
        elements.append(Spacer(1, 12))

    # parte economica
    elements.append(Paragraph("<b>Parte economica</b>", styles["Heading2"]))

    preventivo = lavoro.importo_preventivato or 0
    consuntivo = lavoro.importo_consuntivo or 0

    totale_materiali = lavoro.totale_materiali or 0
    totale_manodopera = lavoro.totale_manodopera or 0

    margine = lavoro.margine or 0

    economica = [
        ["Voce", "Importo"],

        ["Preventivo", f"EUR {preventivo:.2f}"],

        ["Costo materiali", f"EUR {totale_materiali:.2f}"],

        ["Costo manodopera", f"EUR {totale_manodopera:.2f}"],

        ["Consuntivo reale", f"EUR {consuntivo:.2f}"],

        ["Margine", f"EUR {margine:.2f}"],
    ]

    tabella_economica = Table(economica, colWidths=[250, 180])
    colore_margine = colors.green if margine >= 0 else colors.red
    tabella_economica.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),

        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),

        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),

        ("ALIGN", (1, 1), (1, -1), "RIGHT"),

        ("PADDING", (0, 0), (-1, -1), 8),

        ("TEXTCOLOR", (1, 5), (1, 5), colore_margine),

        ("FONTNAME", (1, 5), (1, 5), "Helvetica-Bold"),
    ]))

    elements.append(tabella_economica)
    elements.append(Spacer(1, 16))

    # materiali usati
    elements.append(Paragraph("<b>Materiali usati</b>", styles["Heading2"]))

    if materiali_usati:
        righe_materiali = [["Materiale", "Quantità", "Costo unitario", "Totale", "Note"]]

        for usato in materiali_usati:
            materiale = materiali_dict.get(usato.materiale_id)

            nome_materiale = materiale.nome if materiale else "Materiale non trovato"
            unita = materiale.unita_misura if materiale else ""

            costo_unitario = usato.costo_unitario or 0
            totale_riga = (usato.quantita or 0) * costo_unitario

            righe_materiali.append([
                nome_materiale,
                f"{usato.quantita} {unita}",
                f"EUR {costo_unitario:.2f}",
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
        elements.append(
            Paragraph(
                f"<b>Totale materiali: EUR {totale_materiali:.2f}</b>",
                styles["Normal"]
            )
        )
    else:
        elements.append(Paragraph("Nessun materiale associato al lavoro.", styles["Normal"]))

    elements.append(Spacer(1, 18))

    if lavoro.note_consuntivo:
        elements.append(Paragraph("<b>Note finali</b>", styles["Heading2"]))
        elements.append(Paragraph(lavoro.note_consuntivo, styles["Normal"]))

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