"""
Test per gli scheduler job:
- app/services/reminder_fatture._esegui(db)
- app/services/garanzie_reminder._esegui(db)

Usa la stessa db fixture dei test CRUD; mock di invia_email/invia_push
per evitare invii reali e verificare che il reminder sia recapitato.
"""
from datetime import date, timedelta
from unittest.mock import patch

from app import models
from app.services.reminder_fatture import _esegui as _esegui_fatture
from app.services.garanzie_reminder import _esegui as _esegui_garanzie

oggi = date.today()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utente_con_azienda(db, username, email_az="az@test.it"):
    u = models.Utente(
        username=username, password="x",
        attivo=2, onboarding_done=True,
        data_registrazione=str(oggi),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(models.ImpostazioniAzienda(
        utente_id=u.id,
        nome_azienda="Test Srl",
        partita_iva="12345678901",
        email=email_az,
        ultimo_numero_fattura=0,
    ))
    db.commit()
    return u


def _cliente(db, utente_id):
    c = models.Cliente(
        utente_id=utente_id,
        tipo_cliente="privato",
        nome="Mario", cognome="Rossi",
        data_creazione=str(oggi),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _fattura(db, utente_id, cliente_id, *,
             giorni_fa=31, stato_pagamento="da_pagare",
             tipo_documento="TD01", reminder_inviato=0):
    """Crea Lavoro + FatturaEmessa con scadenza relativa a oggi."""
    lavoro = models.Lavoro(
        utente_id=utente_id, cliente_id=cliente_id,
        titolo="Lavoro test",
        data_lavoro=oggi - timedelta(days=giorni_fa + 5),
        stato="completato", priorita="normale",
        importo_consuntivo=500.0, totale_documento=610.0,
        stato_pagamento=stato_pagamento,
        residuo_pagamento=610.0,
        data_scadenza_pagamento=oggi - timedelta(days=giorni_fa),
        data_creazione=str(oggi),
    )
    db.add(lavoro)
    db.commit()
    db.refresh(lavoro)

    fat = models.FatturaEmessa(
        utente_id=utente_id, lavoro_id=lavoro.id,
        numero=1, anno=oggi.year,
        data_emissione=oggi - timedelta(days=giorni_fa),
        importo_totale=610.0,
        stato="emessa",
        tipo_documento=tipo_documento,
        reminder_inviato=reminder_inviato,
        data_creazione=str(oggi),
    )
    db.add(fat)
    db.commit()
    db.refresh(fat)
    return fat


def _garanzia(db, utente_id, cliente_id, *,
              giorni_a_scadenza=15, reminder_30g=0, reminder_7g=0):
    """Crea Garanzia con scadenza relativa a oggi."""
    g = models.Garanzia(
        utente_id=utente_id, cliente_id=cliente_id,
        descrizione="Caldaia murale",
        data_installazione=oggi - timedelta(days=365),
        durata_mesi=24,
        data_scadenza=oggi + timedelta(days=giorni_a_scadenza),
        reminder_30g_inviato=reminder_30g,
        reminder_7g_inviato=reminder_7g,
        data_creazione=str(oggi),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# ── reminder_fatture._esegui ──────────────────────────────────────────────────

@patch("app.services.reminder_fatture.invia_push")
@patch("app.services.reminder_fatture.invia_email", return_value=True)
def test_reminder_fattura_scaduta_31g(mock_email, mock_push, db):
    """Fattura scaduta da 31 giorni → reminder_inviato incrementa a 1."""
    u = _utente_con_azienda(db, "rf1@test.it")
    cl = _cliente(db, u.id)
    fat = _fattura(db, u.id, cl.id, giorni_fa=31)

    _esegui_fatture(db)

    db.refresh(fat)
    assert fat.reminder_inviato == 1
    mock_email.assert_called_once()


@patch("app.services.reminder_fatture.invia_push")
@patch("app.services.reminder_fatture.invia_email", return_value=True)
def test_reminder_fattura_scaduta_61g_livello_2(mock_email, mock_push, db):
    """Fattura scaduta da 61 giorni e reminder_inviato=0 → sale subito a 2."""
    u = _utente_con_azienda(db, "rf2@test.it")
    cl = _cliente(db, u.id)
    fat = _fattura(db, u.id, cl.id, giorni_fa=61, reminder_inviato=0)

    _esegui_fatture(db)

    db.refresh(fat)
    assert fat.reminder_inviato == 2


@patch("app.services.reminder_fatture.invia_push")
@patch("app.services.reminder_fatture.invia_email", return_value=True)
def test_reminder_fattura_gia_al_livello_1_non_avanza(mock_email, mock_push, db):
    """Fattura a 31g con reminder già a 1 → livello non cambia, email non inviata."""
    u = _utente_con_azienda(db, "rf3@test.it")
    cl = _cliente(db, u.id)
    fat = _fattura(db, u.id, cl.id, giorni_fa=31, reminder_inviato=1)

    _esegui_fatture(db)

    db.refresh(fat)
    assert fat.reminder_inviato == 1
    mock_email.assert_not_called()


@patch("app.services.reminder_fatture.invia_push")
@patch("app.services.reminder_fatture.invia_email", return_value=True)
def test_reminder_td04_saltata(mock_email, mock_push, db):
    """Nota di credito TD04 → filtrata a livello SQL, reminder_inviato resta 0."""
    u = _utente_con_azienda(db, "rf4@test.it")
    cl = _cliente(db, u.id)
    fat = _fattura(db, u.id, cl.id, giorni_fa=31, tipo_documento="TD04")

    _esegui_fatture(db)

    db.refresh(fat)
    assert fat.reminder_inviato == 0
    mock_email.assert_not_called()


@patch("app.services.reminder_fatture.invia_push")
@patch("app.services.reminder_fatture.invia_email", return_value=True)
def test_reminder_lavoro_pagato_saltato(mock_email, mock_push, db):
    """Lavoro già segnato come pagato → loop lo salta, email non inviata."""
    u = _utente_con_azienda(db, "rf5@test.it")
    cl = _cliente(db, u.id)
    _fattura(db, u.id, cl.id, giorni_fa=31, stato_pagamento="pagato")

    _esegui_fatture(db)

    mock_email.assert_not_called()


@patch("app.services.reminder_fatture.invia_push")
@patch("app.services.reminder_fatture.invia_email", return_value=True)
def test_reminder_fattura_futura_saltata(mock_email, mock_push, db):
    """Fattura che scade tra 10 giorni → giorni negativi, non notificata."""
    u = _utente_con_azienda(db, "rf6@test.it")
    cl = _cliente(db, u.id)
    # giorni_fa negativo → data_scadenza_pagamento nel futuro
    fat = _fattura(db, u.id, cl.id, giorni_fa=-10)

    _esegui_fatture(db)

    db.refresh(fat)
    assert fat.reminder_inviato == 0
    mock_email.assert_not_called()


# ── garanzie_reminder._esegui ─────────────────────────────────────────────────

@patch("app.services.garanzie_reminder.invia_push")
@patch("app.services.garanzie_reminder.invia_email", return_value=True)
def test_garanzia_scade_15g_solo_reminder_30g(mock_email, mock_push, db):
    """Garanzia a 15 giorni → reminder_30g marcato, 7g ancora no."""
    u = _utente_con_azienda(db, "gr1@test.it")
    cl = _cliente(db, u.id)
    g = _garanzia(db, u.id, cl.id, giorni_a_scadenza=15)

    _esegui_garanzie(db)

    db.refresh(g)
    assert g.reminder_30g_inviato == 1
    assert g.reminder_7g_inviato == 0
    mock_email.assert_called_once()


@patch("app.services.garanzie_reminder.invia_push")
@patch("app.services.garanzie_reminder.invia_email", return_value=True)
def test_garanzia_scade_5g_entrambi_reminder(mock_email, mock_push, db):
    """Garanzia a 5 giorni → entrambi i reminder inviati nella stessa esecuzione."""
    u = _utente_con_azienda(db, "gr2@test.it")
    cl = _cliente(db, u.id)
    g = _garanzia(db, u.id, cl.id, giorni_a_scadenza=5)

    _esegui_garanzie(db)

    db.refresh(g)
    assert g.reminder_30g_inviato == 1
    assert g.reminder_7g_inviato == 1
    assert mock_email.call_count == 2


@patch("app.services.garanzie_reminder.invia_push")
@patch("app.services.garanzie_reminder.invia_email", return_value=True)
def test_garanzia_gia_notificata_non_ripete(mock_email, mock_push, db):
    """Garanzia già con entrambi i flag → email non inviata."""
    u = _utente_con_azienda(db, "gr3@test.it")
    cl = _cliente(db, u.id)
    _garanzia(db, u.id, cl.id, giorni_a_scadenza=5, reminder_30g=1, reminder_7g=1)

    _esegui_garanzie(db)

    mock_email.assert_not_called()


@patch("app.services.garanzie_reminder.invia_push")
@patch("app.services.garanzie_reminder.invia_email", return_value=True)
def test_garanzia_scaduta_non_notificata(mock_email, mock_push, db):
    """Garanzia già scaduta (giorni negativi) → fuori dalla finestra 0–30g."""
    u = _utente_con_azienda(db, "gr4@test.it")
    cl = _cliente(db, u.id)
    g = _garanzia(db, u.id, cl.id, giorni_a_scadenza=-5)

    _esegui_garanzie(db)

    db.refresh(g)
    assert g.reminder_30g_inviato == 0
    mock_email.assert_not_called()


@patch("app.services.garanzie_reminder.invia_push")
@patch("app.services.garanzie_reminder.invia_email", return_value=True)
def test_garanzia_45g_fuori_finestra(mock_email, mock_push, db):
    """Garanzia che scade tra 45 giorni → ancora oltre la soglia 30g."""
    u = _utente_con_azienda(db, "gr5@test.it")
    cl = _cliente(db, u.id)
    g = _garanzia(db, u.id, cl.id, giorni_a_scadenza=45)

    _esegui_garanzie(db)

    db.refresh(g)
    assert g.reminder_30g_inviato == 0
    mock_email.assert_not_called()
