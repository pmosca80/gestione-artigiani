import os
from sqlalchemy.orm import Session

# ── Promo lancio "piano fondatore" ─────────────────────────────────
# Primo anno gratis, poi 50% a vita, per i primi 100 che si registrano
# (vedi auth.py::register). Il primo coupon si applica al checkout; il
# secondo lo applica app/services/fondatore.py quando il primo scade.
POSTI_FONDATORE_TOTALI = 100


def posti_fondatore_rimasti(db: Session) -> int:
    from app.models import Utente
    assegnati = db.query(Utente).filter(Utente.piano_fondatore == True).count()
    return max(0, POSTI_FONDATORE_TOTALI - assegnati)


def get_stripe_coupon_fondatore_anno() -> str:
    """Coupon 100% di sconto per i primi 12 mesi (applicato al checkout)."""
    return os.getenv("STRIPE_COUPON_FONDATORE_ANNO", "")


def get_stripe_coupon_fondatore_post() -> str:
    """Coupon 50% a vita applicato dopo la scadenza del primo anno gratis."""
    return os.getenv("STRIPE_COUPON_FONDATORE_POST", "")


# ── Limiti clienti per piano ──────────────────────────────────────
LIMITE_CLIENTI_FREE    = 5
LIMITE_CLIENTI_STARTER = 30

_LIMITE_CLIENTI = {
    "free":     LIMITE_CLIENTI_FREE,
    "starter":  LIMITE_CLIENTI_STARTER,
    "pro":      None,   # illimitati
    "business": None,   # illimitati
}

# ── Gerarchia piani ───────────────────────────────────────────────
_RANK = {"free": 0, "starter": 1, "pro": 2, "business": 3}

def _rank(piano: str) -> int:
    return _RANK.get(piano or "free", 0)


def get_piano(db: Session, user_id: int) -> str:
    from app.models import Utente
    u = db.query(Utente).filter(Utente.id == user_id).first()
    if not u:
        return "free"
    if u.username == "admin":
        return "business"
    return getattr(u, "piano", None) or "free"


def is_pro(db: Session, user_id: int) -> bool:
    """True per qualsiasi piano a pagamento (starter, pro, business)."""
    return _rank(get_piano(db, user_id)) >= _rank("starter")


# ── Feature flags per piano ───────────────────────────────────────

def ha_fatturapa(piano: str) -> bool:
    return _rank(piano) >= _rank("starter")


def ha_export(piano: str) -> bool:
    return _rank(piano) >= _rank("starter")


def ha_team(piano: str) -> bool:
    return _rank(piano) >= _rank("pro")


def ha_backup(piano: str) -> bool:
    return _rank(piano) >= _rank("pro")


def ha_email_invio(piano: str) -> bool:
    return _rank(piano) >= _rank("pro")


def max_collaboratori(piano: str) -> int | None:
    """None = illimitati, 0 = nessuno."""
    if piano == "business":
        return None
    if piano == "pro":
        return 3
    return 0


def get_limite_clienti(piano: str) -> int | None:
    """None = illimitati."""
    return _LIMITE_CLIENTI.get(piano or "free", LIMITE_CLIENTI_FREE)


def conta_clienti(db: Session, user_id: int) -> int:
    from app.models import Cliente
    return db.query(Cliente).filter(Cliente.utente_id == user_id).count()


def puo_aggiungere_cliente(db: Session, user_id: int) -> bool:
    piano = get_piano(db, user_id)
    limite = get_limite_clienti(piano)
    if limite is None:
        return True
    return conta_clienti(db, user_id) < limite


# ── Stripe ────────────────────────────────────────────────────────

def stripe_configurato() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def get_stripe_price_id(piano: str = "pro") -> str:
    mapping = {
        "starter":  os.getenv("STRIPE_PRICE_ID_STARTER", ""),
        "pro":      os.getenv("STRIPE_PRICE_ID_PRO", os.getenv("STRIPE_PRICE_ID", "")),
        "business": os.getenv("STRIPE_PRICE_ID_BUSINESS", ""),
    }
    return mapping.get(piano, "")


def get_base_url(request=None) -> str:
    base = os.getenv("BASE_URL", "")
    if base:
        return base.rstrip("/")
    if request:
        return str(request.base_url).rstrip("/")
    return "http://localhost:8000"
