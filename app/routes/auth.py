from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Utente
from app.security import hash_password, verify_password

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(Utente).filter(Utente.username == username).first()

    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"errore": "Credenziali errate"}
        )

    password_ok = False

    try:
        password_ok = verify_password(password, user.password)
    except Exception:
        password_ok = False

    if not password_ok and user.password == password:
        user.password = hash_password(password)
        db.commit()
        password_ok = True

    if not password_ok:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"errore": "Credenziali errate"}
        )

    request.session.clear()
    request.session["user_id"] = user.id

    return RedirectResponse(url="/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={}
    )


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    esiste = db.query(Utente).filter(Utente.username == username).first()

    if esiste:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"errore": "Username già esistente"}
        )

    nuovo = Utente(
        username=username,
        password=hash_password(password)
    )

    db.add(nuovo)
    db.commit()

    return RedirectResponse(url="/login", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)