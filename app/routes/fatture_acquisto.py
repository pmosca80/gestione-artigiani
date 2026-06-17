from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.templates_config import templates
from app.services.audit import log_audit, get_actor, get_client_ip
from app.limiter import user_limiter
from app.validators import DESCRIZIONE_MAX, NOTE_MAX, CATEGORIA_MAX, NUMERO_FATTURA_MAX, clean

router = APIRouter(prefix="/fatture-acquisto", tags=["fatture-acquisto"])

_CATEGORIE = ["materiali", "subappalto", "carburante", "attrezzatura", "utenze", "varie"]


@router.get("/", response_class=HTMLResponse)
def lista_fatture_acquisto(
    request: Request,
    anno: int | None = None,
    fornitore_id: int | None = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    anni = crud.get_anni_fatture_acquisto(db, user_id)
    anno_sel = anno or (anni[0] if anni else date.today().year)

    fatture = crud.get_fatture_acquisto(db, user_id, anno=anno_sel, fornitore_id=fornitore_id or None)
    fornitori = crud.get_fornitori(db, user_id)

    tot_imponibile = sum(f.importo_imponibile or 0 for f in fatture)
    tot_iva = sum(f.importo_iva or 0 for f in fatture)
    tot_totale = sum(f.importo_totale or 0 for f in fatture)
    tot_da_pagare = sum(f.importo_totale or 0 for f in fatture if f.stato_pagamento == "da_pagare")

    return templates.TemplateResponse(
        request=request,
        name="fatture_acquisto.html",
        context={
            "fatture": fatture,
            "fornitori": fornitori,
            "anni": anni,
            "anno_sel": anno_sel,
            "fornitore_id": fornitore_id or 0,
            "tot_imponibile": tot_imponibile,
            "tot_iva": tot_iva,
            "tot_totale": tot_totale,
            "tot_da_pagare": tot_da_pagare,
            "categorie": _CATEGORIE,
            "oggi": date.today().isoformat(),
        },
    )


@router.post("/", response_class=RedirectResponse)
@user_limiter.limit("30/minute")
def crea_fattura(
    request: Request,
    data_fattura: str = Form(...),
    descrizione: str = Form(...),
    importo_imponibile: str = Form("0"),
    aliquota_iva: float = Form(22.0),
    numero_fattura: str = Form(""),
    categoria: str = Form(""),
    fornitore_id: int = Form(0),
    lavoro_id: int = Form(0),
    data_scadenza: str = Form(""),
    note: str = Form(""),
    anno_redirect: int = Form(0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    try:
        imponibile = float(importo_imponibile.replace(",", "."))
    except (ValueError, TypeError):
        imponibile = 0.0

    aliq = float(aliquota_iva)
    iva = round(imponibile * aliq / 100, 2)
    totale = round(imponibile + iva, 2)

    desc_ok = clean(descrizione, DESCRIZIONE_MAX)
    if imponibile > 0 and desc_ok:
        fa = crud.crea_fattura_acquisto(
            db,
            utente_id=user_id,
            data_fattura=data_fattura,
            descrizione=desc_ok,
            importo_imponibile=imponibile,
            aliquota_iva=aliq,
            importo_iva=iva,
            importo_totale=totale,
            numero_fattura=clean(numero_fattura, NUMERO_FATTURA_MAX),
            categoria=clean(categoria, CATEGORIA_MAX),
            fornitore_id=fornitore_id or None,
            lavoro_id=lavoro_id or None,
            data_scadenza=data_scadenza,
            note=clean(note, NOTE_MAX),
        )
        attore_id, attore_username = get_actor(request, db)
        log_audit(db, user_id, attore_id, attore_username,
                  "crea_fattura_acquisto", "fatture_acquisto", fa.id,
                  {"imponibile": imponibile, "iva": iva, "totale": totale,
                   "descrizione": desc_ok[:80]},
                  get_client_ip(request))

    anno = anno_redirect or int(data_fattura[:4])
    return RedirectResponse(url=f"/fatture-acquisto/?anno={anno}", status_code=303)


@router.post("/{fa_id}/elimina", response_class=RedirectResponse)
def elimina(
    request: Request,
    fa_id: int,
    anno: int = Form(0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    fa = crud.get_fattura_acquisto_by_id(db, fa_id, user_id)
    det = {"totale": float(fa.importo_totale or 0), "descrizione": (fa.descrizione or "")[:80]} if fa else {}
    crud.elimina_fattura_acquisto(db, fa_id, user_id)
    attore_id, attore_username = get_actor(request, db)
    log_audit(db, user_id, attore_id, attore_username,
              "elimina_fattura_acquisto", "fatture_acquisto", fa_id, det,
              get_client_ip(request))
    return RedirectResponse(
        url=f"/fatture-acquisto/?anno={anno or date.today().year}",
        status_code=303,
    )


@router.post("/{fa_id}/paga", response_class=RedirectResponse)
def paga(
    request: Request,
    fa_id: int,
    data_pagamento: str = Form(""),
    metodo_pagamento: str = Form(""),
    anno: int = Form(0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    data_pag = data_pagamento or date.today().isoformat()
    crud.marca_pagata_fattura_acquisto(
        db, fa_id, user_id,
        data_pagamento=data_pag,
        metodo=metodo_pagamento,
    )
    attore_id, attore_username = get_actor(request, db)
    log_audit(db, user_id, attore_id, attore_username,
              "pagamento_fattura_acquisto", "fatture_acquisto", fa_id,
              {"data_pagamento": data_pag, "metodo": metodo_pagamento or "—"},
              get_client_ip(request))
    return RedirectResponse(
        url=f"/fatture-acquisto/?anno={anno or date.today().year}",
        status_code=303,
    )
