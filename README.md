# Mastro

Gestionale SaaS per artigiani (clienti, lavori, preventivi, fatture, prima nota, magazzino). Backend FastAPI + SQLAlchemy + Jinja2, migrazioni con Alembic, deploy su Railway.

## Stack

- **Backend**: FastAPI, SQLAlchemy 2.x, Jinja2
- **Database**: SQLite in locale/test, PostgreSQL in produzione
- **Migrazioni**: Alembic
- **Deploy**: Railway (Nixpacks + Procfile), Gunicorn + Uvicorn workers
- **Python**: 3.11.9 (vedi `runtime.txt`)

## Setup ambiente locale

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements-dev.txt   # requirements.txt + pytest/httpx

copy .env.example .env          # Windows
# cp .env.example .env           # macOS/Linux
```

Apri `.env` e compila almeno `SECRET_KEY` (obbligatoria, l'app non parte senza). Tutte le altre variabili in `.env.example` sono opzionali: ogni integrazione mancante (email, Stripe, Cloudinary, push, backup S3, Sentry) disabilita semplicemente quella funzionalità senza bloccare l'avvio.

```bash
python -m alembic upgrade head   # crea lo schema (SQLite locale di default)
python -m uvicorn app.main:app --reload
```

L'app è su `http://127.0.0.1:8000`.

## Test

```bash
python -m pytest
```

La suite usa SQLite in-memory (vedi `tests/conftest.py`), non serve configurazione aggiuntiva. La CI (GitHub Actions, `.github/workflows/tests.yml`) esegue la stessa suite su ogni push/PR su `main`.

## Migrazioni

```bash
python -m alembic revision --autogenerate -m "descrizione"
python -m alembic upgrade head
```

Genera sempre le revisioni con `alembic revision`, non a mano: un `revision id` scritto a mano che collide con uno esistente crea due head e blocca il deploy (vedi `tests/test_alembic_heads.py`, che verifica una sola head e nessun id duplicato).

Lo storico delle migrazioni precedenti alla baseline unificata (`2480529b19e6`) è archiviato in `alembic/versions_archive/` per consultazione: non viene eseguito, ma resta leggibile.

## Deploy (Railway)

Il `Procfile` esegue `alembic upgrade head` prima di avviare Gunicorn: se la migrazione fallisce, l'app non parte. Le variabili d'ambiente di produzione si configurano nel pannello Railway (`Variables`), non in `.env` (che resta solo locale e non va mai committato).

## Script di utilità

- `check_routes.py` — elenca tutte le route registrate nell'app
- `controlla_admin.py` — diagnostica rapida sullo stato di un account
