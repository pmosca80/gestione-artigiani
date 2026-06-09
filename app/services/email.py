import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.logger import get_logger

logger = get_logger("email")


def invia_email(destinatario: str, oggetto: str, corpo: str) -> bool:
    username = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")
    mittente = os.getenv("MAIL_FROM", username)

    if not username or not password:
        logger.error("Credenziali email non configurate nel .env")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = oggetto
        msg["From"] = mittente
        msg["To"] = destinatario

        parte_testo = MIMEText(corpo, "html", "utf-8")
        msg.attach(parte_testo)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(username, password)
            server.sendmail(mittente, destinatario, msg.as_string())

        logger.info(f"Email inviata a {destinatario} | {oggetto}")
        return True

    except Exception as e:
        logger.error(f"Errore invio email a {destinatario} | {e}")
        return False