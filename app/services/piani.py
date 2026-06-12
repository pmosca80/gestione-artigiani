import os
from sqlalchemy.orm import Session

LIMITE_CLIENTI_FREE = 5


def get_piano(db: Session, user_id: int) -> str:
    from app.models import Utente
    u = db.query(Utente).filter(Utente.id == user_id).first()
    return (getattr(u, "piano", None) or "free") if u else "free"


def is_pro(db: Session, user_id: int) -> bool:
    return get_piano(db, user_id) == "pro"


def conta_clienti(db: Session, user_id: int) -> int:
    from app.models import Cliente
    return db.query(Cliente).filter(Cliente.utente_id == user_id).count()


def puo_aggiungere_cliente(db: Session, user_id: int) -> bool:
    if is_pro(db, user_id):
        return True
    return conta_clienti(db, user_id) < LIMITE_CLIENTI_FREE


def stripe_configurato() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def get_stripe_price_id() -> str:
    return os.getenv("STRIPE_PRICE_ID", "")


def get_base_url(request=None) -> str:
    base = os.getenv("BASE_URL", "")
    if base:
        return base.rstrip("/")
    if request:
        return str(request.base_url).rstrip("/")
    return "http://localhost:8000"
