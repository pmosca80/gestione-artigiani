import gzip
import os
import subprocess
from datetime import datetime, timezone

from app.logger import get_logger
from app.services.scheduler_lock import con_lock

logger = get_logger("backup")

RETENTION = 30  # numero di backup da mantenere


def _configurato() -> bool:
    return bool(
        os.getenv("BACKUP_S3_BUCKET")
        and os.getenv("BACKUP_S3_KEY_ID")
        and os.getenv("BACKUP_S3_SECRET")
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
        logger.error(f"Backup fallito: {e}")


def _esegui(db_url: str) -> None:
    import boto3
    from botocore.client import Config

    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    nome_file = f"backup_{ts}.sql.gz"

    # pg_dump con timeout 5 min
    result = subprocess.run(
        ["pg_dump", "--no-owner", "--no-acl", db_url],
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump fallito: {result.stderr.decode()[:400]}")

    dati_gz = gzip.compress(result.stdout, compresslevel=6)

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
    logger.info(f"Backup caricato: {nome_file} ({len(dati_gz)/1024/1024:.2f} MB)")

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
