import os
from functools import wraps

from sqlalchemy import text

from app.database import engine
from app.logger import get_logger

logger = get_logger("scheduler_lock")

# ID stabili tra deploy — pg_try_advisory_lock vuole un bigint
_LOCK_IDS: dict[str, int] = {
    "controlla_scadenze": 1001,
    "controlla_fatture":  1002,
    "controlla_garanzie": 1003,
    "backup_giornaliero": 1004,
    "verifica_ripristino_backup": 1005,
}


def con_lock(nome_job: str):
    """Decoratore per job APScheduler: su PostgreSQL acquisisce un advisory lock.
    Se il lock è già preso da un'altra istanza il job viene saltato silenziosamente.
    Su SQLite (test/dev) esegue sempre, senza lock."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            db_url = os.getenv("DATABASE_URL", "")
            if not db_url.startswith("postgres"):
                return func(*args, **kwargs)

            lock_id = _LOCK_IDS.get(nome_job)
            if lock_id is None:
                logger.error(f"[{nome_job}] lock ID non registrato — eseguo senza lock")
                return func(*args, **kwargs)

            try:
                with engine.connect() as conn:
                    acquired = conn.execute(
                        text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id}
                    ).scalar()
                    if not acquired:
                        logger.info(f"[{nome_job}] skip — lock già preso da altra istanza")
                        return
                    # il lock si rilascia automaticamente alla chiusura della connessione
                    return func(*args, **kwargs)
            except Exception as exc:
                logger.error(f"[{nome_job}] errore advisory lock: {exc} — eseguo senza lock")
                return func(*args, **kwargs)

        return wrapper
    return decorator
