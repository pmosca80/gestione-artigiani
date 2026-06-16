from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Garanzia, ImpostazioniAzienda
from app.services.email import invia_email
from app.services.push import invia_push
from app.services.scheduler_lock import con_lock
from app.logger import get_logger

logger = get_logger("garanzie_reminder")


@con_lock("controlla_garanzie")
def controlla_garanzie() -> None:
    logger.info("Controllo scadenze garanzie in corso...")
    db: Session = SessionLocal()
    try:
        _esegui(db)
    except Exception as e:
        logger.error(f"Errore reminder garanzie: {e}")
    finally:
        db.close()


def _esegui(db: Session) -> None:
    oggi = datetime.now().date()
    tra_30 = oggi + timedelta(days=30)
    tra_7 = oggi + timedelta(days=7)

    garanzie = db.query(Garanzia).all()

    da_notificare_30: dict[int, list[dict]] = defaultdict(list)
    da_notificare_7: dict[int, list[dict]] = defaultdict(list)
    aggiornamenti_30 = []
    aggiornamenti_7 = []

    for g in garanzie:
        scad = g.data_scadenza
        if not scad:
            continue

        giorni = (scad - oggi).days
        nome_cliente = "—"
        if g.cliente:
            nome_cliente = (
                g.cliente.ragione_sociale
                or f"{g.cliente.nome or ''} {g.cliente.cognome or ''}".strip()
                or "—"
            )

        voce = {
            "descrizione": g.descrizione,
            "cliente": nome_cliente,
            "data_scadenza": scad.strftime("%d/%m/%Y"),
            "giorni": giorni,
        }

        if 0 <= giorni <= 30 and not g.reminder_30g_inviato:
            da_notificare_30[g.utente_id].append(voce)
            aggiornamenti_30.append(g)

        if 0 <= giorni <= 7 and not g.reminder_7g_inviato:
            da_notificare_7[g.utente_id].append(voce)
            aggiornamenti_7.append(g)

    email_inviate = 0

    for utente_id, voci in da_notificare_30.items():
        azienda = db.query(ImpostazioniAzienda).filter(
            ImpostazioniAzienda.utente_id == utente_id
        ).first()
        email_dest = azienda.email if azienda else None
        if not email_dest:
            continue
        n = len(voci)
        oggetto = f"🔧 {n} garanzi{'a' if n == 1 else 'e'} in scadenza nei prossimi 30 giorni"
        corpo = _componi_email(voci, azienda.nome_azienda or "", "30 giorni")
        if invia_email(email_dest, oggetto, corpo):
            email_inviate += 1
        invia_push(
            db, utente_id,
            titolo=f"{n} garanzi{'a' if n == 1 else 'e'} in scadenza (30g)",
            corpo=", ".join(v["descrizione"] for v in voci[:3]),
            url="/garanzie/",
        )

    for utente_id, voci in da_notificare_7.items():
        azienda = db.query(ImpostazioniAzienda).filter(
            ImpostazioniAzienda.utente_id == utente_id
        ).first()
        email_dest = azienda.email if azienda else None
        if not email_dest:
            continue
        n = len(voci)
        oggetto = f"⚠️ {n} garanzi{'a' if n == 1 else 'e'} in scadenza questa settimana!"
        corpo = _componi_email(voci, azienda.nome_azienda or "", "7 giorni")
        if invia_email(email_dest, oggetto, corpo):
            email_inviate += 1
        invia_push(
            db, utente_id,
            titolo=f"Urgente: {n} garanzi{'a' if n == 1 else 'e'} scade questa settimana",
            corpo=", ".join(v["descrizione"] for v in voci[:3]),
            url="/garanzie/",
        )

    for g in aggiornamenti_30:
        g.reminder_30g_inviato = 1
    for g in aggiornamenti_7:
        g.reminder_7g_inviato = 1

    db.commit()
    logger.info(f"Reminder garanzie completato. Email inviate: {email_inviate}")


def _componi_email(voci: list[dict], nome_azienda: str, finestra: str) -> str:
    righe = ""
    for v in sorted(voci, key=lambda x: x["giorni"]):
        colore = "#dc2626" if v["giorni"] <= 7 else "#d97706"
        righe += f"""
        <tr>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;font-weight:600;">{v['descrizione']}</td>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;">{v['cliente']}</td>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;">{v['data_scadenza']}</td>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;font-weight:700;color:{colore};">
                tra {v['giorni']} giorni
            </td>
        </tr>"""

    intestazione = f"per <strong>{nome_azienda}</strong>" if nome_azienda else ""

    return f"""
    <html>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;padding:32px 0;margin:0;">
    <div style="max-width:620px;margin:0 auto;background:white;border-radius:12px;
                box-shadow:0 2px 16px rgba(0,0,0,0.08);overflow:hidden;">

      <div style="background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:28px 32px;">
        <p style="margin:0;color:#94a3b8;font-size:13px;">Mastro</p>
        <h1 style="margin:6px 0 0;color:white;font-size:20px;">
          🔧 Garanzie in scadenza {intestazione}
        </h1>
      </div>

      <div style="padding:28px 32px;">
        <p style="color:#374151;font-size:14px;margin:0 0 20px;">
          Le seguenti garanzie scadono nei prossimi <strong>{finestra}</strong>.
          È un'ottima occasione per contattare i clienti e programmare la manutenzione.
        </p>

        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="background:#f1f5f9;">
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Apparecchio</th>
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Cliente</th>
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Scadenza</th>
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Mancano</th>
            </tr>
          </thead>
          <tbody>{righe}</tbody>
        </table>

        <div style="margin-top:24px;padding:16px;background:#fef3c7;border:1px solid #fcd34d;
                    border-radius:8px;font-size:13px;color:#92400e;">
          💡 Accedi alla sezione <strong>Garanzie</strong> del gestionale per creare i lavori
          di manutenzione direttamente dalla scheda garanzia.
        </div>
      </div>

      <div style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e5e7eb;">
        <p style="margin:0;font-size:11px;color:#9ca3af;">
          Email inviata automaticamente dal Mastro.
        </p>
      </div>
    </div>
    </body>
    </html>
    """
