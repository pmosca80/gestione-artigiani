from datetime import date
from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.templates_config import templates
from app.services.audit import log_audit, get_actor, get_client_ip
from app.limiter import user_limiter
from app.validators import DESCRIZIONE_MAX, NOTE_MAX, CATEGORIA_MAX, clean

router = APIRouter(prefix="/prima-nota", tags=["prima-nota"])

_CATEGORIE = ["carburante", "materiali", "attrezzatura", "compenso", "varie"]


@router.get("/", response_class=HTMLResponse)
def prima_nota_lista(
    request: Request,
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    oggi = date.today()
    anno = anno or oggi.year
    mese = mese or oggi.month

    voci = crud.get_prima_nota(db, user_id, anno=anno, mese=mese)

    # Raggruppa per giorno
    per_giorno: dict[str, list] = defaultdict(list)
    for v in voci:
        per_giorno[v.data].append(v)
    giorni = sorted(per_giorno.keys(), reverse=True)

    # Totali mese
    entrate_mese = sum(v.importo for v in voci if v.tipo == "entrata")
    uscite_mese  = sum(v.importo for v in voci if v.tipo == "uscita")
    saldo_mese   = entrate_mese - uscite_mese

    return templates.TemplateResponse(
        request=request,
        name="prima_nota.html",
        context={
            "voci": voci,
            "per_giorno": per_giorno,
            "giorni": giorni,
            "anno": anno,
            "mese": mese,
            "entrate_mese": entrate_mese,
            "uscite_mese": uscite_mese,
            "saldo_mese": saldo_mese,
            "oggi": oggi.isoformat(),
            "categorie": _CATEGORIE,
            "mesi_nomi": ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
                          "Lug", "Ago", "Set", "Ott", "Nov", "Dic"],
        },
    )


@router.post("/", response_class=RedirectResponse)
@user_limiter.limit("30/minute")
def aggiungi_voce(
    request: Request,
    data: str = Form(...),
    descrizione: str = Form(...),
    importo: str = Form(...),
    tipo: str = Form("uscita"),
    categoria: str = Form(""),
    lavoro_id: int = Form(0),
    cliente_id: int = Form(0),
    anno: int = Form(0),
    mese: int = Form(0),
    aliquota_iva: float = Form(0.0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    try:
        imp = float(importo.replace(",", "."))
    except (ValueError, TypeError):
        imp = 0.0

    desc_ok = clean(descrizione, DESCRIZIONE_MAX)
    cat_ok = clean(categoria, CATEGORIA_MAX) or None
    if imp > 0 and desc_ok:
        tipo_ok = tipo if tipo in ("entrata", "uscita") else "uscita"
        # IVA a credito solo su uscite con aliquota > 0
        # Calcola la quota IVA dal totale pagato: iva = totale * aliq / (100 + aliq)
        iva_calc = 0.0
        aliq = float(aliquota_iva) if aliquota_iva else 0.0
        if tipo_ok == "uscita" and aliq > 0:
            iva_calc = round(imp * aliq / (100.0 + aliq), 2)
        voce = crud.crea_voce_prima_nota(
            db, user_id,
            data=data,
            descrizione=desc_ok,
            importo=round(imp, 2),
            tipo=tipo_ok,
            categoria=cat_ok,
            lavoro_id=lavoro_id or None,
            cliente_id=cliente_id or None,
            aliquota_iva=aliq,
            importo_iva=iva_calc,
        )
        attore_id, attore_username = get_actor(request, db)
        log_audit(db, user_id, attore_id, attore_username,
                  "crea_prima_nota", "prima_nota", voce.id,
                  {"tipo": tipo_ok, "importo": round(imp, 2),
                   "descrizione": desc_ok[:80]},
                  get_client_ip(request))

    redirect_mese = mese or int(data[5:7])
    redirect_anno = anno or int(data[:4])
    return RedirectResponse(
        url=f"/prima-nota/?anno={redirect_anno}&mese={redirect_mese}",
        status_code=303,
    )


@router.post("/{voce_id}/elimina")
def elimina_voce(
    request: Request,
    voce_id: int,
    anno: int = Form(0),
    mese: int = Form(0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    from app.models import VocePrimaNota
    voce = db.query(VocePrimaNota).filter(
        VocePrimaNota.id == voce_id, VocePrimaNota.utente_id == user_id
    ).first()
    det = {"tipo": voce.tipo, "importo": float(voce.importo or 0),
           "descrizione": (voce.descrizione or "")[:80]} if voce else {}
    crud.elimina_voce_prima_nota(db, voce_id, user_id)
    attore_id, attore_username = get_actor(request, db)
    log_audit(db, user_id, attore_id, attore_username,
              "elimina_prima_nota", "prima_nota", voce_id, det,
              get_client_ip(request))
    oggi = date.today()
    return RedirectResponse(
        url=f"/prima-nota/?anno={anno or oggi.year}&mese={mese or oggi.month}",
        status_code=303,
    )


@router.get("/export.csv")
def export_csv(
    anno: int | None = None,
    mese: int | None = None,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    oggi = date.today()
    anno = anno or oggi.year
    voci = crud.get_prima_nota(db, user_id, anno=anno, mese=mese)

    righe = ["Data,Descrizione,Tipo,Categoria,Importo"]
    for v in sorted(voci, key=lambda x: x.data):
        imp = f"{v.importo:.2f}" if v.tipo == "entrata" else f"-{v.importo:.2f}"
        desc = v.descrizione.replace('"', "'") if v.descrizione else ""
        righe.append(f'{v.data},"{desc}",{v.tipo},{v.categoria or ""},{imp}')

    content = "﻿" + "\n".join(righe)
    filename = f"prima_nota_{anno}_{mese:02d}.csv" if mese else f"prima_nota_{anno}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
