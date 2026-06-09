from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Lavoro, Utente, ImpostazioniAzienda
from app.services.email import invia_email
from app.logger import get_logger

logger = get_logger("notifiche")


def controlla_scadenze():
    logger.info("Controllo scadenze pagamenti in corso...")

    db: Session = SessionLocal()

    try:
        oggi = datetime.now().date()
        tra_7_giorni = oggi + timedelta(days=7)

        lavori_in_scadenza = db.query(Lavoro).filter(
            Lavoro.stato_pagamento != "pagato",
            Lavoro.residuo_pagamento > 0,
            Lavoro.data_scadenza_pagamento != None,
        ).all()

        contatore = 0

        for lavoro in lavori_in_scadenza:
            try:
                scadenza = datetime.strptime(
                    lavoro.data_scadenza_pagamento, "%Y-%m-%d"
                ).date()
            except:
                continue

            giorni_mancanti = (scadenza - oggi).days

            if giorni_mancanti not in [7, 3, 1, 0, -1, -3, -7]:
                continue

            utente = db.query(Utente).filter(
                Utente.id == lavoro.utente_id
            ).first()

            if not utente:
                continue

            azienda = db.query(ImpostazioniAzienda).filter(
                ImpostazioniAzienda.utente_id == lavoro.utente_id
            ).first()

            email_utente = azienda.email if azienda else None

            if not email_utente:
                continue

            cliente = lavoro.cliente
            nome_cliente = f"{cliente.nome or ''} {cliente.cognome or ''}".strip()
            if cliente.ragione_sociale:
                nome_cliente = cliente.ragione_sociale

            if giorni_mancanti > 0:
                stato_testo = f"scade tra {giorni_mancanti} giorni ({scadenza.strftime('%d/%m/%Y')})"
                oggetto = f"⚠️ Pagamento in scadenza: {nome_cliente}"
            elif giorni_mancanti == 0:
                stato_testo = "scade OGGI"
                oggetto = f"🔴 Pagamento scade oggi: {nome_cliente}"
            else:
                stato_testo = f"scaduto da {abs(giorni_mancanti)} giorni ({scadenza.strftime('%d/%m/%Y')})"
                oggetto = f"❌ Pagamento scaduto: {nome_cliente}"

            corpo = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Promemoria pagamento</h2>
                <p>Il pagamento per il lavoro <strong>{lavoro.titolo}</strong>
                di <strong>{nome_cliente}</strong> {stato_testo}.</p>
                <table style="border-collapse: collapse; width: 100%; max-width: 500px;">
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Cliente</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{nome_cliente}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Lavoro</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{lavoro.titolo}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Residuo</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">€ {lavoro.residuo_pagamento:.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Scadenza</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{scadenza.strftime('%d/%m/%Y')}</td>
                    </tr>
                </table>
                <p style="margin-top: 20px; color: gray; font-size: 12px;">
                    Email inviata automaticamente dal gestionale.
                </p>
            </body>
            </html>
            """

            inviata = invia_email(email_utente, oggetto, corpo)
            if inviata:
                contatore += 1

        logger.info(f"Controllo scadenze completato. Email inviate: {contatore}")

    except Exception as e:
        logger.error(f"Errore durante controllo scadenze: {e}")

    finally:
        db.close()