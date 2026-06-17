import gzip
import os
import subprocess
from datetime import datetime, timezone

from app.logger import get_logger
from app.services.scheduler_lock import con_lock

logger = get_logger("backup")

RETENTION = 30
_MIN_BACKUP_BYTES = 1024  # un pg_dump reale è sempre > 1 KB


def _configurato() -> bool:
    return bool(
        os.getenv("BACKUP_S3_BUCKET")
        and os.getenv("BACKUP_S3_KEY_ID")
        and os.getenv("BACKUP_S3_SECRET")
    )


def _dest_alert() -> str:
    """Restituisce l'indirizzo email per gli alert di sistema, o stringa vuota."""
    dest = os.getenv("ADMIN_EMAIL") or os.getenv("MAIL_FROM", "")
    if not dest:
        return ""
    if "<" in dest and ">" in dest:
        dest = dest.split("<")[1].rstrip(">").strip()
    return dest if "@" in dest else ""


def _invia_alert(messaggio: str) -> None:
    """Invia email di alert quando il backup fallisce."""
    dest = _dest_alert()
    if not dest:
        return
    try:
        from app.services.email import invia_email, smtp_configurato
        if not smtp_configurato():
            return
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        corpo = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#fff7ed;padding:24px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:12px;
     border-left:4px solid #dc2626;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
  <h2 style="color:#dc2626;margin:0 0 16px;">Backup fallito &mdash; Mastro</h2>
  <p style="color:#374151;margin:0 0 12px;"><strong>Data/ora:</strong> {ts}</p>
  <p style="color:#374151;margin:0 0 12px;"><strong>Errore:</strong></p>
  <pre style="background:#fef2f2;border-radius:8px;padding:12px;font-size:13px;
       color:#991b1b;overflow-x:auto;white-space:pre-wrap;">{messaggio}</pre>
  <p style="color:#6b7280;font-size:13px;margin:16px 0 0;">
    Accedi al server per verificare lo stato del database.
  </p>
</div>
</body></html>"""
        invia_email(dest, "ALERT: Backup Mastro fallito", corpo)
    except Exception as e:
        logger.warning(f"Impossibile inviare alert backup: {e}")


@con_lock("backup_giornaliero")
def esegui_backup() -> None:
    """Backup giornaliero: pg_dump → gzip → S3. Non lancia mai eccezioni."""
    if not _configurato():
        logger.warning("Backup saltato: BACKUP_S3_BUCKET/KEY_ID/SECRET non configurati")
        return

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or not db_url.startswith("postgres"):
        logger.warning("Backup saltato: DATABASE_URL non configurata o non PostgreSQL")
        return

    try:
        _esegui(db_url)
    except Exception as e:
        msg = str(e)
        logger.error(f"Backup fallito: {msg}")
        _invia_alert(msg)


def _esegui(db_url: str) -> None:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    nome_file = f"backup_{ts}.sql.gz"

    result = subprocess.run(
        ["pg_dump", "--no-owner", "--no-acl", db_url],
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump fallito: {result.stderr.decode()[:400]}")

    if not result.stdout:
        raise RuntimeError("pg_dump ha prodotto output vuoto")

    dati_gz = gzip.compress(result.stdout, compresslevel=6)

    if len(dati_gz) < _MIN_BACKUP_BYTES:
        raise RuntimeError(
            f"Backup sospettosamente piccolo ({len(dati_gz)} byte) — dump non affidabile"
        )

    import boto3
    from botocore.client import Config

    endpoint = os.getenv("BACKUP_S3_ENDPOINT") or None
    region = os.getenv("BACKUP_S3_REGION", "auto")
    bucket = os.getenv("BACKUP_S3_BUCKET")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("BACKUP_S3_KEY_ID"),
        aws_secret_access_key=os.getenv("BACKUP_S3_SECRET"),
        region_name=region,
        config=Config(signature_version="s3v4"),
    )

    s3.put_object(
        Bucket=bucket,
        Key=nome_file,
        Body=dati_gz,
        ContentType="application/gzip",
    )
    logger.info(f"Backup caricato: {nome_file} ({len(dati_gz) / 1024 / 1024:.2f} MB)")

    _pulisci_vecchi(s3, bucket)


def _pulisci_vecchi(s3, bucket: str) -> None:
    try:
        risposta = s3.list_objects_v2(Bucket=bucket, Prefix="backup_")
        oggetti = sorted(risposta.get("Contents", []), key=lambda o: o["Key"], reverse=True)
        for obj in oggetti[RETENTION:]:
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
            logger.info(f"Backup vecchio rimosso: {obj['Key']}")
    except Exception as e:
        logger.warning(f"Pulizia backup fallita: {e}")
