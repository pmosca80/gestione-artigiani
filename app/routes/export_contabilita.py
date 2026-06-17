from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, richiedi_titolare
from app import crud
from app.templates_config import templates

router = APIRouter(prefix="/export", tags=["export"], dependencies=[Depends(richiedi_titolare)])


@router.get("/", response_class=HTMLResponse)
def export_hub(
    request: Request,
    anno: int = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.services.piani import get_piano, ha_export
    if not ha_export(get_piano(db, user_id)):
        return RedirectResponse("/piani?upgrade=export", status_code=303)

    anni_fatture = crud.get_anni_fatture(db, user_id)
    anno_corrente = datetime.now().year
    anno_sel = anno or (anni_fatture[0] if anni_fatture else anno_corrente)
    anni_disponibili = list(range(anno_corrente, anno_corrente - 6, -1))
    return templates.TemplateResponse(
        request=request,
        name="export_contabilita.html",
        context={
            "anno_sel": anno_sel,
            "anni_disponibili": anni_disponibili,
        },
    )


@router.get("/riepilogo.xml")
def export_xml(
    anno: int = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.services.piani import get_piano, ha_export
    if not ha_export(get_piano(db, user_id)):
        return RedirectResponse("/piani?upgrade=export", status_code=303)

    anno_sel = anno or datetime.now().year
    fatture_list = crud.get_fatture_registro(db, user_id, anno_sel)
    voci_pn = crud.get_prima_nota(db, user_id, anno=anno_sel)
    azienda = crud.get_impostazioni_azienda(db, user_id)
    nome_az = (azienda.nome_azienda or "") if azienda else ""

    root = Element("Contabilita")
    root.set("anno", str(anno_sel))
    root.set("azienda", nome_az)
    root.set("generato", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

    fat_el = SubElement(root, "Fatture")
    tot_imp = sum(float(f.importo_imponibile or 0) for f in fatture_list)
    tot_iva = sum(float(f.importo_iva or 0) for f in fatture_list)
    tot_tot = sum(float(f.importo_totale or 0) for f in fatture_list)
    fat_el.set("count", str(len(fatture_list)))
    fat_el.set("totale_imponibile", f"{tot_imp:.2f}")
    fat_el.set("totale_iva", f"{tot_iva:.2f}")
    fat_el.set("totale_lordo", f"{tot_tot:.2f}")

    for f in fatture_list:
        lav = f.lavoro
        cli = lav.cliente if lav else None
        nome_cli = piva_cf = ""
        if cli:
            nome_cli = (
                cli.ragione_sociale if cli.tipo_cliente == "azienda"
                else f"{cli.nome or ''} {cli.cognome or ''}".strip()
            )
            piva_cf = cli.partita_iva or cli.codice_fiscale or ""
        fe = SubElement(fat_el, "Fattura")
        fe.set("numero", f"{f.anno}/{str(f.numero).zfill(3)}")
        fe.set("data", str(f.data_emissione))
        fe.set("cliente", nome_cli)
        fe.set("piva_cf", piva_cf)
        fe.set("imponibile", f"{float(f.importo_imponibile or 0):.2f}")
        fe.set("iva", f"{float(f.importo_iva or 0):.2f}")
        fe.set("totale", f"{float(f.importo_totale or 0):.2f}")
        fe.set("stato", f.stato or "emessa")

    pn_el = SubElement(root, "PrimaNota")
    entrate = sum(v.importo for v in voci_pn if v.tipo == "entrata")
    uscite = sum(v.importo for v in voci_pn if v.tipo == "uscita")
    pn_el.set("totale_entrate", f"{entrate:.2f}")
    pn_el.set("totale_uscite", f"{uscite:.2f}")
    pn_el.set("saldo", f"{entrate - uscite:.2f}")

    for v in sorted(voci_pn, key=lambda x: x.data):
        ve = SubElement(pn_el, "Voce")
        ve.set("data", str(v.data))
        ve.set("tipo", v.tipo)
        ve.set("importo", f"{v.importo:.2f}")
        ve.set("categoria", v.categoria or "")
        ve.set("descrizione", v.descrizione or "")

    raw = tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding=None)
    # minidom aggiunge la sua dichiarazione XML, la sostituiamo con encoding corretto
    lines = pretty.split("\n")
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines[1:])

    filename = f"contabilita_{anno_sel}.xml"
    return Response(
        content=xml_str.encode("utf-8"),
        media_type="application/xml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
