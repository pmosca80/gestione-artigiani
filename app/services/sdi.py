import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from app.logger import get_logger

logger = get_logger("sdi")

SDI_PEC = "sdi01@pec.fatturapa.it"


def pec_configurata(azienda) -> bool:
    return bool(
        (azienda.pec_indirizzo or "").strip()
        and (azienda.pec_smtp_host or "").strip()
        and (azienda.pec_smtp_password or "").strip()
    )


def invia_xml_a_sdi(xml_bytes: bytes, nome_file: str, azienda) -> None:
    """
    Invia il file XML FatturaPA a SDI tramite PEC.
    Lancia eccezione in caso di errore (il chiamante gestisce il feedback all'utente).
    """
    pec_addr = (azienda.pec_indirizzo or "").strip()
    pec_host = (azienda.pec_smtp_host or "").strip()
    pec_port = int(azienda.pec_smtp_port or 465)
    pec_pass = (azienda.pec_smtp_password or "").strip()

    msg = MIMEMultipart()
    msg["From"] = pec_addr
    msg["To"] = SDI_PEC
    msg["Subject"] = nome_file

    part = MIMEBase("application", "xml")
    part.set_payload(xml_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{nome_file}"')
    msg.attach(part)

    if pec_port == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(pec_host, pec_port, context=ctx, timeout=30) as smtp:
            smtp.login(pec_addr, pec_pass)
            smtp.sendmail(pec_addr, SDI_PEC, msg.as_string())
    else:
        with smtplib.SMTP(pec_host, pec_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(pec_addr, pec_pass)
            smtp.sendmail(pec_addr, SDI_PEC, msg.as_string())

    logger.info(f"XML {nome_file} inviato a SDI da {pec_addr}")
