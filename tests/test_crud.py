"""
Test per le funzioni in crud.py.
Nessuna chiamata HTTP — si testa la logica pura con sessione DB diretta.
"""
from datetime import date, timedelta
from app import crud, models


def _crea_lavoro_con_fattura(db, utente_id, cliente_id, importo=1000.0):
    """Helper: crea Lavoro + ImpostazioniAzienda per test fatturazione."""
    if not db.query(models.ImpostazioniAzienda).filter(
        models.ImpostazioniAzienda.utente_id == utente_id
    ).first():
        db.add(models.ImpostazioniAzienda(
            utente_id=utente_id,
            nome_azienda="Test Srl",
            partita_iva="12345678901",
            email="owner@example.com",
            ultimo_numero_fattura=0,
        ))
        db.commit()

    lavoro = models.Lavoro(
        utente_id=utente_id,
        cliente_id=cliente_id,
        titolo="Lavoro fatturabile",
        data_lavoro=date.today(),
        stato="completato",
        priorita="normale",
        importo_consuntivo=importo,
        aliquota_iva=22.0,
        totale_iva=round(importo * 0.22, 2),
        totale_documento=round(importo * 1.22, 2),
        stato_pagamento="da_pagare",
        residuo_pagamento=round(importo * 1.22, 2),
        data_creazione=str(date.today()),
    )
    db.add(lavoro)
    db.commit()
    db.refresh(lavoro)
    return lavoro


# ── get_notifiche_dashboard ───────────────────────────────────────────────────

def test_notifiche_garanzia_in_scadenza(db, utente_test, cliente_test):
    """
    Regressione: crashava con TypeError se data_scadenza (date) veniva
    confrontata con tra_30 (str). La garanzia entro 30gg deve essere contata.
    """
    g = models.Garanzia(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        descrizione="Caldaia Sig. Rossi",
        data_installazione=date.today(),
        data_scadenza=date.today() + timedelta(days=10),
        durata_mesi=24,
        data_creazione=str(date.today()),
    )
    db.add(g)
    db.commit()

    result = crud.get_notifiche_dashboard(db, utente_test.id)

    assert isinstance(result, dict)
    assert result["garanzie_scadenza"] == 1


def test_notifiche_garanzia_oltre_30gg_non_conta(db, utente_test, cliente_test):
    """Garanzia che scade tra 60 giorni non rientra nell'alert."""
    g = models.Garanzia(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        descrizione="Impianto nuovo",
        data_installazione=date.today(),
        data_scadenza=date.today() + timedelta(days=60),
        durata_mesi=24,
        data_creazione=str(date.today()),
    )
    db.add(g)
    db.commit()

    result = crud.get_notifiche_dashboard(db, utente_test.id)

    assert result["garanzie_scadenza"] == 0


def test_notifiche_lavori_oggi(db, utente_test, cliente_test):
    """Un lavoro con data_lavoro=oggi viene contato in lavori_oggi."""
    l = models.Lavoro(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        titolo="Lavoro urgente",
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="alta",
        data_creazione=str(date.today()),
    )
    db.add(l)
    db.commit()

    result = crud.get_notifiche_dashboard(db, utente_test.id)

    assert result["lavori_oggi"] == 1
    assert result["lavori_aperti"] >= 1


def test_notifiche_pagamenti_scaduti(db, utente_test, cliente_test):
    """Lavoro con scadenza pagamento nel passato e residuo > 0 → alert."""
    l = models.Lavoro(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        titolo="Lavoro non pagato",
        data_lavoro=date.today(),
        stato="completato",
        priorita="normale",
        data_scadenza_pagamento=date.today() - timedelta(days=5),
        residuo_pagamento=500.0,
        importo_pagato=0.0,
        data_creazione=str(date.today()),
    )
    db.add(l)
    db.commit()

    result = crud.get_notifiche_dashboard(db, utente_test.id)

    assert result["pagamenti_scaduti"] == 1


# ── get_clienti ───────────────────────────────────────────────────────────────

def test_get_clienti_isolamento_utente(db, utente_test):
    """Un utente non vede i clienti di un altro utente."""
    altro = models.Utente(
        username="altro@example.com",
        password="x",
        attivo=1,
        onboarding_done=True,
        data_registrazione=str(date.today()),
    )
    db.add(altro)
    db.commit()

    c_mio = models.Cliente(
        utente_id=utente_test.id,
        tipo_cliente="privato",
        nome="Cliente Mio",
        cognome="Test",
        data_creazione=str(date.today()),
    )
    c_altrui = models.Cliente(
        utente_id=altro.id,
        tipo_cliente="privato",
        nome="Cliente Altrui",
        cognome="Test",
        data_creazione=str(date.today()),
    )
    db.add_all([c_mio, c_altrui])
    db.commit()

    result = crud.get_clienti(db, utente_id=utente_test.id)

    assert result["totale"] == 1
    assert result["items"][0].nome == "Cliente Mio"


def test_get_clienti_ricerca(db, utente_test):
    """La ricerca filtra per nome/cognome."""
    for nome in ["Rossi", "Bianchi", "Verdi"]:
        db.add(models.Cliente(
            utente_id=utente_test.id,
            tipo_cliente="privato",
            nome=nome,
            cognome="Test",
            data_creazione=str(date.today()),
        ))
    db.commit()

    result = crud.get_clienti(db, utente_id=utente_test.id, cerca="Bianchi")

    assert result["totale"] == 1
    assert result["items"][0].nome == "Bianchi"


# ── _controlla (regressione: strptime su FlexDate) ───────────────────────────

def test_controlla_scadenze_trova_pagamento_scaduto(db, utente_test, cliente_test):
    """
    Regressione: notifiche.py usava strptime() su data_scadenza_pagamento che
    è FlexDate → restituisce già un date object → TypeError silenzioso → zero
    reminder inviati su PostgreSQL. Verifica che _controlla() trovi il lavoro.
    """
    from unittest.mock import patch
    from app.services.notifiche import _controlla

    lavoro = models.Lavoro(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        titolo="Lavoro non pagato",
        data_lavoro=date.today(),
        stato="completato",
        priorita="normale",
        stato_pagamento="da_pagare",
        residuo_pagamento=500.0,
        data_scadenza_pagamento=date.today() - timedelta(days=7),
        data_creazione=str(date.today()),
    )
    db.add(lavoro)
    db.add(models.ImpostazioniAzienda(
        utente_id=utente_test.id,
        nome_azienda="Idraulica Rossi",
        email="owner@example.com",
    ))
    db.commit()

    with patch("app.services.notifiche.invia_email", return_value=True) as mock_email, \
         patch("app.services.notifiche.invia_push"):
        contatore = _controlla(db)

    assert contatore == 1
    mock_email.assert_called_once()
    oggetto = mock_email.call_args[0][1]
    assert "Mario" in oggetto or "Rossi" in oggetto


def test_controlla_scadenze_salta_pagato(db, utente_test, cliente_test):
    """Lavoro già pagato non genera reminder."""
    from unittest.mock import patch
    from app.services.notifiche import _controlla

    db.add(models.Lavoro(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        titolo="Già pagato",
        data_lavoro=date.today(),
        stato="completato",
        priorita="normale",
        stato_pagamento="pagato",
        residuo_pagamento=0.0,
        data_scadenza_pagamento=date.today() - timedelta(days=7),
        data_creazione=str(date.today()),
    ))
    db.commit()

    with patch("app.services.notifiche.invia_email", return_value=True) as mock_email, \
         patch("app.services.notifiche.invia_push"):
        contatore = _controlla(db)

    assert contatore == 0
    mock_email.assert_not_called()


def test_controlla_scadenze_salta_scadenza_futura(db, utente_test, cliente_test):
    """Lavoro con scadenza tra 15 giorni (non in soglia) non genera reminder."""
    from unittest.mock import patch
    from app.services.notifiche import _controlla

    db.add(models.Lavoro(
        utente_id=utente_test.id,
        cliente_id=cliente_test.id,
        titolo="Scadenza lontana",
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        stato_pagamento="da_pagare",
        residuo_pagamento=800.0,
        data_scadenza_pagamento=date.today() + timedelta(days=15),
        data_creazione=str(date.today()),
    ))
    db.commit()

    with patch("app.services.notifiche.invia_email", return_value=True) as mock_email, \
         patch("app.services.notifiche.invia_push"):
        contatore = _controlla(db)

    assert contatore == 0
    mock_email.assert_not_called()


# ── Fatturazione: genera_numero_fattura ───────────────────────────────────────

def test_genera_numero_fattura_incrementale(db, utente_test):
    """Il numero cresce ad ogni chiamata e l'anno è quello corrente."""
    from datetime import datetime as _dt
    db.add(models.ImpostazioniAzienda(
        utente_id=utente_test.id,
        nome_azienda="Test Srl",
        ultimo_numero_fattura=0,
    ))
    db.commit()

    anno1, n1 = crud.genera_numero_fattura(db, utente_test.id)
    anno2, n2 = crud.genera_numero_fattura(db, utente_test.id)

    assert anno1 == _dt.now().year
    assert n1 == 1
    assert n2 == 2


def test_genera_numero_fattura_reset_anno(db, utente_test):
    """Se ultimo_anno_fattura è diverso dall'anno corrente, riparte da 1."""
    from datetime import datetime as _dt
    db.add(models.ImpostazioniAzienda(
        utente_id=utente_test.id,
        nome_azienda="Test Srl",
        ultimo_numero_fattura=99,
        ultimo_anno_fattura=2020,
    ))
    db.commit()

    anno, numero = crud.genera_numero_fattura(db, utente_test.id)

    assert anno == _dt.now().year
    assert numero == 1


# ── Fatturazione: salva_fattura_emessa ────────────────────────────────────────

def test_salva_fattura_emessa_crea(db, utente_test, cliente_test):
    """Prima chiamata crea un nuovo record FatturaEmessa."""
    lavoro = _crea_lavoro_con_fattura(db, utente_test.id, cliente_test.id)

    fattura = crud.salva_fattura_emessa(
        db, utente_test.id, lavoro.id,
        numero=1, anno=2026,
        data_emissione=date.today(),
        imponibile=1000.0, iva=220.0, totale=1220.0,
        nome_file="IT12345678901_00001.xml",
    )

    assert fattura.id is not None
    assert fattura.numero == 1
    assert fattura.importo_totale == 1220.0
    assert fattura.stato == "emessa"


def test_salva_fattura_emessa_idempotente(db, utente_test, cliente_test):
    """Seconda chiamata sullo stesso lavoro aggiorna il record esistente."""
    lavoro = _crea_lavoro_con_fattura(db, utente_test.id, cliente_test.id)

    crud.salva_fattura_emessa(
        db, utente_test.id, lavoro.id,
        numero=1, anno=2026,
        data_emissione=date.today(),
        imponibile=1000.0, iva=220.0, totale=1220.0,
        nome_file="IT12345678901_00001.xml",
    )
    fattura2 = crud.salva_fattura_emessa(
        db, utente_test.id, lavoro.id,
        numero=1, anno=2026,
        data_emissione=date.today(),
        imponibile=1000.0, iva=220.0, totale=1500.0,
        nome_file="IT12345678901_00001_v2.xml",
    )

    tutti = db.query(models.FatturaEmessa).filter(
        models.FatturaEmessa.lavoro_id == lavoro.id
    ).all()
    assert len(tutti) == 1
    assert fattura2.importo_totale == 1500.0


# ── Fatturazione: aggiorna_pagamento_fattura ─────────────────────────────────

def test_aggiorna_pagamento_fattura_segna_pagato(db, utente_test, cliente_test):
    """Marca la fattura come pagata e aggiorna stato_pagamento del lavoro."""
    lavoro = _crea_lavoro_con_fattura(db, utente_test.id, cliente_test.id)
    fattura = crud.salva_fattura_emessa(
        db, utente_test.id, lavoro.id,
        numero=1, anno=2026,
        data_emissione=date.today(),
        imponibile=1000.0, iva=220.0, totale=1220.0,
        nome_file="IT12345678901_00001.xml",
    )

    crud.aggiorna_pagamento_fattura(db, fattura.id, utente_test.id, "pagato")

    db.refresh(lavoro)
    assert lavoro.stato_pagamento == "pagato"


def test_aggiorna_pagamento_fattura_altrui_no_effetto(db, utente_test, cliente_test):
    """Un utente non può modificare le fatture di un altro."""
    lavoro = _crea_lavoro_con_fattura(db, utente_test.id, cliente_test.id)
    fattura = crud.salva_fattura_emessa(
        db, utente_test.id, lavoro.id,
        numero=1, anno=2026,
        data_emissione=date.today(),
        imponibile=1000.0, iva=220.0, totale=1220.0,
        nome_file="IT12345678901_00001.xml",
    )

    altro = models.Utente(
        username="hacker@example.com", password="x",
        attivo=1, onboarding_done=True,
        data_registrazione=str(date.today()),
    )
    db.add(altro)
    db.commit()

    crud.aggiorna_pagamento_fattura(db, fattura.id, altro.id, "pagato")

    db.refresh(lavoro)
    assert lavoro.stato_pagamento == "da_pagare"


# ── Fatturazione: crea_nota_credito ──────────────────────────────────────────

def test_crea_nota_credito_td04(db, utente_test, cliente_test):
    """La nota di credito copia gli importi e imposta tipo_documento=TD04."""
    lavoro = _crea_lavoro_con_fattura(db, utente_test.id, cliente_test.id)
    # Usa genera_numero_fattura così il contatore è aggiornato (numero=1)
    anno_gen, numero_gen = crud.genera_numero_fattura(db, utente_test.id)
    fattura = crud.salva_fattura_emessa(
        db, utente_test.id, lavoro.id,
        numero=numero_gen, anno=anno_gen,
        data_emissione=date.today(),
        imponibile=1000.0, iva=220.0, totale=1220.0,
        nome_file="IT12345678901_00001.xml",
    )

    nc = crud.crea_nota_credito(db, utente_test.id, fattura.id)

    assert nc is not None
    assert nc.tipo_documento == "TD04"
    assert nc.fattura_rif_numero == fattura.numero
    assert nc.fattura_rif_anno == fattura.anno
    assert nc.importo_totale == fattura.importo_totale
    # La NC prende il numero successivo disponibile (2), non lo stesso (1)
    assert nc.numero == fattura.numero + 1


def test_crea_nota_credito_fattura_inesistente(db, utente_test):
    """Ritorna None se la fattura non esiste o appartiene ad altro utente."""
    result = crud.crea_nota_credito(db, utente_test.id, fattura_id=999999)
    assert result is None
