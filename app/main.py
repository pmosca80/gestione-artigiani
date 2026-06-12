from pathlib import Path
import os

from dotenv import load_dotenv

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.routes import clienti, lavori, auth, materiali, impostazioni, documenti, fatture, piani
from app.dependencies import NotAuthenticated, AccountScaduto, AccountDisattivato, get_current_user
from app import models, crud
from app.models import Cliente, Lavoro, Materiale
from app.logger import get_logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.notifiche import controlla_scadenze
from app.services.backup import esegui_backup
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

Base.metadata.create_all(bind=engine)

# Migrazione inline: aggiunge colonne aggiunte dopo il deploy iniziale
from sqlalchemy import text, inspect as _inspect
def _run_migrations():
    insp = _inspect(engine)
    cols = [c["name"] for c in insp.get_columns("utenti")]
    with engine.connect() as conn:
        if "pro_scadenza" not in cols:
            conn.execute(text("ALTER TABLE utenti ADD COLUMN pro_scadenza VARCHAR"))
            conn.commit()
_run_migrations()

app = FastAPI(
    title="Gestione Artigiani"
)

app.state.limiter = limiter

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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

@app.get("/api/cerca")
def cerca_globale(
    q: str = "",
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    q = q.strip()
    if len(q) < 2:
        return {"clienti": [], "lavori": [], "materiali": []}

    like = f"%{q}%"

    clienti_qs = db.query(Cliente).filter(
        Cliente.utente_id == user_id,
        or_(
            Cliente.nome.ilike(like),
            Cliente.cognome.ilike(like),
            Cliente.ragione_sociale.ilike(like),
            Cliente.telefono.ilike(like),
            Cliente.email.ilike(like),
        )
    ).limit(5).all()

    lavori_qs = db.query(Lavoro).filter(
        Lavoro.utente_id == user_id,
        or_(
            Lavoro.titolo.ilike(like),
            Lavoro.descrizione.ilike(like),
        )
    ).order_by(Lavoro.data_creazione.desc()).limit(5).all()

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


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html", context={})


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
scheduler.start()
logger.info("Scheduler avviato — scadenze 08:00, backup 02:00")


@app.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
):
    from app.services.piani import get_piano, conta_clienti, LIMITE_CLIENTI_FREE

    user_id = request.session.get("user_id")
    if not user_id:
        return templates.TemplateResponse(request=request, name="landing.html", context={})

    azienda = crud.get_impostazioni_azienda(db, user_id)
    if not azienda or not azienda.nome_azienda:
        return RedirectResponse(url="/impostazioni/onboarding", status_code=303)

    piano_corrente = get_piano(db, user_id)
    n_clienti = conta_clienti(db, user_id)

    stats = crud.get_dashboard_pro(db, user_id)

    notifiche = crud.get_notifiche_dashboard(
        db,
        user_id
    )

    classifica_clienti = crud.get_classifica_clienti(
        db,
        user_id
    )

    lavori_redditizi = crud.get_lavori_piu_redditizi(
        db,
        user_id
    )

    cliente_top = None

    if classifica_clienti:
        cliente_top = classifica_clienti[0]

    # Calcolo giorni rimasti nel trial (free o promo pro)
    trial_giorni_rimasti = None
    trial_tipo = None
    from app.models import Utente as _Utente
    utente_obj = db.query(_Utente).filter(_Utente.id == user_id).first()
    if utente_obj and utente_obj.username != "admin":
        if piano_corrente == "free" and getattr(utente_obj, "attivo", 1) != 2 and utente_obj.data_registrazione:
            try:
                data_reg = datetime.strptime(utente_obj.data_registrazione, "%Y-%m-%d")
                rimasti = 30 - (datetime.now() - data_reg).days
                if rimasti > 0:
                    trial_giorni_rimasti = rimasti
                    trial_tipo = "free"
            except Exception:
                pass
        elif (piano_corrente == "pro"
              and getattr(utente_obj, "pro_scadenza", None)
              and not getattr(utente_obj, "stripe_subscription_id", None)):
            try:
                scadenza = datetime.strptime(utente_obj.pro_scadenza, "%Y-%m-%d")
                rimasti = (scadenza.date() - datetime.now().date()).days
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