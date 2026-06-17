import io
from datetime import datetime, date

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

from app.database import get_db
from app.dependencies import get_current_user, to_float, scope_collaboratore
from app import crud
from app.templates_config import templates
from app.validators import DESCRIZIONE_MAX, NOTE_MAX, clean

router = APIRouter(tags=["sal"])


@router.get("/lavori/{lavoro_id}/sal", response_class=HTMLResponse)
def lista_sal(lavoro_id: int, request: Request,
              db: Session = Depends(get_db),
              user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    if not lavoro:
        raise HTTPException(status_code=404)
    sal_list = crud.get_sal_lavoro(db, user_id, lavoro_id)
    preventivo = lavoro.importo_preventivato or 0
    totale_richiesto = sum(s.importo_richiesto for s in sal_list)
    return templates.TemplateResponse(request=request, name="lavoro_sal.html", context={
        "lavoro": lavoro,
        "sal_list": sal_list,
        "preventivo": preventivo,
        "totale_richiesto": totale_richiesto,
        "oggi": date.today(),
    })


@router.post("/lavori/{lavoro_id}/sal/nuovo")
def nuovo_sal(lavoro_id: int, request: Request,
              data: str = Form(...),
              percentuale: str = Form("0"),
              importo_richiesto: str = Form("0"),
              descrizione: str = Form(""),
              note: str = Form(""),
              db: Session = Depends(get_db),
              user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    if not lavoro:
        raise HTTPException(status_code=404)
    crud.crea_sal(
        db=db, utente_id=user_id, lavoro_id=lavoro_id,
        data=data, percentuale=to_float(percentuale),
        importo_richiesto=to_float(importo_richiesto),
        descrizione=clean(descrizione, DESCRIZIONE_MAX),
        note=clean(note, NOTE_MAX),
    )
    return RedirectResponse(url=f"/lavori/{lavoro_id}/sal", status_code=303)


@router.post("/lavori/{lavoro_id}/sal/{sal_id}/stato")
def toggle_sal_stato(lavoro_id: int, sal_id: int, request: Request,
                     db: Session = Depends(get_db),
                     user_id: int = Depends(get_current_user)):
    crud.segna_sal_pagato(db, sal_id, user_id)
    return RedirectResponse(url=f"/lavori/{lavoro_id}/sal", status_code=303)


@router.post("/lavori/{lavoro_id}/sal/{sal_id}/elimina")
def elimina_sal(lavoro_id: int, sal_id: int, request: Request,
                db: Session = Depends(get_db),
                user_id: int = Depends(get_current_user)):
    crud.elimina_sal(db, sal_id, user_id)
    return RedirectResponse(url=f"/lavori/{lavoro_id}/sal", status_code=303)


@router.get("/lavori/{lavoro_id}/sal/{sal_id}/pdf")
def pdf_sal(lavoro_id: int, sal_id: int, request: Request,
            db: Session = Depends(get_db),
            user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id, assegnato_a_id=scope_collaboratore(request, db))
    sal = crud.get_sal_by_id(db, sal_id, user_id)
    if not lavoro or not sal:
        raise HTTPException(status_code=404)

    azienda = crud.get_impostazioni_azienda(db, user_id)
    cliente = lavoro.cliente

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    els = []

    from pathlib import Path
    from reportlab.platypus import Image as RLImage
    if azienda and azienda.logo_path:
        lp = azienda.logo_path
        if lp.startswith("http") or Path(lp).exists():
            img = RLImage(lp, width=120, height=60)
            img.hAlign = "LEFT"
            els.append(img)
            els.append(Spacer(1, 8))

    nome_az = (azienda.nome_azienda or "La tua azienda") if azienda else "La tua azienda"
    piva = (azienda.partita_iva or "") if azienda else ""
    indirizzo = (azienda.indirizzo or "") if azienda else ""
    tel = (azienda.telefono or "") if azienda else ""
    email = (azienda.email or "") if azienda else ""

    els.append(Paragraph(f"<b>{nome_az}</b>", styles["Title"]))
    if piva:
        els.append(Paragraph(f"P.IVA: {piva}", styles["Normal"]))
    if indirizzo:
        els.append(Paragraph(f"Indirizzo: {indirizzo}", styles["Normal"]))
    if tel or email:
        els.append(Paragraph(f"Tel: {tel}  —  Email: {email}", styles["Normal"]))
    els.append(Spacer(1, 18))

    els.append(Paragraph(f"<b>STATO AVANZAMENTO LAVORI N. {sal.numero}</b>", styles["Heading1"]))
    els.append(Paragraph(f"Data: {sal.data}", styles["Normal"]))
    els.append(Spacer(1, 12))

    # Cliente
    nome_cliente = f"{cliente.nome or ''} {cliente.cognome or ''}".strip() if cliente else ""
    if cliente and cliente.ragione_sociale:
        nome_cliente = cliente.ragione_sociale
    els.append(Paragraph("<b>Cliente</b>", styles["Heading2"]))
    els.append(Paragraph(nome_cliente, styles["Normal"]))
    if cliente and cliente.telefono:
        els.append(Paragraph(f"Tel: {cliente.telefono}", styles["Normal"]))
    els.append(Spacer(1, 12))

    # Lavoro
    els.append(Paragraph("<b>Lavoro</b>", styles["Heading2"]))
    els.append(Paragraph(f"Titolo: {lavoro.titolo}", styles["Normal"]))
    els.append(Paragraph(f"Data lavoro: {lavoro.data_lavoro}", styles["Normal"]))
    els.append(Spacer(1, 12))

    if sal.descrizione:
        els.append(Paragraph("<b>Lavori eseguiti</b>", styles["Heading2"]))
        els.append(Paragraph(sal.descrizione.replace("\n", "<br/>"), styles["Normal"]))
        els.append(Spacer(1, 10))

    # Tabella importi
    preventivo = lavoro.importo_preventivato or 0
    righe = [
        ["Descrizione", "Importo"],
        ["Preventivo totale lavoro", f"EUR {preventivo:.2f}"],
        [f"Avanzamento al {sal.percentuale:.0f}%", f"EUR {sal.importo_richiesto:.2f}"],
        ["<b>Importo richiesto con questo SAL</b>", f"<b>EUR {sal.importo_richiesto:.2f}</b>"],
    ]
    tab = Table(righe, colWidths=[330, 150])
    tab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -2), colors.whitesmoke),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f9ff")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    els.append(tab)
    els.append(Spacer(1, 16))

    if sal.note:
        els.append(Paragraph(f"<b>Note:</b> {sal.note}", styles["Normal"]))
        els.append(Spacer(1, 10))

    els.append(Spacer(1, 30))
    els.append(Paragraph("Firma del committente: ______________________________", styles["Normal"]))

    doc.build(els)
    buffer.seek(0)
    filename = f"SAL_{sal.numero}_{lavoro.titolo[:30].replace(' ', '_')}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
