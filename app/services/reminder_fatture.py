from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import FatturaEmessa, ImpostazioniAzienda, Utente
from app.services.email import invia_email
from app.services.push import invia_push
from app.logger import get_logger

logger = get_logger("reminder_fatture")

# Prima email dopo 30 giorni dalla data emissione, seconda dopo 60
SOGLIE = [30, 60]


def controlla_fatture_non_pagate() -> None:
    logger.info("Controllo fatture non pagate in corso...")
    db: Session = SessionLocal()
    try:
        _esegui(db)
    except Exception as e:
        logger.error(f"Errore reminder fatture: {e}")
    finally:
        db.close()


def _esegui(db: Session) -> None:
    oggi = datetime.now().date()

    # Carica tutte le fatture emesse non ancora pagate con reminder non ancora esauriti
    fatture = (
        db.query(FatturaEmessa)
        .filter(
            FatturaEmessa.stato == "emessa",
            FatturaEmessa.reminder_inviato < len(SOGLIE),
        )
        .all()
    )

    # Raggruppa per utente le fatture che hanno raggiunto una nuova soglia
    da_notificare: dict[int, list[dict]] = defaultdict(list)
    aggiornamenti: list[tuple[FatturaEmessa, int]] = []

    for fattura in fatture:
        try:
            data_em = datetime.strptime(fattura.data_emissione, "%Y-%m-%d").date()
        except Exception:
            continue

        giorni = (oggi - data_em).days
        livello_attuale = fattura.reminder_inviato or 0

        # Determina se va inviato un nuovo reminder
        nuovo_livello = livello_attuale
        for i, soglia in enumerate(SOGLIE):
            if giorni >= soglia and livello_attuale <= i:
                nuovo_livello = i + 1

        if nuovo_livello <= livello_attuale:
            continue  # nessuna nuova soglia raggiunta

        lavoro = fattura.lavoro
        cliente = lavoro.cliente if lavoro else None
        nome_cliente = "—"
        if cliente:
            nome_cliente = (
                cliente.ragione_sociale
                or f"{cliente.nome or ''} {cliente.cognome or ''}".strip()
                or "—"
            )

        da_notificare[fattura.utente_id].append(
            {
                "numero": fattura.numero,
                "anno": fattura.anno,
                "importo": fattura.importo_totale,
                "data_emissione": data_em.strftime("%d/%m/%Y"),
                "giorni": giorni,
                "cliente": nome_cliente,
            }
        )
        aggiornamenti.append((fattura, nuovo_livello))

    # Invia un'email digest per ogni artigiano
    email_inviate = 0
    for utente_id, voci in da_notificare.items():
        azienda = (
            db.query(ImpostazioniAzienda)
            .filter(ImpostazioniAzienda.utente_id == utente_id)
            .first()
        )
        email_dest = azienda.email if azienda else None
        if not email_dest:
            continue

        n = len(voci)
        oggetto = f"⚠️ {n} fattur{'a non pagata' if n == 1 else 'e non pagate'} — promemoria automatico"
        corpo = _componi_email(voci, azienda.nome_azienda or "")
        if invia_email(email_dest, oggetto, corpo):
            email_inviate += 1

        n = len(voci)
        invia_push(
            db, utente_id,
            titolo=f"{n} fattur{'a non pagata' if n == 1 else 'e non pagate'}",
            corpo=", ".join(f"{v['numero']}/{v['anno']} · {v['cliente']}" for v in voci[:3]),
            url="/fatture/",
        )

    # Aggiorna reminder_inviato solo dopo aver inviato le email
    for fattura, livello in aggiornamenti:
        utente_id = fattura.utente_id
        if utente_id in da_notificare:
            azienda = (
                db.query(ImpostazioniAzienda)
                .filter(ImpostazioniAzienda.utente_id == utente_id)
                .first()
            )
            if azienda and azienda.email:
                fattura.reminder_inviato = livello

    db.commit()
    logger.info(
        f"Reminder fatture completato. Email inviate: {email_inviate}, "
        f"fatture aggiornate: {len(aggiornamenti)}"
    )


def _componi_email(voci: list[dict], nome_azienda: str) -> str:
    righe = ""
    for v in sorted(voci, key=lambda x: x["giorni"], reverse=True):
        colore_giorni = "#dc2626" if v["giorni"] >= 60 else "#d97706"
        righe += f"""
        <tr>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;font-weight:600;">
                {v['numero']}/{v['anno']}
            </td>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;">{v['cliente']}</td>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;">{v['data_emissione']}</td>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;font-weight:700;color:{colore_giorni};">
                {v['giorni']} giorni
            </td>
            <td style="padding:9px 12px;border:1px solid #e5e7eb;font-weight:700;">
                € {v['importo']:.2f}
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
          ⚠️ Fatture non pagate {intestazione}
        </h1>
      </div>

      <div style="padding:28px 32px;">
        <p style="color:#374151;font-size:14px;margin:0 0 20px;">
          Le seguenti fatture risultano ancora <strong>non pagate</strong>.
          Ti invitiamo a verificare lo stato dei pagamenti e a contattare i clienti se necessario.
        </p>

        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="background:#f1f5f9;">
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Fattura</th>
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Cliente</th>
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Emessa il</th>
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Scaduta da</th>
              <th style="padding:9px 12px;border:1px solid #e5e7eb;text-align:left;">Importo</th>
            </tr>
          </thead>
          <tbody>{righe}</tbody>
        </table>

        <div style="margin-top:24px;padding:16px;background:#fef3c7;border:1px solid #fcd34d;
                    border-radius:8px;font-size:13px;color:#92400e;">
          💡 Puoi aggiornare lo stato delle fatture dalla sezione
          <strong>Fatture</strong> del gestionale.
        </div>
      </div>

      <div style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e5e7eb;">
        <p style="margin:0;font-size:11px;color:#9ca3af;">
          Email inviata automaticamente dal Mastro.
          Per disattivare questi avvisi contatta il supporto.
        </p>
      </div>
    </div>
    </body>
    </html>
    """
