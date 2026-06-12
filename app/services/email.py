import os
import smtplib
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from app.logger import get_logger

logger = get_logger("email")


def smtp_configurato() -> bool:
    """True se le variabili SMTP sono impostate."""
    return bool(
        os.getenv("MAIL_USERNAME") or os.getenv("SMTP_USER")
    ) and bool(
        os.getenv("MAIL_PASSWORD") or os.getenv("SMTP_PASSWORD")
    )


def _smtp_settings() -> dict:
    """Legge le variabili env SMTP, accetta sia MAIL_* che SMTP_*."""
    return {
        "host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME", ""),
        "password": os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD", ""),
        "from":     os.getenv("MAIL_FROM") or os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME", ""),
    }


def invia_email(destinatario: str, oggetto: str, corpo: str) -> bool:
    """Invia email HTML semplice (funzione originale, mantenuta)."""
    cfg = _smtp_settings()
    if not cfg["user"] or not cfg["password"]:
        logger.error("Credenziali email non configurate")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = oggetto
        msg["From"] = cfg["from"]
        msg["To"] = destinatario
        msg.attach(MIMEText(corpo, "html", "utf-8"))
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            s.ehlo()
            s.starttls()
            s.login(cfg["user"], cfg["password"])
            s.sendmail(cfg["from"], destinatario, msg.as_string())
        logger.info(f"Email inviata a {destinatario} — {oggetto}")
        return True
    except Exception as e:
        logger.error(f"Errore invio email: {e}")
        return False


def invia_fattura_xml(
    *,
    to_email: str,
    to_nome: str,
    from_nome: str,
    numero_fattura: str,
    data_emissione: str,
    importo_totale: float,
    xml_bytes: bytes,
    nome_file: str,
) -> None:
    """
    Invia la FatturaPA XML via email con allegato.
    Lancia RuntimeError se SMTP non è configurato o l'invio fallisce.
    """
    cfg = _smtp_settings()
    if not cfg["user"] or not cfg["password"]:
        raise RuntimeError(
            "SMTP non configurato. Imposta MAIL_USERNAME e MAIL_PASSWORD "
            "(o SMTP_USER / SMTP_PASSWORD) nelle variabili d'ambiente."
        )

    msg = MIMEMultipart()
    msg["Subject"] = f"Fattura n. {numero_fattura} — {from_nome}"
    msg["From"] = f"{from_nome} <{cfg['from']}>"
    msg["To"] = f"{to_nome} <{to_email}>"

    corpo = (
        f"Gentile {to_nome},\n\n"
        f"in allegato trova la FatturaPA elettronica n. {numero_fattura} "
        f"del {data_emissione}.\n\n"
        f"  Importo totale: € {importo_totale:.2f}\n\n"
        "Il file XML è conforme allo standard FatturaPA FPR12 e può essere\n"
        "consegnato al proprio intermediario o commercialista per l'inoltro\n"
        "al Sistema di Interscambio (SDI).\n\n"
        f"Cordiali saluti,\n{from_nome}\n"
    )
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    allegato = MIMEBase("application", "xml")
    allegato.set_payload(xml_bytes)
    encoders.encode_base64(allegato)
    allegato.add_header("Content-Disposition", "attachment", filename=nome_file)
    msg.attach(allegato)

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            s.ehlo()
            s.starttls()
            s.login(cfg["user"], cfg["password"])
            s.sendmail(cfg["from"], to_email, msg.as_string())
        logger.info(f"FatturaPA {nome_file} inviata a {to_email}")
    except Exception as e:
        logger.error(f"Errore invio FatturaPA a {to_email}: {e}")
        raise RuntimeError(f"Invio fallito: {e}") from e
