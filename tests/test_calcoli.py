"""
Test per app/services/calcoli.py.
Logica di calcolo totali lavoro: manodopera, materiali, IVA, margine, residuo.
"""
from datetime import date
from app.services.calcoli import calcola_totali_lavoro
from app import models


def _crea_lavoro(db, utente_id, cliente_id, **kwargs):
    defaults = dict(
        titolo="Test",
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        aliquota_iva=22.0,
        sconto=0.0,
        ore_lavoro=0.0,
        costo_orario=0.0,
        importo_pagato=0.0,
        data_creazione=str(date.today()),
    )
    defaults.update(kwargs)
    l = models.Lavoro(utente_id=utente_id, cliente_id=cliente_id, **defaults)
    db.add(l)
    db.commit()
    db.refresh(l)
    return l


def test_calcola_manodopera(db, utente_test, cliente_test):
    """8 ore × 35 €/h = 280 € manodopera."""
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=8.0, costo_orario=35.0)

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.totale_manodopera == 280.0


def test_calcola_iva_22(db, utente_test, cliente_test):
    """Imponibile 1000 € + IVA 22% = totale 1220 €."""
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=10.0, costo_orario=100.0,
                          aliquota_iva=22.0)

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.importo_consuntivo == 1000.0
    assert abs(risultato.totale_iva - 220.0) < 0.01
    assert abs(risultato.totale_documento - 1220.0) < 0.01


def test_residuo_non_negativo_se_pagato_in_eccesso(db, utente_test, cliente_test):
    """
    Se importo_pagato > totale_documento, residuo deve essere 0 (mai negativo).
    Questa è la fix presente in _run_migrations().
    """
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=1.0, costo_orario=100.0,
                          aliquota_iva=0.0,
                          importo_pagato=500.0)  # paga 500 su 100 dovuti

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.residuo_pagamento == 0.0


def test_stato_pagamento_parziale(db, utente_test, cliente_test):
    """Acconto versato: stato deve diventare 'acconto'."""
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=10.0, costo_orario=100.0,
                          aliquota_iva=0.0,
                          importo_pagato=500.0)  # 500 su 1000

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.stato_pagamento == "acconto"
    assert risultato.residuo_pagamento == 500.0


def test_stato_pagamento_saldato(db, utente_test, cliente_test):
    """Pagamento completo: stato 'pagato', residuo 0."""
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=10.0, costo_orario=100.0,
                          aliquota_iva=0.0,
                          importo_pagato=1000.0)

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.stato_pagamento == "pagato"
    assert risultato.residuo_pagamento == 0.0


def test_margine_con_costo_materiali(db, utente_test, cliente_test):
    """
    Margine = totale_documento - (costo_materiali + costo_manodopera).
    Se vendi i materiali a prezzo pieno, il margine è solo sulla manodopera.
    """
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=4.0, costo_orario=50.0,
                          aliquota_iva=0.0)

    # Materiale: costo 30 €, venduto a 30 € (margine zero sul materiale)
    mat = models.Materiale(
        utente_id=utente_test.id,
        nome="Tubo rame",
        quantita=10,
        data_creazione=str(date.today()),
    )
    db.add(mat)
    db.commit()

    uso = models.MaterialeUsatoLavoro(
        utente_id=utente_test.id,
        lavoro_id=lavoro.id,
        materiale_id=mat.id,
        quantita=2.0,
        costo_unitario=30.0,
        prezzo_unitario_cliente=30.0,
        data_creazione=str(date.today()),
    )
    db.add(uso)
    db.commit()

    risultato = calcola_totali_lavoro(db, lavoro.id)

    # Imponibile = 2*30 (materiali cliente) + 4*50 (manodopera) = 260
    # Costo reale = 2*30 (materiali costo) + 4*50 (manodopera) = 260
    # Margine = 260 - 260 = 0
    assert risultato.importo_consuntivo == 260.0
    assert risultato.margine == 0.0


def test_margine_con_ricarico_materiali(db, utente_test, cliente_test):
    """
    Materiale acquistato a 10 €, venduto a 20 €: genera margine sul materiale.
    Manodopera 0. Imponibile=40, costo_reale=20, margine=20. IVA 0%.
    """
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id, aliquota_iva=0.0)

    mat = models.Materiale(
        utente_id=utente_test.id,
        nome="Raccordo rame",
        quantita=10,
        data_creazione=str(date.today()),
    )
    db.add(mat)
    db.commit()

    uso = models.MaterialeUsatoLavoro(
        utente_id=utente_test.id,
        lavoro_id=lavoro.id,
        materiale_id=mat.id,
        quantita=2.0,
        costo_unitario=10.0,
        prezzo_unitario_cliente=20.0,
        data_creazione=str(date.today()),
    )
    db.add(uso)
    db.commit()

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.importo_consuntivo == 40.0
    assert risultato.totale_materiali == 20.0
    assert risultato.margine == 20.0


def test_sconto_assoluto_riduce_totale_documento(db, utente_test, cliente_test):
    """
    Lo sconto è un importo assoluto in € sottratto dal totale_documento.
    Imponibile 100, IVA 22% = 22, sconto 10 € → totale_documento = 112.
    Nota: importo_consuntivo e totale_iva restano calcolati sull'imponibile lordo.
    """
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=2.0, costo_orario=50.0,
                          aliquota_iva=22.0, sconto=10.0)

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.importo_consuntivo == 100.0
    assert abs(risultato.totale_iva - 22.0) < 0.01
    assert abs(risultato.totale_documento - 112.0) < 0.01


def test_stato_pagamento_da_pagare(db, utente_test, cliente_test):
    """importo_pagato=0 → stato_pagamento='da_pagare'."""
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=1.0, costo_orario=100.0,
                          aliquota_iva=0.0, importo_pagato=0.0)

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.stato_pagamento == "da_pagare"
    assert risultato.residuo_pagamento == 100.0


def test_iva_zero_regime_forfettario(db, utente_test, cliente_test):
    """Aliquota IVA 0% (regime forfettario) → totale_documento = imponibile."""
    lavoro = _crea_lavoro(db, utente_test.id, cliente_test.id,
                          ore_lavoro=3.0, costo_orario=100.0, aliquota_iva=0.0)

    risultato = calcola_totali_lavoro(db, lavoro.id)

    assert risultato.totale_iva == 0.0
    assert risultato.totale_documento == 300.0


def test_lavoro_inesistente_restituisce_none(db):
    """ID non esistente → None senza eccezioni."""
    assert calcola_totali_lavoro(db, 999999) is None
