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


def _s3_client():
    import boto3
    from botocore.client import Config

    endpoint = os.getenv("BACKUP_S3_ENDPOINT") or None
    region = os.getenv("BACKUP_S3_REGION", "auto")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("BACKUP_S3_KEY_ID"),
        aws_secret_access_key=os.getenv("BACKUP_S3_SECRET"),
        region_name=region,
        config=Config(signature_version="s3v4"),
    )


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

    bucket = os.getenv("BACKUP_S3_BUCKET")
    s3 = _s3_client()

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


@con_lock("verifica_ripristino_backup")
def verifica_ripristino_backup() -> None:
    """Settimanale: scarica l'ultimo backup, lo ripristina in un DB temporaneo e verifica
    che sia effettivamente leggibile. Un backup integro che non si ripristina è un
    incidente silenzioso — questo job lo rende visibile. Non lancia mai eccezioni."""
    if not _configurato():
        logger.warning("Verifica ripristino saltata: backup non configurato")
        return

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url or not db_url.startswith("postgres"):
        logger.warning("Verifica ripristino saltata: DATABASE_URL non configurata o non PostgreSQL")
        return

    try:
        _verifica_ripristino(db_url)
    except Exception as e:
        msg = str(e)
        logger.error(f"Verifica ripristino backup fallita: {msg}")
        _invia_alert(f"Verifica ripristino backup fallita: {msg}")


def _verifica_ripristino(db_url: str) -> None:
    import secrets
    from urllib.parse import urlparse, urlunparse

    bucket = os.getenv("BACKUP_S3_BUCKET")
    s3 = _s3_client()

    risposta = s3.list_objects_v2(Bucket=bucket, Prefix="backup_")
    oggetti = sorted(risposta.get("Contents", []), key=lambda o: o["Key"], reverse=True)
    if not oggetti:
        raise RuntimeError("Nessun backup trovato su S3 da verificare")

    ultima_key = oggetti[0]["Key"]
    corpo = s3.get_object(Bucket=bucket, Key=ultima_key)["Body"].read()
    dump_sql = gzip.decompress(corpo)

    if not dump_sql:
        raise RuntimeError(f"Backup {ultima_key} vuoto dopo decompressione")

    parsed = urlparse(db_url)
    nome_db_temp = f"backup_verify_{secrets.token_hex(6)}"
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    temp_url = urlunparse(parsed._replace(path=f"/{nome_db_temp}"))

    crea = subprocess.run(
        ["psql", admin_url, "-v", "ON_ERROR_STOP=1", "-c", f'CREATE DATABASE "{nome_db_temp}";'],
        capture_output=True,
        timeout=60,
    )
    if crea.returncode != 0:
        raise RuntimeError(f"Creazione DB temporaneo di verifica fallita: {crea.stderr.decode()[:300]}")

    try:
        ripristino = subprocess.run(
            ["psql", temp_url, "-v", "ON_ERROR_STOP=1"],
            input=dump_sql,
            capture_output=True,
            timeout=300,
        )
        if ripristino.returncode != 0:
            raise RuntimeError(
                f"Ripristino di verifica fallito (backup {ultima_key}): {ripristino.stderr.decode()[:400]}"
            )

        verifica = subprocess.run(
            ["psql", temp_url, "-t", "-c", "SELECT count(*) FROM utenti;"],
            capture_output=True,
            timeout=30,
        )
        if verifica.returncode != 0:
            raise RuntimeError(f"Verifica post-ripristino fallita: {verifica.stderr.decode()[:300]}")
        try:
            righe = int(verifica.stdout.decode().strip())
        except ValueError:
            raise RuntimeError("Verifica post-ripristino: output inatteso da psql")

        logger.info(f"Verifica ripristino OK — backup {ultima_key}, tabella utenti: {righe} righe")
    finally:
        subprocess.run(
            ["psql", admin_url, "-c", f'DROP DATABASE IF EXISTS "{nome_db_temp}";'],
            capture_output=True,
            timeout=60,
        )
