from pathlib import Path
import os

from dotenv import load_dotenv

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.routes import clienti, lavori, auth, materiali, impostazioni, documenti
from app.dependencies import NotAuthenticated, AccountScaduto, AccountDisattivato, get_current_user
from app import models, crud
from app.logger import get_logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.notifiche import controlla_scadenze

logger = get_logger("main")


# Carica variabili dal file .env
load_dotenv(override=False)

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.getenv("SECRET_KEY", "")

if not SECRET_KEY or SECRET_KEY == "dev-secret-key" or len(SECRET_KEY) < 20:
    raise RuntimeError(
        "SECRET_KEY non impostata o non valida nel file .env. "
        "Imposta una chiave random di almeno 20 caratteri."
    )

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Gestione Artigiani"
)

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
scheduler.start()
logger.info("Scheduler avviato — controllo scadenze ogni giorno alle 08:00")


@app.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user),
):
    azienda = crud.get_impostazioni_azienda(db, user_id)
    if not azienda or not azienda.nome_azienda:
        return RedirectResponse(url="/impostazioni/onboarding", status_code=303)

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
        }
    )

@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login", status_code=303)

@app.exception_handler(AccountScaduto)
async def account_scaduto_handler(request: Request, exc: AccountScaduto):
    return templates.TemplateResponse(
        request=request,
        name="trial_scaduto.html",
        context={},
        status_code=403
    )


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