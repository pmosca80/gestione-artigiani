"""Test per app/services/backup.py — verifica integrità e alert."""

import gzip
from unittest.mock import MagicMock, patch

import pytest

from app.services.backup import (
    _dest_alert,
    _esegui,
    _invia_alert,
    _verifica_ripristino,
    esegui_backup,
    verifica_ripristino_backup,
)


# ── _dest_alert ──────────────────────────────────────────────────────────────

def test_dest_alert_da_ADMIN_EMAIL(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.delenv("MAIL_FROM", raising=False)
    assert _dest_alert() == "admin@example.com"


def test_dest_alert_da_MAIL_FROM_formato_nome(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.setenv("MAIL_FROM", "Mastro <noreply@app.com>")
    assert _dest_alert() == "noreply@app.com"


def test_dest_alert_vuoto_senza_env(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    assert _dest_alert() == ""


def test_dest_alert_ignora_stringa_senza_chiocciola(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "non-una-email")
    assert _dest_alert() == ""


# ── _invia_alert ─────────────────────────────────────────────────────────────

def test_invia_alert_chiama_invia_email(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    sent = {}

    def fake_invia(dest, oggetto, corpo):
        sent["dest"] = dest
        sent["oggetto"] = oggetto

    with patch("app.services.backup._dest_alert", return_value="admin@example.com"), \
         patch("app.services.email.smtp_configurato", return_value=True), \
         patch("app.services.email.invia_email", side_effect=fake_invia):
        _invia_alert("pg_dump fallito: connection refused")

    assert sent.get("dest") == "admin@example.com"
    assert "ALERT" in sent.get("oggetto", "")


def test_invia_alert_non_crasha_senza_email_configurata(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    with patch("app.services.backup._dest_alert", return_value="admin@example.com"), \
         patch("app.services.email.smtp_configurato", return_value=False):
        _invia_alert("errore qualsiasi")  # non deve sollevare eccezioni


def test_invia_alert_silenzioso_senza_destinatario(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    # non deve sollevare eccezioni
    _invia_alert("errore")


# ── _esegui — verifica integrità ─────────────────────────────────────────────

def _make_result(returncode=0, stdout=b"", stderr=b""):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_esegui_lancia_se_pg_dump_fallisce():
    dump_sql = b"-- SQL dump\nSELECT 1;" * 100
    with patch("subprocess.run", return_value=_make_result(returncode=1, stderr=b"auth error")):
        with pytest.raises(RuntimeError, match="pg_dump fallito"):
            _esegui("postgresql://u:p@host/db")


def test_esegui_lancia_se_stdout_vuoto():
    with patch("subprocess.run", return_value=_make_result(returncode=0, stdout=b"")):
        with pytest.raises(RuntimeError, match="output vuoto"):
            _esegui("postgresql://u:p@host/db")


def test_esegui_lancia_se_backup_troppo_piccolo():
    piccolo = b"x" * 10  # stdout presente ma minuscolo → gzip < 1 KB
    with patch("subprocess.run", return_value=_make_result(returncode=0, stdout=piccolo)):
        with pytest.raises(RuntimeError, match="piccolo"):
            _esegui("postgresql://u:p@host/db")


def test_esegui_carica_su_s3_se_dump_valido():
    import sys

    dump_sql = b"-- valid pg_dump output\n" + b"INSERT INTO t VALUES (1);\n" * 10

    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {"Contents": []}
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    mock_botocore = MagicMock()

    fake_modules = {
        "boto3": mock_boto3,
        "botocore": mock_botocore,
        "botocore.client": mock_botocore,
    }

    with patch("subprocess.run", return_value=_make_result(returncode=0, stdout=dump_sql)), \
         patch("app.services.backup._MIN_BACKUP_BYTES", 0), \
         patch.dict(sys.modules, fake_modules):
        _esegui("postgresql://u:p@host/db")

    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["ContentType"] == "application/gzip"
    assert call_kwargs["Key"].endswith(".sql.gz")


# ── esegui_backup — alert su errore ─────────────────────────────────────────

def test_esegui_backup_chiama_alert_se_pg_dump_fallisce(monkeypatch):
    monkeypatch.setenv("BACKUP_S3_BUCKET", "mybucket")
    monkeypatch.setenv("BACKUP_S3_KEY_ID", "key")
    monkeypatch.setenv("BACKUP_S3_SECRET", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")

    alert_ricevuti = []

    with patch("subprocess.run", return_value=_make_result(returncode=1, stderr=b"conn refused")), \
         patch("app.services.backup._invia_alert", side_effect=lambda m: alert_ricevuti.append(m)):
        esegui_backup()

    assert len(alert_ricevuti) == 1
    assert "pg_dump" in alert_ricevuti[0]


def test_esegui_backup_non_chiama_alert_se_non_configurato(monkeypatch):
    monkeypatch.delenv("BACKUP_S3_BUCKET", raising=False)
    monkeypatch.delenv("BACKUP_S3_KEY_ID", raising=False)
    monkeypatch.delenv("BACKUP_S3_SECRET", raising=False)

    alert_ricevuti = []
    with patch("app.services.backup._invia_alert", side_effect=lambda m: alert_ricevuti.append(m)):
        esegui_backup()

    assert len(alert_ricevuti) == 0


def test_esegui_backup_non_chiama_alert_se_db_non_postgres(monkeypatch):
    monkeypatch.setenv("BACKUP_S3_BUCKET", "b")
    monkeypatch.setenv("BACKUP_S3_KEY_ID", "k")
    monkeypatch.setenv("BACKUP_S3_SECRET", "s")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")

    alert_ricevuti = []
    with patch("app.services.backup._invia_alert", side_effect=lambda m: alert_ricevuti.append(m)):
        esegui_backup()

    assert len(alert_ricevuti) == 0


# ── _verifica_ripristino — verifica settimanale ──────────────────────────────

def _mock_s3_con_backup(dump_sql: bytes):
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {
        "Contents": [{"Key": "backup_2026-06-17_020000.sql.gz"}]
    }
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=gzip.compress(dump_sql)))
    }
    return mock_s3


def _fake_boto_modules(mock_s3):
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    mock_botocore = MagicMock()
    return {"boto3": mock_boto3, "botocore": mock_botocore, "botocore.client": mock_botocore}


def test_verifica_ripristino_lancia_se_nessun_backup_su_s3():
    import sys
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {"Contents": []}
    with patch.dict(sys.modules, _fake_boto_modules(mock_s3)):
        with pytest.raises(RuntimeError, match="Nessun backup"):
            _verifica_ripristino("postgresql://u:p@host/db")


def test_verifica_ripristino_lancia_se_dump_vuoto():
    import sys
    mock_s3 = _mock_s3_con_backup(b"")
    with patch.dict(sys.modules, _fake_boto_modules(mock_s3)):
        with pytest.raises(RuntimeError, match="vuoto"):
            _verifica_ripristino("postgresql://u:p@host/db")


def test_verifica_ripristino_lancia_se_creazione_db_fallisce():
    import sys
    mock_s3 = _mock_s3_con_backup(b"-- dump\nCREATE TABLE utenti(id int);\n")
    with patch.dict(sys.modules, _fake_boto_modules(mock_s3)), \
         patch("subprocess.run", return_value=_make_result(returncode=1, stderr=b"permission denied")):
        with pytest.raises(RuntimeError, match="Creazione DB temporaneo"):
            _verifica_ripristino("postgresql://u:p@host/db")


def _fake_run_factory(esito_ripristino=0, esito_count=0, stdout_count=b" 3\n"):
    chiamate = []

    def fake_run(cmd, **kwargs):
        chiamate.append(cmd)
        joined = " ".join(cmd)
        if "CREATE DATABASE" in joined:
            return _make_result(returncode=0)
        if "DROP DATABASE" in joined:
            return _make_result(returncode=0)
        if "SELECT count" in joined:
            return _make_result(returncode=esito_count, stdout=stdout_count, stderr=b"errore count")
        return _make_result(returncode=esito_ripristino, stderr=b"syntax error")  # ripristino (stdin)

    return chiamate, fake_run


def test_verifica_ripristino_lancia_se_ripristino_fallisce_e_pulisce_comunque():
    import sys
    mock_s3 = _mock_s3_con_backup(b"-- dump corrotto")
    chiamate, fake_run = _fake_run_factory(esito_ripristino=1)

    with patch.dict(sys.modules, _fake_boto_modules(mock_s3)), \
         patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="Ripristino di verifica fallito"):
            _verifica_ripristino("postgresql://u:p@host/db")

    drop_calls = [c for c in chiamate if "DROP DATABASE" in " ".join(c)]
    assert len(drop_calls) == 1  # cleanup eseguito anche dopo il fallimento


def test_verifica_ripristino_lancia_se_count_fallisce():
    import sys
    mock_s3 = _mock_s3_con_backup(b"-- dump\nCREATE TABLE utenti(id int);\n")
    _, fake_run = _fake_run_factory(esito_count=1)

    with patch.dict(sys.modules, _fake_boto_modules(mock_s3)), \
         patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="Verifica post-ripristino fallita"):
            _verifica_ripristino("postgresql://u:p@host/db")


def test_verifica_ripristino_successo_pulisce_db_temporaneo():
    import sys
    mock_s3 = _mock_s3_con_backup(b"-- dump valido\nCREATE TABLE utenti(id int);\n")
    chiamate, fake_run = _fake_run_factory(stdout_count=b" 5\n")

    with patch.dict(sys.modules, _fake_boto_modules(mock_s3)), \
         patch("subprocess.run", side_effect=fake_run):
        _verifica_ripristino("postgresql://u:p@host/db")  # non deve lanciare

    drop_calls = [c for c in chiamate if "DROP DATABASE" in " ".join(c)]
    assert len(drop_calls) == 1


# ── verifica_ripristino_backup — alert su errore ─────────────────────────────

def test_verifica_ripristino_backup_chiama_alert_se_fallisce(monkeypatch):
    monkeypatch.setenv("BACKUP_S3_BUCKET", "b")
    monkeypatch.setenv("BACKUP_S3_KEY_ID", "k")
    monkeypatch.setenv("BACKUP_S3_SECRET", "s")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")

    alert_ricevuti = []
    with patch("app.services.backup._verifica_ripristino", side_effect=RuntimeError("nessun backup trovato")), \
         patch("app.services.backup._invia_alert", side_effect=lambda m: alert_ricevuti.append(m)):
        verifica_ripristino_backup()

    assert len(alert_ricevuti) == 1
    assert "nessun backup trovato" in alert_ricevuti[0]


def test_verifica_ripristino_backup_non_chiama_alert_se_non_configurato(monkeypatch):
    monkeypatch.delenv("BACKUP_S3_BUCKET", raising=False)
    monkeypatch.delenv("BACKUP_S3_KEY_ID", raising=False)
    monkeypatch.delenv("BACKUP_S3_SECRET", raising=False)

    alert_ricevuti = []
    with patch("app.services.backup._invia_alert", side_effect=lambda m: alert_ricevuti.append(m)):
        verifica_ripristino_backup()

    assert len(alert_ricevuti) == 0


def test_verifica_ripristino_backup_non_chiama_alert_se_db_non_postgres(monkeypatch):
    monkeypatch.setenv("BACKUP_S3_BUCKET", "b")
    monkeypatch.setenv("BACKUP_S3_KEY_ID", "k")
    monkeypatch.setenv("BACKUP_S3_SECRET", "s")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")

    alert_ricevuti = []
    with patch("app.services.backup._invia_alert", side_effect=lambda m: alert_ricevuti.append(m)):
        verifica_ripristino_backup()

    assert len(alert_ricevuti) == 0
