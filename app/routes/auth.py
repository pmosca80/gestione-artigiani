import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Utente
from app.security import hash_password, verify_password
from app.limiter import limiter
from app.templates_config import templates

router = APIRouter()


def _base_url(request: Request) -> str:
    env_url = os.getenv("BASE_URL", "").rstrip("/")
    if env_url:
        return env_url
    return str(request.base_url).rstrip("/")


def _find_user(db: Session, identifier: str):
    """Cerca utente per email o per username, case-insensitive."""
    user = db.query(Utente).filter(func.lower(Utente.email) == identifier).first()
    if not user:
        user = db.query(Utente).filter(func.lower(Utente.username) == identifier).first()
    return user


# ── LOGIN ────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, account_cancellato: str = None):
    ctx = {}
    if account_cancellato:
        ctx["successo"] = "Account cancellato. Ci dispiace vederti andare."
    return templates.TemplateResponse(request=request, name="login.html", context=ctx)


@router.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _find_user(db, username.strip().lower())

    if not user:
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"errore": "Credenziali errate"},
        )

    password_ok = False
    try:
        password_ok = verify_password(password, user.password)
    except Exception:
        pass

    if not password_ok and user.password == password:
        user.password = hash_password(password)
        db.commit()
        password_ok = True

    if not password_ok:
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"errore": "Credenziali errate"},
        )

    if user.token_verifica and not user.email_verificato:
        return templates.TemplateResponse(
            request=request, name="login.html",
            context={"errore": "Devi verificare la tua email prima di accedere. Controlla la posta in arrivo."},
        )

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["is_collaboratore"] = bool(getattr(user, "titolare_id", None))
    request.session["piano"] = getattr(user, "piano", None) or "free"
    request.session["last_activity"] = datetime.now().isoformat()

    return RedirectResponse(url="/", status_code=303)


# ── REGISTRAZIONE ─────────────────────────────────────────────────────────────

@router.get("/register", response_class=HTMLResponse)
@router.get("/registrati", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"errore": None})


import re as _re

@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    conferma_password: str = Form(...),
    accetta_termini: str = Form(""),
    codice_promo: str = Form(""),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    username = username.strip().lower()

    if not accetta_termini:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "Devi accettare i Termini di servizio e la Privacy Policy per continuare."},
        )

    if "@" not in email or "." not in email.split("@")[-1]:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "Inserisci un indirizzo email valido."},
        )

    if len(username) < 3:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "Lo username deve essere di almeno 3 caratteri."},
        )

    if not _re.match(r'^[a-z0-9_]+$', username):
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "Lo username può contenere solo lettere, numeri e underscore (niente spazi)."},
        )

    if password != conferma_password:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "Le due password non coincidono."},
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "La password deve essere di almeno 8 caratteri."},
        )

    if db.query(Utente).filter(func.lower(Utente.email) == email).first():
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "Questo indirizzo email è già registrato. Accedi o usa 'Password dimenticata'."},
        )

    if db.query(Utente).filter(func.lower(Utente.username) == username).first():
        return templates.TemplateResponse(
            request=request, name="register.html",
            context={"errore": "Username già in uso. Scegline un altro."},
        )

    codice_promo_valido = os.getenv("CODICE_PROMO", "")
    promo_ok = bool(codice_promo and codice_promo_valido and codice_promo.strip() == codice_promo_valido)

    from app.services.email import smtp_configurato, invia_verifica_email
    smtp_ok = smtp_configurato()

    token = secrets.token_urlsafe(32) if smtp_ok else None

    nuovo = Utente(
        username=username,
        email=email,
        password=hash_password(password),
        data_registrazione=datetime.now().strftime("%Y-%m-%d"),
        attivo=1 if not smtp_ok else 0,
        email_verificato=not smtp_ok,
        token_verifica=token,
        accetta_termini=True,
        piano="pro" if promo_ok else "free",
        pro_scadenza=(datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d") if promo_ok else None,
    )
    db.add(nuovo)
    db.commit()

    if smtp_ok:
        import threading
        threading.Thread(
            target=invia_verifica_email,
            args=(email, token, _base_url(request)),
            daemon=True,
        ).start()
        return RedirectResponse(url="/register?pendente=1", status_code=303)

    return RedirectResponse(url="/login?verificato=1", status_code=303)


# ── VERIFICA EMAIL ─────────────────────────────────────────────────────────────

@router.get("/verifica-email/{token}", response_class=HTMLResponse)
def verifica_email(token: str, request: Request, db: Session = Depends(get_db)):
    user = db.query(Utente).filter(Utente.token_verifica == token).first()

    if not user:
        return templates.TemplateResponse(
            request=request, name="verifica_email_ok.html",
            context={"errore": "Link non valido o già utilizzato."},
        )

    user.email_verificato = True
    user.attivo = 1
    user.token_verifica = None
    db.commit()

    from app.services.email import invia_benvenuto
    import threading
    threading.Thread(target=invia_benvenuto, args=(user.email or user.username,), daemon=True).start()

    return RedirectResponse(url="/login?verificato=1", status_code=303)


# ── PASSWORD DIMENTICATA ──────────────────────────────────────────────────────

@router.get("/password-dimenticata", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="password_dimenticata.html", context={}
    )


@router.post("/password-dimenticata")
@limiter.limit("3/minute")
def forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = _find_user(db, email)

    if user:
        token = secrets.token_urlsafe(32)
        scadenza = (datetime.now() + timedelta(hours=2)).isoformat()
        user.token_reset = token
        user.token_reset_scadenza = scadenza
        db.commit()

        dest_email = user.email or user.username
        if "@" in (dest_email or ""):
            from app.services.email import invia_reset_password
            import threading
            threading.Thread(
                target=invia_reset_password,
                args=(dest_email, token, _base_url(request)),
                daemon=True,
            ).start()

    # Risposta identica sia che l'utente esista o no (anti-enumeration)
    return RedirectResponse(url="/password-dimenticata?inviato=1", status_code=303)


# ── RESET PASSWORD (token da email) ──────────────────────────────────────────

@router.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_token_page(token: str, request: Request, db: Session = Depends(get_db)):
    user = db.query(Utente).filter(Utente.token_reset == token).first()

    scaduto = False
    if user and user.token_reset_scadenza:
        try:
            scaduto = datetime.now() > datetime.fromisoformat(user.token_reset_scadenza)
        except ValueError:
            scaduto = True

    if not user or scaduto:
        return templates.TemplateResponse(
            request=request, name="reset_password_token.html",
            context={"token": token, "errore": "Link non valido o scaduto. Richiedi un nuovo reset.", "successo": None},
        )

    return templates.TemplateResponse(
        request=request, name="reset_password_token.html",
        context={"token": token, "errore": None, "successo": None},
    )


@router.post("/reset-password/{token}")
def reset_password_token(
    token: str,
    request: Request,
    nuova_password: str = Form(...),
    conferma_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(Utente).filter(Utente.token_reset == token).first()

    scaduto = False
    if user and user.token_reset_scadenza:
        try:
            scaduto = datetime.now() > datetime.fromisoformat(user.token_reset_scadenza)
        except ValueError:
            scaduto = True

    if not user or scaduto:
        return templates.TemplateResponse(
            request=request, name="reset_password_token.html",
            context={"token": token, "errore": "Link non valido o scaduto.", "successo": None},
        )

    if nuova_password != conferma_password:
        return templates.TemplateResponse(
            request=request, name="reset_password_token.html",
            context={"token": token, "errore": "Le password non coincidono.", "successo": None},
        )

    if len(nuova_password) < 8:
        return templates.TemplateResponse(
            request=request, name="reset_password_token.html",
            context={"token": token, "errore": "La password deve essere di almeno 8 caratteri.", "successo": None},
        )

    user.password = hash_password(nuova_password)
    user.token_reset = None
    user.token_reset_scadenza = None
    db.commit()

    return RedirectResponse(url="/login?reset=1", status_code=303)


# ── LOGOUT ────────────────────────────────────────────────────────────────────

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ── VECCHIO RESET (mantenuto per retrocompatibilità) ──────────────────────────

@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_legacy_page(request: Request):
    return RedirectResponse(url="/password-dimenticata", status_code=301)
