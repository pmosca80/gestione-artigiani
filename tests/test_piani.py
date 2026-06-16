"""
Test per app/services/piani.py.

Le funzioni di feature-gating sono pure (solo stringhe) e testabili
senza DB. Le tre funzioni con DB usano le fixture di conftest.
"""
from datetime import date
import pytest

from app import models
from app.services.piani import (
    ha_fatturapa, ha_export, ha_team, ha_backup, ha_email_invio,
    max_collaboratori, get_limite_clienti,
    get_piano, is_pro, puo_aggiungere_cliente,
)

oggi = date.today()


# ── ha_fatturapa / ha_export — starter+ ──────────────────────────────────────

def test_ha_fatturapa_free_no():
    assert ha_fatturapa("free") is False

def test_ha_fatturapa_starter_si():
    assert ha_fatturapa("starter") is True

def test_ha_fatturapa_pro_si():
    assert ha_fatturapa("pro") is True

def test_ha_export_free_no():
    assert ha_export("free") is False

def test_ha_export_starter_si():
    assert ha_export("starter") is True


# ── ha_team / ha_backup / ha_email_invio — pro+ ──────────────────────────────

def test_ha_team_free_no():
    assert ha_team("free") is False

def test_ha_team_starter_no():
    assert ha_team("starter") is False

def test_ha_team_pro_si():
    assert ha_team("pro") is True

def test_ha_team_business_si():
    assert ha_team("business") is True

def test_ha_backup_starter_no():
    assert ha_backup("starter") is False

def test_ha_backup_pro_si():
    assert ha_backup("pro") is True

def test_ha_email_invio_starter_no():
    assert ha_email_invio("starter") is False

def test_ha_email_invio_pro_si():
    assert ha_email_invio("pro") is True


# ── max_collaboratori ─────────────────────────────────────────────────────────

def test_max_collaboratori_free():
    assert max_collaboratori("free") == 0

def test_max_collaboratori_starter():
    assert max_collaboratori("starter") == 0

def test_max_collaboratori_pro():
    assert max_collaboratori("pro") == 3

def test_max_collaboratori_business():
    assert max_collaboratori("business") is None


# ── get_limite_clienti ────────────────────────────────────────────────────────

def test_limite_clienti_free():
    assert get_limite_clienti("free") == 5

def test_limite_clienti_starter():
    assert get_limite_clienti("starter") == 30

def test_limite_clienti_pro():
    assert get_limite_clienti("pro") is None

def test_limite_clienti_business():
    assert get_limite_clienti("business") is None

def test_limite_clienti_none_come_free():
    """Piano None (non impostato) → trattato come free → limite 5."""
    assert get_limite_clienti(None) == 5

def test_limite_clienti_piano_sconosciuto():
    """Piano inesistente → fallback a free → limite 5."""
    assert get_limite_clienti("enterprise") == 5


# ── get_piano con DB ──────────────────────────────────────────────────────────

def test_get_piano_utente_pro(db, utente_test):
    """utente_test ha piano='pro' dal fixture conftest."""
    assert get_piano(db, utente_test.id) == "pro"


def test_get_piano_utente_inesistente(db):
    """Utente non trovato → piano di default 'free'."""
    assert get_piano(db, 999999) == "free"


def test_get_piano_admin_override(db):
    """Utente con username='admin' riceve sempre piano 'business'."""
    admin = models.Utente(
        username="admin",
        password="x",
        piano="free",   # anche se il piano è free, l'override lo porta a business
        attivo=2,
        onboarding_done=True,
        data_registrazione=str(oggi),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    assert get_piano(db, admin.id) == "business"


# ── is_pro con DB ─────────────────────────────────────────────────────────────

def test_is_pro_piano_pro(db, utente_test):
    assert is_pro(db, utente_test.id) is True


def test_is_pro_piano_free(db):
    u = models.Utente(
        username="free@test.it", password="x", piano="free",
        attivo=2, onboarding_done=True, data_registrazione=str(oggi),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    assert is_pro(db, u.id) is False


def test_is_pro_piano_starter(db):
    u = models.Utente(
        username="starter@test.it", password="x", piano="starter",
        attivo=2, onboarding_done=True, data_registrazione=str(oggi),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    assert is_pro(db, u.id) is True


# ── puo_aggiungere_cliente con DB ─────────────────────────────────────────────

def _crea_clienti(db, utente_id, n):
    for i in range(n):
        db.add(models.Cliente(
            utente_id=utente_id,
            tipo_cliente="privato",
            nome=f"Cliente{i}",
            cognome="Test",
            data_creazione=str(oggi),
        ))
    db.commit()


def test_puo_aggiungere_cliente_free_sotto_limite(db):
    u = models.Utente(
        username="fl1@test.it", password="x", piano="free",
        attivo=2, onboarding_done=True, data_registrazione=str(oggi),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    _crea_clienti(db, u.id, 4)   # 4 clienti su 5 → può aggiungere

    assert puo_aggiungere_cliente(db, u.id) is True


def test_puo_aggiungere_cliente_free_al_limite(db):
    u = models.Utente(
        username="fl2@test.it", password="x", piano="free",
        attivo=2, onboarding_done=True, data_registrazione=str(oggi),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    _crea_clienti(db, u.id, 5)   # 5 clienti su 5 → NON può aggiungere

    assert puo_aggiungere_cliente(db, u.id) is False


def test_puo_aggiungere_cliente_pro_illimitato(db, utente_test):
    """Piano pro → limite=None → può sempre aggiungere."""
    _crea_clienti(db, utente_test.id, 100)

    assert puo_aggiungere_cliente(db, utente_test.id) is True
