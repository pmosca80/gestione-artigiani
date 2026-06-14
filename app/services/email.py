import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from app.logger import get_logger

logger = get_logger("email")

_SENDER_DEFAULT = "Gestionale Artigiani <noreply@resend.dev>"


def smtp_configurato() -> bool:
    """True se Resend o SMTP sono configurati."""
    if os.getenv("RESEND_API_KEY"):
        return True
    return bool(
        (os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME"))
        and (os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD"))
    )


def _sender() -> str:
    return os.getenv("MAIL_FROM", _SENDER_DEFAULT)


# ── backend Resend ────────────────────────────────────────────────────────────

def _send_resend(*, to: str, subject: str, html: str, from_: str, attachments: list | None) -> bool:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")
    params: dict = {"from": from_, "to": [to], "subject": subject, "html": html}
    if attachments:
        params["attachments"] = attachments
    resend.Emails.send(params)


# ── backend SMTP (Brevo / qualsiasi SMTP) ────────────────────────────────────

def _smtp_cfg() -> dict:
    return {
        "host":     os.getenv("SMTP_HOST", "smtp-relay.brevo.com"),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME", ""),
        "password": os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD", ""),
    }


def _send_smtp(*, to: str, subject: str, html: str, from_: str, attachments: list | None) -> None:
    cfg = _smtp_cfg()
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = from_
    msg["To"]      = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    if attachments:
        for att in attachments:
            part = MIMEBase("application", "octet-stream")
            content = att.get("content", b"")
            if isinstance(content, list):
                content = bytes(content)
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=att.get("filename", "allegato"))
            msg.attach(part)
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
        s.ehlo()
        s.starttls()
        s.login(cfg["user"], cfg["password"])
        s.sendmail(from_, to, msg.as_string())


# ── dispatcher ───────────────────────────────────────────────────────────────

def _send(
    *,
    to: str,
    subject: str,
    html: str,
    from_: str | None = None,
    attachments: list | None = None,
) -> bool:
    sender = from_ or _sender()
    try:
        if os.getenv("RESEND_API_KEY"):
            _send_resend(to=to, subject=subject, html=html, from_=sender, attachments=attachments)
        else:
            _send_smtp(to=to, subject=subject, html=html, from_=sender, attachments=attachments)
        logger.info(f"Email inviata a {to} — {subject}")
        return True
    except Exception as e:
        logger.warning(f"Errore invio email a {to}: {e}")
        return False


# ── funzioni pubbliche ────────────────────────────────────────────────────────

def invia_email(destinatario: str, oggetto: str, corpo: str) -> bool:
    return _send(to=destinatario, subject=oggetto, html=corpo)


def invia_verifica_email(email: str, token: str, base_url: str) -> bool:
    link = f"{base_url}/verifica-email/{token}"
    corpo = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;margin:0;padding:32px 16px;">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:16px;
     box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">
  <div style="background:linear-gradient(135deg,#2563eb,#1d4ed8);padding:32px;text-align:center;">
    <div style="font-size:40px;">🔧</div>
    <h1 style="color:white;font-size:22px;font-weight:700;margin:12px 0 4px;">Gestionale Artigiani</h1>
    <p style="color:#bfdbfe;font-size:14px;margin:0;">Conferma il tuo indirizzo email</p>
  </div>
  <div style="padding:32px;">
    <p style="color:#374151;font-size:15px;margin:0 0 20px;">
      Benvenuto! Clicca il pulsante qui sotto per attivare il tuo account.
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{link}" style="display:inline-block;padding:14px 32px;background:#2563eb;color:white;
         border-radius:10px;font-size:15px;font-weight:700;text-decoration:none;">
        Attiva il mio account →
      </a>
    </div>
    <p style="color:#9ca3af;font-size:12px;margin:24px 0 0;">
      Il link è valido per 48 ore. Se non hai richiesto questo account, ignora questa email.<br>
      Oppure copia e incolla nel browser:<br>
      <span style="word-break:break-all;">{link}</span>
    </p>
  </div>
</div>
</body></html>"""
    return invia_email(email, "Attiva il tuo account — Gestionale Artigiani", corpo)


def invia_reset_password(email: str, token: str, base_url: str) -> bool:
    link = f"{base_url}/reset-password/{token}"
    corpo = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;margin:0;padding:32px 16px;">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:16px;
     box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">
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
      Il link è valido per 2 ore. Se non hai richiesto il reset, ignora questa email.<br>
      Oppure copia e incolla:<br>
      <span style="word-break:break-all;">{link}</span>
    </p>
  </div>
</div>
</body></html>"""
    return invia_email(email, "Reimposta la password — Gestionale Artigiani", corpo)


def invia_benvenuto(username: str, piano: str = "free") -> None:
    if "@" not in (username or "") or not smtp_configurato():
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
<html lang="it"><head><meta charset="UTF-8">
<style>
  body{{margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;}}
  .wrap{{max-width:560px;margin:40px auto;background:white;border-radius:16px;
        overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);}}
  .hdr{{background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);padding:32px 36px;text-align:center;}}
  .hdr h1{{color:white;font-size:24px;margin:0;font-weight:700;}}
  .hdr p{{color:#94a3b8;font-size:14px;margin:8px 0 0;}}
  .bdy{{padding:32px 36px;}}
  .bdy h2{{font-size:18px;color:#111827;margin:0 0 12px;}}
  .bdy p{{font-size:14px;color:#374151;line-height:1.7;margin:0 0 16px;}}
  .ft{{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;}}
  .ft span{{font-size:20px;flex-shrink:0;}}
  .ft p{{margin:0;font-size:14px;color:#374151;line-height:1.5;}}
  .btn{{display:inline-block;background:#2563eb;color:white;padding:13px 28px;
        border-radius:10px;font-size:15px;font-weight:700;text-decoration:none;margin-top:8px;}}
  .ftr{{background:#f8fafc;padding:16px 36px;text-align:center;
        font-size:12px;color:#9ca3af;border-top:1px solid #f1f5f9;}}
</style></head>
<body><div class="wrap">
  <div class="hdr"><h1>🔧 Gestionale Artigiani</h1>
    <p>Il gestionale pensato per chi lavora con le mani</p></div>
  <div class="bdy">
    <h2>Benvenuto, {username}!</h2>
    <p>Il tuo account è pronto. Ecco cosa puoi fare subito:</p>
    {promo_banner}
    <div class="ft"><span>👥</span><p><strong>Gestisci i clienti</strong> — rubrica completa con storico lavori</p></div>
    <div class="ft"><span>🛠️</span><p><strong>Traccia i lavori</strong> — da preventivo a fattura, tutto in un posto</p></div>
    <div class="ft"><span>📦</span><p><strong>Magazzino</strong> — scorte e materiali sotto controllo</p></div>
    <div class="ft"><span>🧾</span><p><strong>FatturaPA XML</strong> — pronto per il commercialista</p></div>
    <div class="ft"><span>📊</span><p><strong>Dashboard KPI</strong> — fatturato, margini, scadenze</p></div>
    <p style="margin-top:24px;">
      <a href="https://optimistic-courtesy-production.up.railway.app" class="btn">Accedi al gestionale →</a>
    </p>
  </div>
  <div class="ftr">© 2026 Gestionale Artigiani · Hai domande? Rispondi a questa email.</div>
</div></body></html>"""

    _send(to=username, subject="Benvenuto su Gestionale Artigiani 🔧", html=corpo)


def invia_conferma_pro(username: str) -> None:
    if "@" not in (username or "") or not smtp_configurato():
        return

    corpo = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8">
<style>
  body{{margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;}}
  .wrap{{max-width:560px;margin:40px auto;background:white;border-radius:16px;
        overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);}}
  .hdr{{background:linear-gradient(135deg,#4c1d95 0%,#6d28d9 100%);padding:32px 36px;text-align:center;}}
  .hdr h1{{color:white;font-size:24px;margin:0;font-weight:700;}}
  .hdr p{{color:#ddd6fe;font-size:14px;margin:8px 0 0;}}
  .badge{{display:inline-block;background:white;color:#7c3aed;padding:6px 16px;
          border-radius:999px;font-weight:700;font-size:13px;margin-top:12px;}}
  .bdy{{padding:32px 36px;}}
  .bdy p{{font-size:14px;color:#374151;line-height:1.7;margin:0 0 16px;}}
  .ft{{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;}}
  .ft span{{font-size:20px;flex-shrink:0;}}
  .ft p{{margin:0;font-size:14px;}}
  .btn{{display:inline-block;background:#7c3aed;color:white;padding:13px 28px;
        border-radius:10px;font-size:15px;font-weight:700;text-decoration:none;margin-top:8px;}}
  .ftr{{background:#f8fafc;padding:16px 36px;text-align:center;
        font-size:12px;color:#9ca3af;border-top:1px solid #f1f5f9;}}
</style></head>
<body><div class="wrap">
  <div class="hdr"><h1>⭐ Piano Pro attivato!</h1>
    <p>Hai sbloccato tutte le funzionalità premium</p>
    <span class="badge">✅ PRO ATTIVO</span></div>
  <div class="bdy">
    <p>Ottimo, <strong>{username}</strong>! Il tuo abbonamento <strong>Pro</strong> è ora attivo.</p>
    <div class="ft"><span>🧾</span><p><strong>FatturaPA XML</strong> illimitata</p></div>
    <div class="ft"><span>📊</span><p><strong>Dashboard KPI avanzata</strong></p></div>
    <div class="ft"><span>💾</span><p><strong>Backup & export</strong> dati completo</p></div>
    <p><a href="https://optimistic-courtesy-production.up.railway.app" class="btn">Vai al gestionale →</a></p>
  </div>
  <div class="ftr">© 2026 Gestionale Artigiani</div>
</div></body></html>"""

    _send(to=username, subject="Piano Pro attivato ⭐ — Gestionale Artigiani", html=corpo)


def invia_notifica_firma_preventivo(
    *,
    artigiano_email: str,
    nome_azienda: str,
    titolo_lavoro: str,
    nome_cliente_firma: str,
    importo: float | None,
    link_lavoro: str,
) -> None:
    if "@" not in (artigiano_email or "") or not smtp_configurato():
        return

    importo_riga = (
        f'<div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px;">'
        f'<span style="color:#6b7280;">Importo</span>'
        f'<span style="font-weight:700;color:#166534;">€ {importo:,.2f}</span></div>'
        if importo else ""
    )

    corpo = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f0fdf4;margin:0;padding:32px 16px;">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:16px;
     box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">
  <div style="background:linear-gradient(135deg,#15803d,#16a34a);padding:28px 36px;text-align:center;">
    <h1 style="color:white;font-size:22px;margin:0;font-weight:700;">✅ Preventivo accettato!</h1>
    <p style="color:#bbf7d0;font-size:14px;margin:8px 0 0;">Il cliente ha firmato il preventivo</p>
  </div>
  <div style="padding:28px 36px;">
    <p style="font-size:14px;color:#374151;">
      Ottima notizia! <strong>{nome_cliente_firma}</strong> ha appena accettato il preventivo.
    </p>
    <div style="background:#f0fdf4;border-radius:12px;padding:16px;margin:20px 0;">
      <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px;">
        <span style="color:#6b7280;">Lavoro</span>
        <span style="font-weight:700;color:#166534;">{titolo_lavoro}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px;">
        <span style="color:#6b7280;">Firmato da</span>
        <span style="font-weight:700;color:#166534;">{nome_cliente_firma}</span>
      </div>
      {importo_riga}
    </div>
    <p style="text-align:center;">
      <a href="{link_lavoro}" style="display:inline-block;background:#16a34a;color:white;
         padding:13px 28px;border-radius:10px;font-size:15px;font-weight:700;text-decoration:none;">
        Apri il lavoro →
      </a>
    </p>
  </div>
  <div style="background:#f8fafc;padding:14px 36px;text-align:center;
       font-size:12px;color:#9ca3af;border-top:1px solid #f1f5f9;">
    {nome_azienda} · Gestionale Artigiani
  </div>
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
    Lancia RuntimeError se il servizio email non è configurato o l'invio fallisce.
    """
    if not smtp_configurato():
        raise RuntimeError(
            "Email non configurata. Imposta RESEND_API_KEY oppure SMTP_USER + SMTP_PASSWORD."
        )

    corpo_html = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;color:#374151;padding:24px;">
<p>Gentile {to_nome},</p>
<p>in allegato trova la FatturaPA elettronica n. <strong>{numero_fattura}</strong>
del {data_emissione}.</p>
<p>Importo totale: <strong>€ {importo_totale:.2f}</strong></p>
<p>Il file XML è conforme allo standard FatturaPA FPR12.</p>
<p>Cordiali saluti,<br><strong>{from_nome}</strong></p>
</body></html>"""

    ok = _send(
        to=to_email,
        subject=f"Fattura n. {numero_fattura} — {from_nome}",
        html=corpo_html,
        attachments=[{"filename": nome_file, "content": list(xml_bytes)}],
    )
    if not ok:
        raise RuntimeError(f"Invio FatturaPA a {to_email} fallito.")
