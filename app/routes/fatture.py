import io
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.templates_config import templates

router = APIRouter(prefix="/fatture", tags=["fatture"])


@router.get("/", response_class=HTMLResponse)
def registro_fatture(
    request: Request,
    anno: int = None,
    inviata: int = None,
    errore: str = None,
    msg: str = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.services.email import smtp_configurato
    from app.services.sdi import pec_configurata

    anni_disponibili = crud.get_anni_fatture(db, user_id)
    anno_sel = anno or (anni_disponibili[0] if anni_disponibili else datetime.now().year)

    fatture = crud.get_fatture_registro(db, user_id, anno_sel)

    tot_imponibile = sum(f.importo_imponibile or 0 for f in fatture)
    tot_iva = sum(f.importo_iva or 0 for f in fatture)
    tot_totale = sum(f.importo_totale or 0 for f in fatture)

    azienda = crud.get_impostazioni_azienda(db, user_id)

    _ERRORI = {
        "email_mancante":       "Il cliente non ha un indirizzo email — aggiornalo nella scheda cliente.",
        "smtp_non_configurato": "Email non configurata. Imposta MAIL_USERNAME e MAIL_PASSWORD nelle variabili d'ambiente.",
        "pec_non_configurata":  "PEC non configurata. Vai a Impostazioni › Azienda e inserisci i dati PEC.",
        "fattura_non_trovata":  "Fattura non trovata.",
        "lavoro_non_trovato":   "Lavoro collegato non trovato.",
        "invio_fallito":        f"Invio fallito: {msg or 'errore sconosciuto'}",
        "sdi_fallito":          f"Invio a SDI fallito: {msg or 'errore sconosciuto'}",
    }

    return templates.TemplateResponse(
        request=request,
        name="fatture_registro.html",
        context={
            "fatture": fatture,
            "anni_disponibili": anni_disponibili,
            "anno_sel": anno_sel,
            "tot_imponibile": tot_imponibile,
            "tot_iva": tot_iva,
            "tot_totale": tot_totale,
            "smtp_ok": smtp_configurato(),
            "pec_ok": pec_configurata(azienda) if azienda else False,
            "flash_ok": inviata,
            "flash_err": _ERRORI.get(errore) if errore else None,
        },
    )


@router.get("/export-excel")
def export_excel(
    anno: int = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    anni_disponibili = crud.get_anni_fatture(db, user_id)
    anno_sel = anno or (anni_disponibili[0] if anni_disponibili else datetime.now().year)
    fatture = crud.get_fatture_registro(db, user_id, anno_sel)
    azienda = crud.get_impostazioni_azienda(db, user_id)
    nome_az = azienda.nome_azienda or "Azienda"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Fatture {anno_sel}"

    # Palette colori
    PURPLE = "7C3AED"
    PURPLE_LIGHT = "EDE9FE"
    GRAY_HEADER = "F8FAFC"
    BORDER_COLOR = "E5E7EB"

    thin_border = Border(
        left=Side(style="thin", color=BORDER_COLOR),
        right=Side(style="thin", color=BORDER_COLOR),
        top=Side(style="thin", color=BORDER_COLOR),
        bottom=Side(style="thin", color=BORDER_COLOR),
    )

    # ── Riga titolo ───────────────────────────────────────────────────────────
    ws.merge_cells("A1:I1")
    title_cell = ws["A1"]
    title_cell.value = f"Registro Fatture {anno_sel} — {nome_az}"
    title_cell.font = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    title_cell.fill = PatternFill("solid", fgColor=PURPLE)
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:I2")
    ws["A2"].value = f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A2"].font = Font(name="Calibri", size=10, color="9CA3AF")
    ws["A2"].alignment = Alignment(horizontal="left", indent=1)
    ws.row_dimensions[2].height = 16

    # ── Intestazioni colonne ──────────────────────────────────────────────────
    headers = ["N° Fattura", "Data", "Cliente", "P.IVA / CF Cliente",
               "Imponibile (€)", "IVA (€)", "Totale (€)", "Stato", "File XML"]
    ws.append([])  # riga 3 vuota
    ws.append(headers)  # riga 4

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.font = Font(name="Calibri", bold=True, size=10, color="374151")
        cell.fill = PatternFill("solid", fgColor=GRAY_HEADER.replace("#", ""))
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 22

    # ── Righe dati ────────────────────────────────────────────────────────────
    tot_imponibile = 0.0
    tot_iva = 0.0
    tot_totale = 0.0

    for f in fatture:
        lav = f.lavoro
        cli = lav.cliente if lav else None

        if cli:
            if cli.tipo_cliente == "azienda":
                nome_cli = cli.ragione_sociale or "—"
            else:
                nome_cli = f"{cli.nome or ''} {cli.cognome or ''}".strip() or "—"
            piva_cf = cli.partita_iva or cli.codice_fiscale or "—"
        else:
            nome_cli = "—"
            piva_cf = "—"

        numero_fmt = f"{f.anno}/{str(f.numero).zfill(3)}"
        imp = float(f.importo_imponibile or 0)
        iva = float(f.importo_iva or 0)
        tot = float(f.importo_totale or 0)
        tot_imponibile += imp
        tot_iva += iva
        tot_totale += tot

        row_data = [
            numero_fmt,
            f.data_emissione,
            nome_cli,
            piva_cf,
            imp,
            iva,
            tot,
            f.stato or "emessa",
            f.nome_file or "",
        ]
        ws.append(row_data)
        data_row = ws.max_row

        for col_idx in range(1, 10):
            cell = ws.cell(row=data_row, column=col_idx)
            cell.font = Font(name="Calibri", size=10)
            cell.alignment = Alignment(vertical="center")
            cell.border = thin_border

        # Numero fattura in viola
        ws.cell(row=data_row, column=1).font = Font(name="Calibri", bold=True, size=10, color=PURPLE)
        ws.cell(row=data_row, column=1).fill = PatternFill("solid", fgColor=PURPLE_LIGHT)

        # Importi allineati a destra con formato valuta
        for col_idx in [5, 6, 7]:
            cell = ws.cell(row=data_row, column=col_idx)
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal="right", vertical="center")

        ws.row_dimensions[data_row].height = 18

    # ── Riga totali ───────────────────────────────────────────────────────────
    totals_row = ws.max_row + 1
    ws.cell(row=totals_row, column=1).value = f"TOTALI {anno_sel}"
    ws.cell(row=totals_row, column=1).font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
    ws.cell(row=totals_row, column=1).fill = PatternFill("solid", fgColor=PURPLE)
    ws.cell(row=totals_row, column=1).alignment = Alignment(horizontal="left", vertical="center", indent=1)

    ws.merge_cells(f"A{totals_row}:D{totals_row}")

    for col_idx, val in [(5, tot_imponibile), (6, tot_iva), (7, tot_totale)]:
        cell = ws.cell(row=totals_row, column=col_idx)
        cell.value = val
        cell.number_format = '#,##0.00'
        cell.font = Font(name="Calibri", bold=True, size=10, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=PURPLE)
        cell.alignment = Alignment(horizontal="right", vertical="center")
        cell.border = thin_border

    for col_idx in [2, 3, 4, 8, 9]:
        cell = ws.cell(row=totals_row, column=col_idx)
        cell.fill = PatternFill("solid", fgColor=PURPLE)
        cell.border = thin_border

    ws.row_dimensions[totals_row].height = 22

    # ── Larghezze colonne ─────────────────────────────────────────────────────
    col_widths = [14, 12, 30, 20, 15, 12, 15, 14, 28]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ── Output ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"fatture_{anno_sel}_{nome_az.replace(' ', '_')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.csv")
def export_csv_fatture(
    anno: int = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from fastapi.responses import Response as _Response
    anni_disponibili = crud.get_anni_fatture(db, user_id)
    anno_sel = anno or (anni_disponibili[0] if anni_disponibili else datetime.now().year)
    fatture_list = crud.get_fatture_registro(db, user_id, anno_sel)

    righe = ["N. Fattura,Data,Cliente,P.IVA/CF,Imponibile,IVA,Totale,Stato"]
    for f in fatture_list:
        lav = f.lavoro
        cli = lav.cliente if lav else None
        if cli:
            nome_cli = (
                cli.ragione_sociale if cli.tipo_cliente == "azienda"
                else f"{cli.nome or ''} {cli.cognome or ''}".strip()
            ) or ""
            piva_cf = cli.partita_iva or cli.codice_fiscale or ""
        else:
            nome_cli = ""
            piva_cf = ""
        numero_fmt = f"{f.anno}/{str(f.numero).zfill(3)}"
        nome_cli = nome_cli.replace('"', "'")
        righe.append(
            f'{numero_fmt},{f.data_emissione},"{nome_cli}",{piva_cf},'
            f'{f.importo_imponibile or 0:.2f},{f.importo_iva or 0:.2f},'
            f'{f.importo_totale or 0:.2f},{f.stato or "emessa"}'
        )

    content = "﻿" + "\n".join(righe)
    filename = f"fatture_{anno_sel}.csv"
    return _Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{fattura_id}/invia-email")
def invia_fattura_email(
    fattura_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.models import FatturaEmessa
    from app.services.fatturapa import genera_xml_fatturapa, nome_file_fatturapa
    from app.services.email import invia_fattura_xml, smtp_configurato

    fattura = db.query(FatturaEmessa).filter(
        FatturaEmessa.id == fattura_id,
        FatturaEmessa.utente_id == user_id,
    ).first()
    if not fattura:
        return RedirectResponse("/fatture/?errore=fattura_non_trovata", status_code=303)

    lav = fattura.lavoro
    if not lav:
        return RedirectResponse("/fatture/?errore=lavoro_non_trovato", status_code=303)

    cli = lav.cliente
    if not cli or not (cli.email or "").strip():
        return RedirectResponse(
            f"/fatture/?anno={fattura.anno}&errore=email_mancante&id={fattura_id}",
            status_code=303,
        )

    if not smtp_configurato():
        return RedirectResponse("/fatture/?errore=smtp_non_configurato", status_code=303)

    azienda = crud.get_impostazioni_azienda(db, user_id)
    nome_file = fattura.nome_file or nome_file_fatturapa(azienda, lav)
    numero_fmt = f"{fattura.anno}/{str(fattura.numero).zfill(3)}"

    try:
        voci = crud.get_voci_preventivo(db, user_id, lav.id)
        xml_bytes = genera_xml_fatturapa(lav, cli, azienda, voci=voci or None)
        to_nome = (
            cli.ragione_sociale if cli.tipo_cliente == "azienda"
            else f"{cli.nome or ''} {cli.cognome or ''}".strip()
        ) or "Cliente"
        invia_fattura_xml(
            to_email=cli.email.strip(),
            to_nome=to_nome,
            from_nome=azienda.nome_azienda or "Azienda",
            numero_fattura=numero_fmt,
            data_emissione=fattura.data_emissione,
            importo_totale=float(fattura.importo_totale or 0),
            xml_bytes=xml_bytes,
            nome_file=nome_file,
        )
        fattura.stato = "inviata_sdi"
        db.commit()
        return RedirectResponse(
            f"/fatture/?anno={fattura.anno}&inviata={fattura_id}",
            status_code=303,
        )
    except Exception as exc:
        import urllib.parse
        msg = urllib.parse.quote(str(exc)[:120])
        return RedirectResponse(
            f"/fatture/?anno={fattura.anno}&errore=invio_fallito&msg={msg}",
            status_code=303,
        )


@router.post("/{fattura_id}/invia-sdi")
def invia_fattura_sdi(
    fattura_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.models import FatturaEmessa
    from app.services.fatturapa import genera_xml_fatturapa, nome_file_fatturapa
    from app.services.sdi import invia_xml_a_sdi, pec_configurata
    import urllib.parse

    fattura = db.query(FatturaEmessa).filter(
        FatturaEmessa.id == fattura_id,
        FatturaEmessa.utente_id == user_id,
    ).first()
    if not fattura:
        return RedirectResponse("/fatture/?errore=fattura_non_trovata", status_code=303)

    lav = fattura.lavoro
    if not lav:
        return RedirectResponse("/fatture/?errore=lavoro_non_trovato", status_code=303)

    azienda = crud.get_impostazioni_azienda(db, user_id)
    if not azienda or not pec_configurata(azienda):
        return RedirectResponse("/fatture/?errore=pec_non_configurata", status_code=303)

    try:
        voci = crud.get_voci_preventivo(db, user_id, lav.id)
        xml_bytes = genera_xml_fatturapa(lav, lav.cliente, azienda, voci=voci or None)
        nome_file = fattura.nome_file or nome_file_fatturapa(azienda, lav)
        invia_xml_a_sdi(xml_bytes, nome_file, azienda)
        fattura.stato = "inviata_sdi"
        db.commit()
        return RedirectResponse(
            f"/fatture/?anno={fattura.anno}&inviata={fattura_id}",
            status_code=303,
        )
    except Exception as exc:
        msg = urllib.parse.quote(str(exc)[:120])
        return RedirectResponse(
            f"/fatture/?anno={fattura.anno}&errore=sdi_fallito&msg={msg}",
            status_code=303,
        )


@router.post("/{fattura_id}/stato")
def aggiorna_stato(
    fattura_id: int,
    stato: str = Form(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.aggiorna_stato_fattura(db, fattura_id, user_id, stato)
    return RedirectResponse("/fatture/", status_code=303)
