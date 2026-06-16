"""
Fixtures condivise per tutti i test.

Ordine critico degli import:
1. os.environ PRIMA di qualsiasi import da app (dotenv usa override=False)
2. app.models PRIMA di create_all (registra le classi ORM con Base.metadata)
3. app.main DOPO create_all (altrimenti lo scheduler parte prima che le tabelle esistano)
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-per-pytest-almeno-20-chars")
os.environ.setdefault("VAPID_PUBLIC_KEY", "")
os.environ.setdefault("SENTRY_DSN", "")

from app.database import Base, engine, get_db
import app.models  # registra tutti i modelli con Base.metadata
Base.metadata.create_all(bind=engine)

from app.main import app
from app.dependencies import get_current_user
from app import models, crud

import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def reset_db():
    """Svuota tutte le tabelle dopo ogni test (rispettando FK)."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db():
    session = SessionTest()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def utente_test(db):
    u = models.Utente(
        username="test@example.com",
        password="$dummy$not$used$in$tests",  # auth è bypassata da override_user
        email="test@example.com",
        email_verificato=True,
        piano="pro",
        attivo=2,
        onboarding_done=True,
        ruolo="titolare",
        data_registrazione="2025-01-01",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def cliente_test(db, utente_test):
    c = models.Cliente(
        utente_id=utente_test.id,
        tipo_cliente="privato",
        nome="Mario",
        cognome="Rossi",
        telefono="3331234567",
        email="mario.rossi@example.com",
        data_creazione=str(date.today()),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lavoro_test(db, utente_test, cliente_test):
    l = models.Lavoro(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        titolo="Installazione impianto idraulico",
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        importo_preventivato=2000.0,
        ore_lavoro=8.0,
        costo_orario=35.0,
        aliquota_iva=22.0,
        sconto=0.0,
        importo_pagato=0.0,
        residuo_pagamento=2000.0,
        data_creazione=str(date.today()),
    )
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


@pytest.fixture
def client_http(db, utente_test):
    """TestClient con get_db e get_current_user sostituiti per i test."""
    def override_db():
        yield db

    def override_user():
        return utente_test.id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
