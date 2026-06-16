import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user
from app.models import AuditLog, Utente
from app.templates_config import templates

router = APIRouter(prefix="/audit", tags=["audit"])

_AZIONI_LABEL = {
    "crea_lavoro": "Crea lavoro",
    "modifica_lavoro": "Modifica lavoro",
    "emette_fattura": "Emissione fattura",
    "pagamento_fattura": "Pagamento fattura",
    "nota_credito": "Nota di credito",
    "stato_fattura": "Stato fattura (SDI)",
    "crea_fattura_acquisto": "Crea fattura acquisto",
    "modifica_fattura_acquisto": "Modifica fattura acquisto",
    "pagamento_fattura_acquisto": "Pagamento fattura acquisto",
    "elimina_fattura_acquisto": "Elimina fattura acquisto",
    "crea_prima_nota": "Crea voce prima nota",
    "elimina_prima_nota": "Elimina voce prima nota",
}

_TABELLA_LABEL = {
    "lavori": "Lavori",
    "fatture_emesse": "Fatture emesse",
    "fatture_acquisto": "Fatture acquisto",
    "prima_nota": "Prima nota",
}


@router.get("/", response_class=HTMLResponse)
def lista_audit(
    request: Request,
    tabella: str = "",
    azione: str = "",
    attore: str = "",
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    utente = db.query(Utente).filter(Utente.id == user_id).first()
    if utente and utente.titolare_id:
        return RedirectResponse("/", status_code=303)

    q = db.query(AuditLog).filter(AuditLog.utente_id == user_id)
    if tabella:
        q = q.filter(AuditLog.tabella == tabella)
    if azione:
        q = q.filter(AuditLog.azione == azione)
    if attore:
        q = q.filter(AuditLog.attore_username.ilike(f"%{attore}%"))

    eventi = q.order_by(AuditLog.timestamp.desc()).limit(500).all()

    collaboratori = db.query(Utente).filter(Utente.titolare_id == user_id).all()

    parsed = []
    for e in eventi:
        det = {}
        if e.dettaglio:
            try:
                det = json.loads(e.dettaglio)
            except Exception:
                det = {}
        parsed.append({
            "id": e.id,
            "timestamp": e.timestamp,
            "attore_username": e.attore_username,
            "azione": e.azione,
            "azione_label": _AZIONI_LABEL.get(e.azione, e.azione),
            "tabella": e.tabella,
            "tabella_label": _TABELLA_LABEL.get(e.tabella, e.tabella),
            "record_id": e.record_id,
            "dettaglio": det,
            "ip": e.ip,
        })

    return templates.TemplateResponse(
        request=request,
        name="audit.html",
        context={
            "eventi": parsed,
            "collaboratori": collaboratori,
            "tabella_sel": tabella,
            "azione_sel": azione,
            "attore_sel": attore,
            "azioni_label": _AZIONI_LABEL,
            "tabelle_label": _TABELLA_LABEL,
            "tot": len(parsed),
        },
    )
