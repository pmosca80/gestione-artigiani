import os
from app.logger import get_logger

logger = get_logger("email")

_SENDER_DEFAULT = "Gestionale Artigiani <onboarding@resend.dev>"


def smtp_configurato() -> bool:
    """True se RESEND_API_KEY è configurata."""
    return bool(os.getenv("RESEND_API_KEY"))


def _sender() -> str:
    return os.getenv("MAIL_FROM", _SENDER_DEFAULT)


def _send(
    *,
    to: str,
    subject: str,
    html: str,
    from_: str | None = None,
    attachments: list | None = None,
) -> bool:
    """Invia via Resend API. Ritorna True se OK, False altrimenti."""
    import resend

    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        logger.warning("RESEND_API_KEY non configurata — email non inviata")
        return False

    resend.api_key = api_key
    params: dict = {
        "from": from_ or _sender(),
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if attachments:
        params["attachments"] = attachments

    try:
        resend.Emails.send(params)
        logger.info(f"Email inviata a {to} — {subject}")
        return True
    except Exception as e:
        logger.warning(f"Errore invio email a {to}: {e}")
        return False


def invia_email(destinatario: str, oggetto: str, corpo: str) -> bool:
    """Invia email HTML semplice."""
    return _send(to=destinatario, subject=oggetto, html=corpo)


def invia_benvenuto(username: str, piano: str = "free") -> None:
    """Email di benvenuto inviata subito dopo la registrazione. Fire-and-forget."""
    if "@" not in (username or ""):
        return
    if not smtp_configurato():
        return

    promo_banner = ""
    if piano == "pro":
        promo_banner = """
        <div style="background:#dcfce7;border:1px solid #86efac;border-radius:10px;
                    padding:14px 18px;margin:20px 0;font-size:14px;color:#166534;">
            🎁 <strong>Codice promo applicato!</strong> Il tuo account è già attivo su piano
            <strong>Pro</strong> per 30 giorni.
        </div>"""

    corpo = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8">
<style>
  body {{ margin:0; padding:0; background:#f1f5f9; font-family:'Segoe UI',Arial,sans-serif; }}
  .wrap {{ max-width:560px; margin:40px auto; background:white; border-radius:16px;
           overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08); }}
  .header {{ background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);
             padding:32px 36px; text-align:center; }}
  .header h1 {{ color:white; font-size:24px; margin:0; font-weight:700; }}
  .header p  {{ color:#94a3b8; font-size:14px; margin:8px 0 0; }}
  .body {{ padding:32px 36px; }}
  .body h2 {{ font-size:18px; color:#111827; margin:0 0 12px; }}
  .body p  {{ font-size:14px; color:#374151; line-height:1.7; margin:0 0 16px; }}
  .feature {{ display:flex; align-items:flex-start; gap:10px; margin-bottom:10px; }}
  .feature span {{ font-size:20px; flex-shrink:0; }}
  .feature p {{ margin:0; font-size:14px; color:#374151; line-height:1.5; }}
  .btn {{ display:inline-block; background:#2563eb; color:white; padding:13px 28px;
          border-radius:10px; font-size:15px; font-weight:700; text-decoration:none;
          margin-top:8px; }}
  .footer {{ background:#f8fafc; padding:16px 36px; text-align:center;
             font-size:12px; color:#9ca3af; border-top:1px solid #f1f5f9; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>🔧 Gestionale Artigiani</h1>
    <p>Il gestionale pensato per chi lavora con le mani</p>
  </div>
  <div class="body">
    <h2>Benvenuto, {username}!</h2>
    <p>Il tuo account è stato creato con successo. Ecco cosa puoi fare subito:</p>
    {promo_banner}
    <div class="feature"><span>👥</span><p><strong>Gestisci i clienti</strong> — rubrica completa con storico lavori</p></div>
    <div class="feature"><span>🛠️</span><p><strong>Traccia i lavori</strong> — da preventivo a fattura, tutto in un posto</p></div>
    <div class="feature"><span>📦</span><p><strong>Magazzino</strong> — tieni sotto controllo scorte e materiali</p></div>
    <div class="feature"><span>🧾</span><p><strong>Documenti PDF e FatturaPA</strong> — genera XML pronto per il commercialista</p></div>
    <div class="feature"><span>📊</span><p><strong>Dashboard KPI</strong> — fatturato, margini, scadenze, tutto a colpo d'occhio</p></div>
    <p style="margin-top:24px;">
      <a href="https://optimistic-courtesy-production.up.railway.app" class="btn">Accedi al gestionale →</a>
    </p>
  </div>
  <div class="footer">© 2026 Gestionale Artigiani · Hai domande? Rispondi a questa email.</div>
</div>
</body></html>"""

    _send(to=username, subject="Benvenuto su Gestionale Artigiani 🔧", html=corpo)


def invia_conferma_pro(username: str) -> None:
    """Email di conferma attivazione piano Pro. Fire-and-forget."""
    if "@" not in (username or ""):
        return
    if not smtp_configurato():
        return

    corpo = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8">
<style>
  body {{ margin:0; padding:0; background:#f1f5f9; font-family:'Segoe UI',Arial,sans-serif; }}
  .wrap {{ max-width:560px; margin:40px auto; background:white; border-radius:16px;
           overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08); }}
  .header {{ background:linear-gradient(135deg,#4c1d95 0%,#6d28d9 100%);
             padding:32px 36px; text-align:center; }}
  .header h1 {{ color:white; font-size:24px; margin:0; font-weight:700; }}
  .header p  {{ color:#ddd6fe; font-size:14px; margin:8px 0 0; }}
  .badge {{ display:inline-block; background:white; color:#7c3aed; padding:6px 16px;
            border-radius:999px; font-weight:700; font-size:13px; margin-top:12px; }}
  .body {{ padding:32px 36px; }}
  .body h2 {{ font-size:18px; color:#111827; margin:0 0 12px; }}
  .body p  {{ font-size:14px; color:#374151; line-height:1.7; margin:0 0 16px; }}
  .feature {{ display:flex; align-items:flex-start; gap:10px; margin-bottom:10px; }}
  .feature span {{ font-size:20px; flex-shrink:0; }}
  .feature p {{ margin:0; font-size:14px; color:#374151; line-height:1.5; }}
  .btn {{ display:inline-block; background:#7c3aed; color:white; padding:13px 28px;
          border-radius:10px; font-size:15px; font-weight:700; text-decoration:none;
          margin-top:8px; }}
  .footer {{ background:#f8fafc; padding:16px 36px; text-align:center;
             font-size:12px; color:#9ca3af; border-top:1px solid #f1f5f9; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>⭐ Piano Pro attivato!</h1>
    <p>Hai sbloccato tutte le funzionalità premium</p>
    <span class="badge">✅ PRO ATTIVO</span>
  </div>
  <div class="body">
    <h2>Ottimo, {username}!</h2>
    <p>Il tuo abbonamento <strong>Pro</strong> è ora attivo.
       Hai accesso completo a tutte le funzionalità senza limiti:</p>
    <div class="feature"><span>👥</span><p><strong>Clienti illimitati</strong></p></div>
    <div class="feature"><span>📑</span><p><strong>Preventivi illimitati</strong> con firma digitale</p></div>
    <div class="feature"><span>🧾</span><p><strong>FatturaPA XML</strong> illimitata</p></div>
    <div class="feature"><span>📊</span><p><strong>Dashboard KPI avanzata</strong> — analisi economica completa</p></div>
    <div class="feature"><span>📦</span><p><strong>Magazzino illimitato</strong> con storico movimenti</p></div>
    <div class="feature"><span>💾</span><p><strong>Backup & export</strong> dati completo</p></div>
    <p>Puoi gestire il tuo abbonamento in qualsiasi momento dal menu <strong>Piano</strong>.</p>
    <p>
      <a href="https://optimistic-courtesy-production.up.railway.app" class="btn">Vai al gestionale →</a>
    </p>
  </div>
  <div class="footer">© 2026 Gestionale Artigiani · Grazie per aver scelto Pro!</div>
</div>
</body></html>"""

    _send(to=username, subject="Piano Pro attivato ⭐ — Gestionale Artigiani", html=corpo)


def invia_verifica_email(email: str, token: str, base_url: str) -> bool:
    """Invia link di verifica account dopo la registrazione."""
    link = f"{base_url}/verifica-email/{token}"
    corpo = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;margin:0;padding:32px 16px;">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">
  <div style="background:linear-gradient(135deg,#2563eb,#1d4ed8);padding:32px;text-align:center;">
    <div style="font-size:40px;">🔧</div>
    <h1 style="color:white;font-size:22px;font-weight:700;margin:12px 0 4px;">Gestionale Artigiani</h1>
    <p style="color:#bfdbfe;font-size:14px;margin:0;">Conferma il tuo indirizzo email</p>
  </div>
  <div style="padding:32px;">
    <p style="color:#374151;font-size:15px;margin:0 0 20px;">Benvenuto! Clicca il pulsante qui sotto per attivare il tuo account.</p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{link}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:white;
         border-radius:10px;font-size:15px;font-weight:700;text-decoration:none;">
        Verifica email →
      </a>
    </div>
    <p style="color:#9ca3af;font-size:12px;margin:24px 0 0;">
      Il link è valido per 48 ore. Se non hai richiesto questo account, ignora questa email.<br>
      Oppure copia e incolla nel browser: <span style="word-break:break-all;">{link}</span>
    </p>
  </div>
</div>
</body></html>"""
    return invia_email(email, "Verifica il tuo account — Gestionale Artigiani", corpo)


def invia_reset_password(email: str, token: str, base_url: str) -> bool:
    """Invia link per reimpostare la password."""
    link = f"{base_url}/reset-password/{token}"
    corpo = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;margin:0;padding:32px 16px;">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">
  <div style="background:linear-gradient(135deg,#0f172a,#1e3a5f);padding:32px;text-align:center;">
    <div style="font-size:40px;">🔑</div>
    <h1 style="color:white;font-size:22px;font-weight:700;margin:12px 0 4px;">Gestionale Artigiani</h1>
    <p style="color:#94a3b8;font-size:14px;margin:0;">Reimposta la tua password</p>
  </div>
  <div style="padding:32px;">
    <p style="color:#374151;font-size:15px;margin:0 0 20px;">
      Hai richiesto di reimpostare la password del tuo account.<br>
      Clicca il pulsante qui sotto per scegliere una nuova password.
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{link}" style="display:inline-block;padding:14px 32px;background:#dc2626;color:white;
         border-radius:10px;font-size:15px;font-weight:700;text-decoration:none;">
        Reimposta password →
      </a>
    </div>
    <p style="color:#9ca3af;font-size:12px;margin:24px 0 0;">
      Il link è valido per 2 ore. Se non hai richiesto il reset, ignora questa email — la tua password rimane invariata.<br>
      Oppure copia e incolla: <span style="word-break:break-all;">{link}</span>
    </p>
  </div>
</div>
</body></html>"""
    return invia_email(email, "Reimposta la password — Gestionale Artigiani", corpo)


def invia_notifica_firma_preventivo(
    *,
    artigiano_email: str,
    nome_azienda: str,
    titolo_lavoro: str,
    nome_cliente_firma: str,
    importo: float | None,
    link_lavoro: str,
) -> None:
    """Notifica all'artigiano che il cliente ha accettato il preventivo. Fire-and-forget."""
    if "@" not in (artigiano_email or ""):
        return
    if not smtp_configurato():
        return

    importo_riga = (
        f'<div class="det-row"><span class="det-label">Importo</span>'
        f'<span class="det-val">€ {importo:,.2f}</span></div>'
        if importo else ""
    )

    corpo = f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8">
<style>
  body {{ margin:0; padding:0; background:#f0fdf4; font-family:'Segoe UI',Arial,sans-serif; }}
  .wrap {{ max-width:520px; margin:40px auto; background:white; border-radius:16px;
           overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,0.08); }}
  .header {{ background:linear-gradient(135deg,#15803d 0%,#16a34a 100%);
             padding:28px 36px; text-align:center; }}
  .header h1 {{ color:white; font-size:22px; margin:0; font-weight:700; }}
  .header p  {{ color:#bbf7d0; font-size:14px; margin:8px 0 0; }}
  .body {{ padding:28px 36px; }}
  .body p {{ font-size:14px; color:#374151; line-height:1.7; margin:0 0 16px; }}
  .details {{ background:#f0fdf4; border-radius:12px; padding:16px; margin:20px 0; }}
  .det-row {{ display:flex; justify-content:space-between; font-size:13px; margin-bottom:6px; }}
  .det-row:last-child {{ margin-bottom:0; }}
  .det-label {{ color:#6b7280; }}
  .det-val {{ font-weight:700; color:#166534; }}
  .btn {{ display:inline-block; background:#16a34a; color:white; padding:13px 28px;
          border-radius:10px; font-size:15px; font-weight:700; text-decoration:none; }}
  .footer {{ background:#f8fafc; padding:14px 36px; text-align:center;
             font-size:12px; color:#9ca3af; border-top:1px solid #f1f5f9; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>✅ Preventivo accettato!</h1>
    <p>Il cliente ha firmato il preventivo</p>
  </div>
  <div class="body">
    <p>Ottima notizia! <strong>{nome_cliente_firma}</strong> ha appena accettato il preventivo.</p>
    <div class="details">
      <div class="det-row"><span class="det-label">Lavoro</span><span class="det-val">{titolo_lavoro}</span></div>
      <div class="det-row"><span class="det-label">Firmato da</span><span class="det-val">{nome_cliente_firma}</span></div>
      {importo_riga}
    </div>
    <p style="text-align:center;">
      <a href="{link_lavoro}" class="btn">Apri il lavoro →</a>
    </p>
  </div>
  <div class="footer">{nome_azienda} · Gestionale Artigiani</div>
</div>
</body></html>"""

    _send(
        to=artigiano_email,
        subject=f"✅ {nome_cliente_firma} ha accettato il preventivo — {titolo_lavoro}",
        html=corpo,
    )


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
    Lancia RuntimeError se Resend non è configurato o l'invio fallisce.
    """
    import resend

    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Resend non configurato. Imposta RESEND_API_KEY nelle variabili d'ambiente."
        )

    resend.api_key = api_key

    corpo_testo = (
        f"Gentile {to_nome},\n\n"
        f"in allegato trova la FatturaPA elettronica n. {numero_fattura} "
        f"del {data_emissione}.\n\n"
        f"  Importo totale: € {importo_totale:.2f}\n\n"
        "Il file XML è conforme allo standard FatturaPA FPR12 e può essere\n"
        "consegnato al proprio intermediario o commercialista per l'inoltro\n"
        "al Sistema di Interscambio (SDI).\n\n"
        f"Cordiali saluti,\n{from_nome}\n"
    )

    params: dict = {
        "from": _sender(),
        "to": [f"{to_nome} <{to_email}>"],
        "subject": f"Fattura n. {numero_fattura} — {from_nome}",
        "text": corpo_testo,
        "attachments": [
            {
                "filename": nome_file,
                "content": list(xml_bytes),
            }
        ],
    }

    try:
        resend.Emails.send(params)
        logger.info(f"FatturaPA {nome_file} inviata a {to_email}")
    except Exception as e:
        logger.error(f"Errore invio FatturaPA a {to_email}: {e}")
        raise RuntimeError(f"Invio fallito: {e}") from e
