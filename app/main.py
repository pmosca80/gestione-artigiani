from pathlib import Path
import os

from dotenv import load_dotenv

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from app.csrf import CSRFMiddleware
from app.security_headers import SecurityHeadersMiddleware
from app.templates_config import templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes import clienti, lavori, auth, materiali, impostazioni, documenti, fatture, piani, team, onboarding, preventivi_template, firma, garanzie, prima_nota, notifiche_push, export_contabilita, listino, lavori_sal, lavori_rapportini, scadenzario, portale_cliente, lavori_timesheet, stripe_webhook, fatture_acquisto, audit
from app.dependencies import NotAuthenticated, AccountScaduto, AccountDisattivato, AccessoNegato, get_current_user, scope_collaboratore
from app import models, crud
from app.models import Cliente, Lavoro, Materiale
from app.logger import get_logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.notifiche import controlla_scadenze
from app.services.backup import esegui_backup, verifica_ripristino_backup
from app.services.reminder_fatture import controlla_fatture_non_pagate
from app.services.garanzie_reminder import controlla_garanzie
from app.limiter import limiter
from slowapi.errors import RateLimitExceeded

logger = get_logger("main")


# Carica variabili dal file .env
load_dotenv(override=False)

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.05,
        send_default_pii=False,
    )
    logger.info("Sentry attivato")

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.getenv("SECRET_KEY", "")

if not SECRET_KEY or SECRET_KEY == "dev-secret-key" or len(SECRET_KEY) < 20:
    raise RuntimeError(
        "SECRET_KEY non impostata o non valida nel file .env. "
        "Imposta una chiave random di almeno 20 caratteri."
    )


# Schema gestito da Alembic — vedi alembic/versions/
# Il Procfile esegue "alembic upgrade head" prima di avviare gunicorn.

app = FastAPI(
    title="Mastro"
)

app.state.limiter = limiter

_MAX_BODY_BYTES = 15 * 1024 * 1024  # 15 MB — copre foto/allegati reali, protegge da payload bomb

@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_BYTES:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Payload troppo grande."}, status_code=413)
    return await call_next(request)

app.add_middleware(CSRFMiddleware)
_https_only = bool(os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("RAILWAY_PROJECT_ID"))
app.add_middleware(SecurityHeadersMiddleware, https_only=_https_only)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=86400 * 30,
    same_site="lax",
    https_only=_https_only,
)

templates.env.globals["VAPID_PUBLIC_KEY"] = os.getenv("VAPID_PUBLIC_KEY", "")


@app.get("/health")
def health():
    """Liveness check leggero, senza DB: serve a distinguere "processo vivo"
    da "app funzionante" (quest'ultimo richiede una query, vedi "/")."""
    return {"status": "ok"}

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

Path("uploads").mkdir(exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)
app.include_router(auth.router)
app.include_router(clienti.router)
app.include_router(lavori.router)
app.include_router(materiali.router)
app.include_router(impostazioni.router)
app.include_router(documenti.router)
app.include_router(fatture.router)
app.include_router(piani.router)
app.include_router(team.router)
app.include_router(onboarding.router)
app.include_router(preventivi_template.router)
app.include_router(firma.router)
app.include_router(garanzie.router)
app.include_router(prima_nota.router)
app.include_router(notifiche_push.router)
app.include_router(export_contabilita.router)
app.include_router(listino.router)
app.include_router(lavori_sal.router)
app.include_router(lavori_rapportini.router)
app.include_router(scadenzario.router)
app.include_router(portale_cliente.router)
app.include_router(lavori_timesheet.router)
app.include_router(stripe_webhook.router)
app.include_router(fatture_acquisto.router)
app.include_router(audit.router)

@app.get("/api/cerca")
def cerca_globale(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    q = q.strip()
    if len(q) < 2:
        return {"clienti": [], "lavori": [], "materiali": []}

    like = f"%{q}%"
    scope = scope_collaboratore(request, db)

    clienti_query = db.query(Cliente).filter(
        Cliente.utente_id == user_id,
        or_(
            Cliente.nome.ilike(like),
            Cliente.cognome.ilike(like),
            Cliente.ragione_sociale.ilike(like),
            Cliente.telefono.ilike(like),
            Cliente.email.ilike(like),
        )
    )
    if scope is not None:
        # Stessa regola di visibilità di crud.get_clienti: un collaboratore
        # vede solo i clienti con un lavoro assegnato a lui, oppure i
        # clienti senza alcun lavoro (non ancora "reclamati" da nessuno).
        assegnati_sub = db.query(Lavoro.cliente_id).filter(Lavoro.assegnato_a_id == scope)
        con_lavori_sub = db.query(Lavoro.cliente_id)
        clienti_query = clienti_query.filter(
            or_(Cliente.id.in_(assegnati_sub), Cliente.id.notin_(con_lavori_sub))
        )
    clienti_qs = clienti_query.limit(5).all()

    lavori_query = db.query(Lavoro).filter(
        Lavoro.utente_id == user_id,
        or_(
            Lavoro.titolo.ilike(like),
            Lavoro.descrizione.ilike(like),
        )
    )
    if scope is not None:
        lavori_query = lavori_query.filter(Lavoro.assegnato_a_id == scope)
    lavori_qs = lavori_query.order_by(Lavoro.data_creazione.desc()).limit(5).all()

    materiali_qs = db.query(Materiale).filter(
        Materiale.utente_id == user_id,
        or_(
            Materiale.nome.ilike(like),
            Materiale.categoria.ilike(like),
            Materiale.note.ilike(like),
        )
    ).limit(5).all()

    def fmt_cliente(c):
        if c.tipo_cliente == "azienda":
            label = c.ragione_sociale or "—"
        else:
            label = f"{c.nome or ''} {c.cognome or ''}".strip() or "—"
        return {"label": label, "sub": c.telefono or c.email or "", "url": f"/clienti/{c.id}"}

    def fmt_lavoro(l):
        cliente_nome = ""
        if l.cliente:
            if l.cliente.tipo_cliente == "azienda":
                cliente_nome = l.cliente.ragione_sociale or ""
            else:
                cliente_nome = f"{l.cliente.nome or ''} {l.cliente.cognome or ''}".strip()
        return {"label": l.titolo or f"Lavoro #{l.id}", "sub": cliente_nome, "url": f"/lavori/{l.id}"}

    def fmt_materiale(m):
        return {
            "label": m.nome,
            "sub": f"{m.quantita} {m.unita_misura or ''} · {m.categoria or ''}".strip(" ·"),
            "url": f"/materiali/",
        }

    return {
        "clienti": [fmt_cliente(c) for c in clienti_qs],
        "lavori": [fmt_lavoro(l) for l in lavori_qs],
        "materiali": [fmt_materiale(m) for m in materiali_qs],
    }


@app.get("/sw.js")
def service_worker():
    from fastapi.responses import FileResponse
    return FileResponse(str(BASE_DIR / "static" / "sw.js"), media_type="application/javascript")

@app.get("/offline", response_class=HTMLResponse)
def offline_page(request: Request):
    return templates.TemplateResponse(request=request, name="offline.html", context={})

@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html", context={})

@app.get("/termini", response_class=HTMLResponse)
def termini_servizio(request: Request):
    return templates.TemplateResponse(request=request, name="termini.html", context={})


@app.get("/guida", response_class=HTMLResponse)
def guida(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="guida.html",
        context={}
    )

scheduler = BackgroundScheduler(timezone="Europe/Rome")
scheduler.add_job(
    controlla_scadenze,
    trigger=CronTrigger(hour=8, minute=0),
    id="controlla_scadenze",
    replace_existing=True,
)
scheduler.add_job(
    esegui_backup,
    trigger=CronTrigger(hour=2, minute=0),
    id="backup_giornaliero",
    replace_existing=True,
)
scheduler.add_job(
    verifica_ripristino_backup,
    trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
    id="verifica_ripristino_backup",
    replace_existing=True,
)
scheduler.add_job(
    controlla_fatture_non_pagate,
    trigger=CronTrigger(hour=8, minute=30),
    id="reminder_fatture",
    replace_existing=True,
)
scheduler.add_job(
    controlla_garanzie,
    trigger=CronTrigger(hour=9, minute=0),
    id="reminder_garanzie",
    replace_existing=True,
)
scheduler.start()
logger.info("Scheduler avviato — scadenze 08:00, fatture 08:30, garanzie 09:00, backup 02:00, verifica ripristino domenica 03:00")


@app.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
):
    from app.services.piani import get_piano, conta_clienti, LIMITE_CLIENTI_FREE

    raw_user_id = request.session.get("user_id")
    if not raw_user_id:
        return templates.TemplateResponse(request=request, name="landing.html", context={})

    # Risolve l'ID effettivo: per i collaboratori usa l'ID del titolare
    from app.models import Utente as _Utente
    _raw_utente = db.query(_Utente).filter(_Utente.id == raw_user_id).first()
    if not _raw_utente or _raw_utente.attivo == 0:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    _titolare_id = getattr(_raw_utente, "titolare_id", None)
    if _titolare_id:
        # Collaboratore: se il titolare ha cancellato/disattivato l'account,
        # blocca anche qui — ogni altra route lo fa già tramite get_current_user.
        _titolare = db.query(_Utente).filter(_Utente.id == _titolare_id).first()
        if not _titolare or _titolare.attivo == 0:
            request.session.clear()
            return RedirectResponse(url="/login", status_code=303)

    user_id = _titolare_id or raw_user_id

    azienda = crud.get_impostazioni_azienda(db, user_id)
    if not _raw_utente.onboarding_done and not request.session.get("is_collaboratore"):
        request.session["onboarding_step"] = 1
        return RedirectResponse(url="/onboarding", status_code=303)

    piano_corrente = get_piano(db, user_id)
    n_clienti = conta_clienti(db, user_id)

    stats = crud.get_dashboard_pro(db, user_id)

    notifiche = crud.get_notifiche_dashboard(db, user_id)

    classifica_clienti = crud.get_classifica_clienti(db, user_id)

    lavori_redditizi = crud.get_lavori_piu_redditizi(db, user_id)

    cliente_top = None
    if classifica_clienti:
        cliente_top = classifica_clienti[0]

    # Calcolo giorni rimasti nel trial (del titolare, non del collaboratore)
    trial_giorni_rimasti = None
    trial_tipo = None
    utente_obj = db.query(_Utente).filter(_Utente.id == user_id).first()
    if utente_obj and utente_obj.username != "admin":
        if piano_corrente == "free" and getattr(utente_obj, "attivo", 1) != 2 and utente_obj.data_registrazione:
            try:
                dr = utente_obj.data_registrazione
                reg = dr if not isinstance(dr, str) else datetime.strptime(dr, "%Y-%m-%d").date()
                rimasti = 30 - (datetime.now().date() - reg).days
                if rimasti > 0:
                    trial_giorni_rimasti = rimasti
                    trial_tipo = "free"
            except Exception:
                pass
        elif (piano_corrente == "pro"
              and getattr(utente_obj, "pro_scadenza", None)
              and not getattr(utente_obj, "stripe_subscription_id", None)):
            try:
                ps = utente_obj.pro_scadenza
                scad = ps if not isinstance(ps, str) else datetime.strptime(ps, "%Y-%m-%d").date()
                rimasti = (scad - datetime.now().date()).days
                if rimasti >= 0:
                    trial_giorni_rimasti = rimasti
                    trial_tipo = "promo_pro"
            except Exception:
                pass

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "stats": stats,
            "oggi": datetime.now().strftime("%Y-%m-%d"),
            "notifiche": notifiche,
            "classifica_clienti": classifica_clienti,
            "cliente_top": cliente_top,
            "lavori_redditizi": lavori_redditizi,
            "piano_corrente": piano_corrente,
            "n_clienti": n_clienti,
            "limite_free": LIMITE_CLIENTI_FREE,
            "trial_giorni_rimasti": trial_giorni_rimasti,
            "trial_tipo": trial_tipo,
        }
    )

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"errore": "Troppi tentativi di accesso. Riprova tra 1 minuto."},
        status_code=429,
    )


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login", status_code=303)

@app.exception_handler(AccountScaduto)
async def account_scaduto_handler(request: Request, exc: AccountScaduto):
    return RedirectResponse(url="/piani?trial_scaduto=1", status_code=303)


@app.exception_handler(AccountDisattivato)
async def account_disattivato_handler(request: Request, exc: AccountDisattivato):
    return templates.TemplateResponse(
        request=request,
        name="trial_scaduto.html",
        context={"disattivato": True},
        status_code=403
    )

@app.exception_handler(AccessoNegato)
async def accesso_negato_handler(request: Request, exc: AccessoNegato):
    return RedirectResponse(url="/?errore=area_riservata", status_code=303)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Errore non gestito | {request.method} {request.url} | {type(exc).__name__}: {exc}"
    )
    return templates.TemplateResponse(
        request=request,
        name="errore.html",
        context={"messaggio": "Si è verificato un errore. Riprova tra qualche minuto."},
        status_code=500
    )