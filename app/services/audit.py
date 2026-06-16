import json
from datetime import datetime
from sqlalchemy.orm import Session


def get_actor(request, db: Session) -> tuple[int, str]:
    """Restituisce (attore_id, attore_username) — il vero utente loggato in sessione.

    Diverso da get_current_user: per i collaboratori restituisce il loro ID,
    non quello del titolare. Serve per sapere CHI ha eseguito l'azione.
    """
    from app.models import Utente
    raw_id = request.session.get("user_id")
    if not raw_id:
        return 0, "—"
    utente = db.query(Utente).filter(Utente.id == raw_id).first()
    return raw_id, (utente.username if utente else "—")


def log_audit(
    db: Session,
    utente_id: int,
    attore_id: int,
    attore_username: str,
    azione: str,
    tabella: str,
    record_id: int | None = None,
    dettaglio: dict | None = None,
    ip: str | None = None,
) -> None:
    """Registra un evento nell'audit log. Non solleva mai eccezioni."""
    from app.models import AuditLog
    try:
        entry = AuditLog(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            utente_id=utente_id,
            attore_id=attore_id,
            attore_username=attore_username,
            azione=azione,
            tabella=tabella,
            record_id=record_id,
            dettaglio=json.dumps(dettaglio, ensure_ascii=False) if dettaglio else None,
            ip=ip,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()


def get_client_ip(request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", None)
