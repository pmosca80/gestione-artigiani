from datetime import date
from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app import crud
from app.templates_config import templates

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
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    try:
        imp = float(importo.replace(",", "."))
    except (ValueError, TypeError):
        imp = 0.0

    if imp > 0 and descrizione.strip():
        crud.crea_voce_prima_nota(
            db, user_id,
            data=data,
            descrizione=descrizione.strip(),
            importo=round(imp, 2),
            tipo=tipo if tipo in ("entrata", "uscita") else "uscita",
            categoria=categoria or None,
            lavoro_id=lavoro_id or None,
            cliente_id=cliente_id or None,
        )

    redirect_mese = mese or int(data[5:7])
    redirect_anno = anno or int(data[:4])
    return RedirectResponse(
        url=f"/prima-nota/?anno={redirect_anno}&mese={redirect_mese}",
        status_code=303,
    )


@router.post("/{voce_id}/elimina")
def elimina_voce(
    voce_id: int,
    anno: int = Form(0),
    mese: int = Form(0),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    crud.elimina_voce_prima_nota(db, voce_id, user_id)
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
