from pathlib import Path
import os

from dotenv import load_dotenv

from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.routes import clienti, lavori, auth, materiali, impostazioni, documenti
from app import models, crud


# Carica variabili dal file .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Chiave sessione: in produzione va messa nel file .env
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

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

app.include_router(auth.router)
app.include_router(clienti.router)
app.include_router(lavori.router)
app.include_router(materiali.router)
app.include_router(impostazioni.router)
app.include_router(documenti.router)


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    if "user_id" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session["user_id"]
    stats = crud.get_dashboard_pro(db, user_id)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"stats": stats}
    )