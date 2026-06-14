from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.services.fatturapa import genera_xml_fatturapa, nome_file_fatturapa, errori_fatturapa, bollo_dovuto, _REGIMI_SENZA_IVA
from app.templates_config import templates

router = APIRouter(prefix="/documenti", tags=["documenti"])


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

    errori = errori_fatturapa(lavoro, cliente, azienda)
    if errori:
        items = "".join(f"<li>{err}</li>" for err in errori)
        return HTMLResponse(
            status_code=422,
            content=f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FatturaPA — dati mancanti</title>
  <link rel="stylesheet" href="/static/style.css">
  <style>
    body {{ font-family: 'DM Sans', sans-serif; background: #f8fafc; }}
    .wrap {{ max-width: 640px; margin: 60px auto; padding: 0 20px; }}
    .card {{ background: white; border: 1px solid #fca5a5; border-radius: 16px; padding: 32px; }}
    h2 {{ font-size: 20px; font-weight: 700; color: #991b1b; margin: 0 0 8px; }}
    p  {{ color: #6b7280; font-size: 14px; margin: 0 0 20px; }}
    ul {{ color: #374151; font-size: 14px; padding-left: 20px; line-height: 1.9; margin: 0 0 28px; }}
    .btn {{ display: inline-block; padding: 10px 20px; background: #2563eb; color: white;
            border-radius: 9px; font-size: 14px; font-weight: 700; text-decoration: none; }}
    .btn-gray {{ background: #f3f4f6; color: #374151; margin-left: 8px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h2>Impossibile generare la FatturaPA</h2>
      <p>Correggi i seguenti dati prima di scaricare il file XML:</p>
      <ul>{items}</ul>
      <a href="/lavori/{lavoro_id}/modifica" class="btn">✏️ Modifica lavoro</a>
      <a href="/lavori/{lavoro_id}" class="btn btn-gray">← Torna alla scheda</a>
    </div>
  </div>
</body>
</html>""",
        )

    # Auto-assegna numero fattura se non ancora impostato
    if not lavoro.numero_fattura:
        anno_gen, numero_gen = _crud.genera_numero_fattura(db, user_id)
        lavoro.numero_fattura = numero_gen
        if not lavoro.data_fattura:
            from datetime import date
            lavoro.data_fattura = f"{anno_gen}-{date.today().month:02d}-{date.today().day:02d}"
        db.commit()
        db.refresh(lavoro)

    lavoro.stato_fattura = "emessa"
    db.commit()

    # Salva nel registro fatture
    from datetime import date as _date
    data_em = lavoro.data_fattura or _date.today().isoformat()
    try:
        anno = int(data_em[:4])
    except (ValueError, TypeError):
        anno = _date.today().year
    imponibile_val = float(lavoro.importo_consuntivo or 0)
    regime_str = (azienda.regime_fiscale or "RF01").strip().upper()
    regime_senza_iva = regime_str in _REGIMI_SENZA_IVA
    aliquota_val = 0.0 if regime_senza_iva else float(lavoro.aliquota_iva or 22)
    iva_val = 0.0 if (regime_senza_iva or aliquota_val == 0) else float(
        lavoro.totale_iva or round(imponibile_val * aliquota_val / 100, 2)
    )
    totale_val = imponibile_val if regime_senza_iva else float(lavoro.totale_documento or 0)
    totale_val = round(totale_val + bollo_dovuto(regime_senza_iva, imponibile_val), 2)
    filename = nome_file_fatturapa(azienda, lavoro)
    _crud.salva_fattura_emessa(
        db, user_id, lavoro.id, lavoro.numero_fattura, anno, data_em,
        imponibile_val, iva_val, totale_val, filename, azienda.regime_fiscale or "RF01"
    )

    voci = _crud.get_voci_preventivo(db, user_id, lavoro_id)
    xml_bytes = genera_xml_fatturapa(lavoro, cliente, azienda, voci=voci or None)

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