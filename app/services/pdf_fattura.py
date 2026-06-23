from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

_PURPLE = colors.HexColor("#7c3aed")
_TEAL   = colors.HexColor("#0d9488")
_DARK   = colors.HexColor("#111827")
_GRAY   = colors.HexColor("#6b7280")
_LIGHT  = colors.HexColor("#f3f4f6")
_BORDER = colors.HexColor("#e5e7eb")
_WHITE  = colors.white
_LAVAND = colors.HexColor("#e0e7ff")

_REGIMI_SENZA_IVA = {"RF19", "RF02"}


def _fmt(d):
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(d or "")


def _euro(val):
    try:
        s = f"{float(val):,.2f}"
        return "€ " + s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "€ 0,00"


def _p(text, style):
    return Paragraph(str(text or ""), style)


def _make_styles():
    return dict(
        norm  = ParagraphStyle("pf_norm",  fontName="Helvetica",      fontSize=9,  leading=13, textColor=_DARK),
        bold  = ParagraphStyle("pf_bold",  fontName="Helvetica-Bold", fontSize=9,  leading=13, textColor=_DARK),
        small = ParagraphStyle("pf_small", fontName="Helvetica",      fontSize=8,  leading=11, textColor=_GRAY),
        big   = ParagraphStyle("pf_big",   fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=_WHITE),
        sub   = ParagraphStyle("pf_sub",   fontName="Helvetica",      fontSize=9,  leading=13, textColor=_LAVAND),
        right = ParagraphStyle("pf_right", fontName="Helvetica",      fontSize=9,  leading=13, textColor=_DARK, alignment=TA_RIGHT),
        boldr = ParagraphStyle("pf_boldr", fontName="Helvetica-Bold", fontSize=9,  leading=13, textColor=_DARK, alignment=TA_RIGHT),
        label = ParagraphStyle("pf_label", fontName="Helvetica-Bold", fontSize=7,  leading=10, textColor=_GRAY),
        title = ParagraphStyle("pf_title", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=_WHITE),
    )


def _az_lines(a):
    if not a:
        return ["La mia azienda"]
    lines = [a.nome_azienda or "La mia azienda"]
    city = " ".join(filter(None, [a.cap or "", a.citta or ""])).strip()
    if a.provincia and city:
        city += f" ({a.provincia})"
    addr = ", ".join(filter(None, [a.indirizzo or "", city]))
    if addr:
        lines.append(addr)
    tax = " | ".join(filter(None, [
        f"P.IVA {a.partita_iva}" if a.partita_iva else "",
        f"C.F. {a.codice_fiscale}" if a.codice_fiscale else "",
    ]))
    if tax:
        lines.append(tax)
    contacts = " | ".join(filter(None, [a.telefono or "", a.email or ""]))
    if contacts:
        lines.append(contacts)
    return lines


def _cli_lines(c):
    if not c:
        return ["—"]
    if c.tipo_cliente == "azienda":
        name = c.ragione_sociale or "Azienda"
    else:
        name = f"{c.nome or ''} {c.cognome or ''}".strip() or "Cliente"
    lines = [name]
    if c.indirizzo:
        lines.append(c.indirizzo)
    city = " ".join(filter(None, [c.cap or "", c.citta or ""])).strip()
    if c.provincia and city:
        city += f" ({c.provincia})"
    if city:
        lines.append(city)
    if c.partita_iva:
        lines.append(f"P.IVA {c.partita_iva}")
    if c.codice_fiscale:
        lines.append(f"C.F. {c.codice_fiscale}")
    if c.email:
        lines.append(c.email)
    return lines


def _voci_table(voci, W, S):
    data = [[
        _p("Descrizione", S["bold"]),
        _p("Qtà", S["bold"]),
        _p("U.M.", S["bold"]),
        _p("Prezzo", S["bold"]),
        _p("Importo", S["bold"]),
    ]]
    for v in sorted(voci, key=lambda x: x.ordine):
        riga = round(float(v.quantita or 1) * float(v.prezzo_unitario or 0), 2)
        data.append([
            _p(v.descrizione or "", S["norm"]),
            _p(f"{v.quantita:g}" if v.quantita is not None else "1", S["norm"]),
            _p(v.unita_misura or "", S["norm"]),
            _p(_euro(v.prezzo_unitario), S["right"]),
            _p(_euro(riga), S["right"]),
        ])
    cw = [W * 0.42, W * 0.08, W * 0.09, W * 0.19, W * 0.22]
    tbl = Table(data, colWidths=cw, repeatRows=1)
    cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), _DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("TOPPADDING",    (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 9),
        ("TOPPADDING",    (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (0, 0), (0, -1), "LEFT"),
        ("GRID",          (0, 0), (-1, -1), 0.3, _BORDER),
    ]
    for idx in range(1, len(data)):
        if idx % 2 == 1:
            cmds.append(("BACKGROUND", (0, idx), (-1, idx), _LIGHT))
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _totals_table(rows, W, S, accent):
    data = []
    for i, (lbl, val) in enumerate(rows):
        is_last = i == len(rows) - 1
        data.append([
            _p("", S["norm"]),
            _p(lbl, S["bold"] if is_last else S["norm"]),
            _p(str(val), S["boldr"] if is_last else S["right"]),
        ])
    tbl = Table(data, colWidths=[W * 0.37, W * 0.41, W * 0.22])
    cmds = [
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (0, -1), 0),
        ("RIGHTPADDING",  (0, 0), (0, -1), 0),
        ("LEFTPADDING",   (1, 0), (1, -1), 10),
        ("RIGHTPADDING",  (2, 0), (2, -1), 6),
        ("LINEABOVE",     (1, 0), (2, 0), 0.5, _BORDER),
        ("LINEABOVE",     (1, -1), (2, -1), 1.5, accent),
        ("TEXTCOLOR",     (1, -1), (2, -1), accent),
        ("FONTNAME",      (1, -1), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (1, -1), (2, -1), 11),
        ("BACKGROUND",    (1, -1), (2, -1), _LIGHT),
    ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _header_block(az, label, subtitle, accent, W, S):
    hdr = Table([[
        [_p(az[0], S["big"])] + [_p(l, S["sub"]) for l in az[1:]],
        [_p(label, S["title"]), _p(subtitle, S["sub"])],
    ]], colWidths=[W * 0.62, W * 0.38])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), accent),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (0, -1), 16),
        ("RIGHTPADDING",  (1, 0), (1, -1), 16),
        ("TOPPADDING",    (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
    ]))
    return hdr


def _sides_block(az, cl, W, S):
    left  = [_p(l, S["bold"] if i == 0 else S["norm"]) for i, l in enumerate(az)]
    right = [_p("DESTINATARIO", S["label"])] + [
        _p(l, S["bold"] if i == 0 else S["norm"]) for i, l in enumerate(cl)
    ]
    tbl = Table([[left, right]], colWidths=[W * 0.5, W * 0.5])
    tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (0, -1), 0),
        ("LEFTPADDING",   (1, 0), (1, -1), 20),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("LINEAFTER",     (0, 0), (0, -1), 0.5, _BORDER),
    ]))
    return tbl


def _info_block(info_rows, W, S):
    n = len(info_rows)
    data = [[[_p(lbl, S["label"]), _p(val, S["bold"])] for lbl, val in info_rows]]
    tbl = Table(data, colWidths=[W / n] * n)
    cmds = [
        ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 0.5, _BORDER),
    ] + [("LINEAFTER", (c, 0), (c, -1), 0.5, _BORDER) for c in range(n - 1)]
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _footer(story, azienda, W, S):
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=_BORDER))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_p(" · ".join(_az_lines(azienda)), S["small"]))


def _totali_fattura(lavoro, voci, forfettario: bool, aliquota: float):
    """Imponibile/IVA/totale per la fattura PDF. Se ci sono voci, il
    totale deve coincidere con quelle appena elencate nel documento — non
    con importo_consuntivo/totale_iva, calcolati solo quando si salva la
    scheda lavoro e quindi potenzialmente scollegati dalle voci attuali."""
    if voci:
        imponibile = sum(float(v.quantita or 1) * float(v.prezzo_unitario or 0) for v in voci)
        totale_iva = 0.0 if forfettario else round(imponibile * aliquota / 100, 2)
        totale_doc = imponibile + totale_iva
    else:
        imponibile = float(lavoro.importo_consuntivo or 0)
        totale_iva = 0.0 if forfettario else float(lavoro.totale_iva or 0)
        totale_doc = float(lavoro.totale_documento or imponibile + totale_iva)
    return imponibile, totale_iva, totale_doc


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def genera_pdf_fattura(lavoro, cliente, azienda, voci=None) -> bytes:
    buf = BytesIO()
    W   = A4[0] - 4 * cm
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    S = _make_styles()
    story = []

    regime      = (azienda.regime_fiscale if azienda else "RF01") or "RF01"
    forfettario = regime in _REGIMI_SENZA_IVA

    num     = lavoro.numero_fattura or "—"
    anno    = str(lavoro.data_fattura or "")[:4] or "—"
    num_fmt = f"{int(num):03d}" if str(num).isdigit() else str(num)

    az = _az_lines(azienda)
    cl = _cli_lines(cliente)

    story.append(_header_block(az, "FATTURA", f"N. {num_fmt}/{anno}", _PURPLE, W, S))
    story.append(Spacer(1, 0.4 * cm))
    story.append(_sides_block(az, cl, W, S))
    story.append(Spacer(1, 0.4 * cm))
    story.append(_info_block([
        ("DATA EMISSIONE", _fmt(lavoro.data_fattura) if lavoro.data_fattura else "—"),
        ("N. FATTURA",     f"{num_fmt}/{anno}"),
        ("SCADENZA",       _fmt(lavoro.data_scadenza_pagamento) if lavoro.data_scadenza_pagamento else "30 gg fattura"),
        ("REGIME",         regime),
    ], W, S))
    story.append(Spacer(1, 0.5 * cm))

    story.append(_p("DETTAGLIO PRESTAZIONI", S["label"]))
    story.append(Spacer(1, 0.2 * cm))
    if voci:
        story.append(_voci_table(voci, W, S))
    else:
        fb = Table(
            [[_p(lavoro.titolo or "Prestazione", S["bold"]),
              _p(_euro(lavoro.importo_consuntivo), S["right"])]],
            colWidths=[W * 0.75, W * 0.25],
        )
        fb.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("BOX",           (0, 0), (-1, -1), 0.5, _BORDER),
        ]))
        story.append(fb)
        if lavoro.descrizione:
            story.append(Spacer(1, 0.2 * cm))
            story.append(_p(lavoro.descrizione, S["small"]))

    story.append(Spacer(1, 0.5 * cm))

    aliquota = float(lavoro.aliquota_iva if lavoro.aliquota_iva is not None else 22)
    imponibile, totale_iva, totale_doc = _totali_fattura(lavoro, voci, forfettario, aliquota)
    bollo = 2.0 if (forfettario and imponibile > 77.47) else 0.0

    rows = [("Imponibile", _euro(imponibile))]
    if forfettario:
        rows.append(("IVA", "Esente — regime forfettario"))
    else:
        rows.append((f"IVA {aliquota:.0f}%", _euro(totale_iva)))
    if lavoro.ritenuta_acconto:
        aliq_r = float(lavoro.aliquota_ritenuta or 20)
        rows.append((f"Ritenuta d'acconto {aliq_r:.0f}%", f"- {_euro(imponibile * aliq_r / 100)}"))
    if bollo:
        rows.append(("Marca da bollo", _euro(bollo)))
        totale_doc += bollo
    rows.append(("TOTALE FATTURA", _euro(totale_doc)))

    story.append(_totals_table(rows, W, S, _PURPLE))

    if lavoro.note_consuntivo:
        story += [Spacer(1, 0.5*cm),
                  HRFlowable(width=W, thickness=0.5, color=_BORDER),
                  Spacer(1, 0.3*cm),
                  _p("NOTE", S["label"]),
                  Spacer(1, 0.15*cm),
                  _p(lavoro.note_consuntivo, S["small"])]

    _footer(story, azienda, W, S)
    doc.build(story)
    return buf.getvalue()


def genera_pdf_preventivo(lavoro, cliente, azienda, voci=None) -> bytes:
    buf = BytesIO()
    W   = A4[0] - 4 * cm
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    S = _make_styles()
    story = []

    regime      = (azienda.regime_fiscale if azienda else "RF01") or "RF01"
    forfettario = regime in _REGIMI_SENZA_IVA

    num_prev  = lavoro.numero_preventivo or str(lavoro.id)
    data_prev = _fmt(lavoro.data_lavoro) if lavoro.data_lavoro else "—"
    tit       = lavoro.titolo or ""
    tit_short = tit[:38] + "…" if len(tit) > 38 else tit

    az = _az_lines(azienda)
    cl = _cli_lines(cliente)

    story.append(_header_block(az, "PREVENTIVO", f"N. {num_prev}", _TEAL, W, S))
    story.append(Spacer(1, 0.4 * cm))
    story.append(_sides_block(az, cl, W, S))
    story.append(Spacer(1, 0.4 * cm))
    story.append(_info_block([
        ("DATA",          data_prev),
        ("N. PREVENTIVO", str(num_prev)),
        ("VALIDITÀ",      "30 giorni"),
        ("OGGETTO",       tit_short),
    ], W, S))
    story.append(Spacer(1, 0.5 * cm))

    if lavoro.descrizione:
        story += [_p("DESCRIZIONE", S["label"]),
                  Spacer(1, 0.15 * cm),
                  _p(lavoro.descrizione, S["norm"]),
                  Spacer(1, 0.4 * cm)]

    story.append(_p("DETTAGLIO VOCI", S["label"]))
    story.append(Spacer(1, 0.2 * cm))

    if voci:
        imponibile = sum(float(v.quantita or 1) * float(v.prezzo_unitario or 0) for v in voci)
        story.append(_voci_table(voci, W, S))
    else:
        imponibile = float(lavoro.importo_preventivato or 0)
        fb = Table(
            [[_p(tit or "Prestazione", S["bold"]),
              _p(_euro(imponibile), S["right"])]],
            colWidths=[W * 0.75, W * 0.25],
        )
        fb.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("BOX",           (0, 0), (-1, -1), 0.5, _BORDER),
        ]))
        story.append(fb)

    story.append(Spacer(1, 0.5 * cm))

    sconto   = float(lavoro.sconto or 0)
    sconto_v = round(imponibile * sconto / 100, 2) if sconto else 0.0
    impon_n  = round(imponibile - sconto_v, 2)
    aliquota = float(lavoro.aliquota_iva if lavoro.aliquota_iva is not None else 22)
    iva_val  = 0.0 if forfettario else round(impon_n * aliquota / 100, 2)
    bollo    = 2.0 if (forfettario and impon_n > 77.47) else 0.0
    totale   = round(impon_n + iva_val + bollo, 2)

    rows = []
    if sconto:
        rows.append(("Imponibile lordo", _euro(imponibile)))
        rows.append((f"Sconto {sconto:.0f}%", f"- {_euro(sconto_v)}"))
    rows.append(("Imponibile", _euro(impon_n)))
    if forfettario:
        rows.append(("IVA", "Esente — regime forfettario"))
        if bollo:
            rows.append(("Marca da bollo", _euro(bollo)))
    else:
        rows.append((f"IVA {aliquota:.0f}%", _euro(iva_val)))
    rows.append(("TOTALE PREVENTIVO", _euro(totale)))

    story.append(_totals_table(rows, W, S, _TEAL))

    story += [
        Spacer(1, 0.5 * cm),
        HRFlowable(width=W, thickness=0.5, color=_BORDER),
        Spacer(1, 0.3 * cm),
        _p("CONDIZIONI", S["label"]),
        Spacer(1, 0.15 * cm),
        _p("Il presente preventivo è valido 30 giorni dalla data di emissione. "
           "Per accettazione si prega di comunicarlo per iscritto o di firmare e restituire copia.", S["small"]),
    ]

    if lavoro.note_consuntivo:
        story += [Spacer(1, 0.3*cm),
                  _p("NOTE", S["label"]),
                  Spacer(1, 0.1*cm),
                  _p(lavoro.note_consuntivo, S["small"])]

    _footer(story, azienda, W, S)
    doc.build(story)
    return buf.getvalue()
