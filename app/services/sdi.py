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


def invia_automatico(
    db, azienda, lavoro, fattura, *,
    tipo_documento="TD01", fattura_rif_numero=None, fattura_rif_anno=None,
) -> None:
    """
    Se l'invio automatico è abilitato nelle impostazioni e la PEC è configurata,
    genera l'XML e lo invia subito a SDI. Non lancia mai eccezioni: un fallimento
    dell'invio automatico non deve bloccare la creazione della fattura — l'utente
    può sempre inviarla manualmente in seguito dal registro fatture.
    """
    if not getattr(azienda, "invio_automatico_sdi", False) or not pec_configurata(azienda):
        return
    try:
        from app import crud
        from app.services.fatturapa import genera_xml_fatturapa, nome_file_fatturapa

        voci = crud.get_voci_preventivo(db, azienda.utente_id, lavoro.id)
        xml_bytes = genera_xml_fatturapa(
            lavoro, lavoro.cliente, azienda, voci=voci or None,
            tipo_documento=tipo_documento,
            fattura_rif_numero=fattura_rif_numero, fattura_rif_anno=fattura_rif_anno,
        )
        nome_file = fattura.nome_file or nome_file_fatturapa(azienda, lavoro)
        invia_xml_a_sdi(xml_bytes, nome_file, azienda)
        fattura.stato = "inviata_sdi"
        db.commit()
        logger.info(f"Fattura {fattura.id} inviata automaticamente a SDI")
    except Exception as e:
        logger.warning(f"Invio automatico SDI fallito per fattura {fattura.id}: {e}")
