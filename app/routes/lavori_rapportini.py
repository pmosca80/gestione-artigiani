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
from app.dependencies import get_current_user, to_float
from app import crud
from app.templates_config import templates

router = APIRouter(tags=["rapportini"])


@router.get("/lavori/{lavoro_id}/rapportini", response_class=HTMLResponse)
def lista_rapportini(lavoro_id: int, request: Request,
                     db: Session = Depends(get_db),
                     user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404)
    rapportini = crud.get_rapportini_lavoro(db, user_id, lavoro_id)
    totale_ore = sum(r.ore_lavorate or 0 for r in rapportini)
    return templates.TemplateResponse(request=request, name="lavoro_rapportini.html", context={
        "lavoro": lavoro,
        "rapportini": rapportini,
        "totale_ore": totale_ore,
        "oggi": date.today(),
    })


@router.post("/lavori/{lavoro_id}/rapportini/nuovo")
def nuovo_rapportino(lavoro_id: int, request: Request,
                     data: str = Form(...),
                     ore_lavorate: str = Form("0"),
                     descrizione_attivita: str = Form(...),
                     materiali_note: str = Form(""),
                     note: str = Form(""),
                     db: Session = Depends(get_db),
                     user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    if not lavoro:
        raise HTTPException(status_code=404)
    crud.crea_rapportino(
        db=db, utente_id=user_id, lavoro_id=lavoro_id,
        data=data, ore_lavorate=to_float(ore_lavorate),
        descrizione_attivita=descrizione_attivita.strip(),
        materiali_note=materiali_note.strip(), note=note.strip(),
    )
    return RedirectResponse(url=f"/lavori/{lavoro_id}/rapportini", status_code=303)


@router.post("/lavori/{lavoro_id}/rapportini/{rapportino_id}/elimina")
def elimina_rapportino(lavoro_id: int, rapportino_id: int, request: Request,
                       db: Session = Depends(get_db),
                       user_id: int = Depends(get_current_user)):
    crud.elimina_rapportino(db, rapportino_id, user_id)
    return RedirectResponse(url=f"/lavori/{lavoro_id}/rapportini", status_code=303)


@router.get("/lavori/{lavoro_id}/rapportini/{rapportino_id}/pdf")
def pdf_rapportino(lavoro_id: int, rapportino_id: int, request: Request,
                   db: Session = Depends(get_db),
                   user_id: int = Depends(get_current_user)):
    lavoro = crud.get_lavoro_by_id(db, lavoro_id, user_id)
    r = crud.get_rapportino_by_id(db, rapportino_id, user_id)
    if not lavoro or not r:
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
    tel = (azienda.telefono or "") if azienda else ""
    email_az = (azienda.email or "") if azienda else ""

    els.append(Paragraph(f"<b>{nome_az}</b>", styles["Title"]))
    if piva:
        els.append(Paragraph(f"P.IVA: {piva}", styles["Normal"]))
    if tel or email_az:
        els.append(Paragraph(f"Tel: {tel}  —  Email: {email_az}", styles["Normal"]))
    els.append(Spacer(1, 18))

    els.append(Paragraph("<b>RAPPORTINO DI LAVORO</b>", styles["Heading1"]))
    els.append(Paragraph(f"Data: {r.data}", styles["Normal"]))
    els.append(Spacer(1, 12))

    # Cliente e lavoro
    nome_cliente = f"{cliente.nome or ''} {cliente.cognome or ''}".strip() if cliente else ""
    if cliente and cliente.ragione_sociale:
        nome_cliente = cliente.ragione_sociale
    righe_info = [
        ["Cliente", nome_cliente],
        ["Lavoro", lavoro.titolo],
        ["Ore lavorate", f"{r.ore_lavorate:.1f} h" if r.ore_lavorate else "—"],
    ]
    tab_info = Table(righe_info, colWidths=[150, 330])
    tab_info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    els.append(tab_info)
    els.append(Spacer(1, 16))

    # Attività svolte
    els.append(Paragraph("<b>Attività svolte</b>", styles["Heading2"]))
    els.append(Paragraph(r.descrizione_attivita.replace("\n", "<br/>"), styles["Normal"]))
    els.append(Spacer(1, 12))

    if r.materiali_note:
        els.append(Paragraph("<b>Materiali utilizzati</b>", styles["Heading2"]))
        els.append(Paragraph(r.materiali_note.replace("\n", "<br/>"), styles["Normal"]))
        els.append(Spacer(1, 12))

    if r.note:
        els.append(Paragraph(f"<b>Note:</b> {r.note}", styles["Normal"]))
        els.append(Spacer(1, 12))

    els.append(Spacer(1, 40))
    els.append(Paragraph("Firma del tecnico: ______________________________", styles["Normal"]))
    els.append(Spacer(1, 20))
    els.append(Paragraph("Firma del cliente per accettazione: ______________________________", styles["Normal"]))

    doc.build(els)
    buffer.seek(0)
    data_str = r.data.strftime("%Y%m%d") if hasattr(r.data, "strftime") else str(r.data).replace("-", "")
    filename = f"Rapportino_{data_str}_{lavoro.titolo[:25].replace(' ', '_')}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
