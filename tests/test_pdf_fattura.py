"""Test per app/services/pdf_fattura.py — generazione PDF fatture/preventivi
(ReportLab). Non c'era nessuna copertura: un None non gestito o un errore di
formattazione si scoprirebbe solo al primo utente che scarica una fattura.

Non verifichiamo il testo renderizzato (richiederebbe un parser PDF non tra
le dipendenze): verifichiamo che la generazione non sollevi eccezioni nelle
combinazioni realistiche di dati mancanti/presenti, e che il risultato sia
un PDF valido e non vuoto.
"""
from datetime import date

import pytest

from app import models
from app.services.pdf_fattura import genera_pdf_fattura, genera_pdf_preventivo, _totali_fattura

oggi = date.today()
oggi_str = str(oggi)


def _assert_pdf_valido(contenuto: bytes):
    assert isinstance(contenuto, bytes)
    assert contenuto.startswith(b"%PDF")
    assert b"%%EOF" in contenuto[-1024:]
    assert len(contenuto) > 500  # un documento vuoto/troncato sarebbe minuscolo


def _azienda(**override):
    base = dict(
        nome_azienda="Idraulica Rossi Srl", partita_iva="12345678901",
        codice_fiscale="RSSXXX80A01H501Z", regime_fiscale="RF01",
        indirizzo="Via Roma 10", cap="00100", citta="Roma", provincia="RM",
        telefono="0612345678", email="info@idraulica.it",
    )
    base.update(override)
    return models.ImpostazioniAzienda(**base)


def _voce(ordine, descrizione="Manodopera", quantita=2, prezzo=50.0):
    return models.VocePreventivo(
        ordine=ordine, descrizione=descrizione, quantita=quantita,
        prezzo_unitario=prezzo, unita_misura="h",
    )


# ── genera_pdf_fattura ───────────────────────────────────────────────────────

def test_fattura_senza_voci_usa_importo_consuntivo(db, utente_test, cliente_test, lavoro_test):
    lavoro_test.numero_fattura = 12
    lavoro_test.data_fattura = oggi
    lavoro_test.importo_consuntivo = 1200.0
    lavoro_test.aliquota_iva = 22
    lavoro_test.totale_iva = 264.0
    lavoro_test.totale_documento = 1464.0
    db.commit()

    pdf = genera_pdf_fattura(lavoro_test, cliente_test, _azienda())
    _assert_pdf_valido(pdf)


def test_fattura_con_voci(db, utente_test, cliente_test, lavoro_test):
    lavoro_test.numero_fattura = 1
    lavoro_test.data_fattura = oggi
    lavoro_test.importo_consuntivo = 200.0
    db.commit()

    voci = [_voce(1, "Manodopera", 2, 50.0), _voce(2, "Materiali", 1, 100.0)]
    pdf = genera_pdf_fattura(lavoro_test, cliente_test, _azienda(), voci=voci)
    _assert_pdf_valido(pdf)


# ── _totali_fattura: il totale deve riflettere le voci, non il dato salvato ──

def test_totali_fattura_con_voci_ignora_importo_consuntivo_scollegato(db, utente_test, cliente_test, lavoro_test):
    """Regressione: importo_consuntivo era rimasto a 200€ (es. non
    ricalcolato dopo l'ultima modifica delle voci), ma le voci attuali
    valgono 300€. Il totale della fattura deve riflettere le voci elencate
    nel documento, non il valore salvato e potenzialmente disallineato."""
    lavoro_test.importo_consuntivo = 200.0
    lavoro_test.totale_iva = 44.0
    lavoro_test.totale_documento = 244.0
    lavoro_test.aliquota_iva = 22
    db.commit()

    voci = [_voce(1, "Manodopera", 2, 50.0), _voce(2, "Materiali", 1, 200.0)]  # 100 + 200 = 300

    imponibile, totale_iva, totale_doc = _totali_fattura(lavoro_test, voci, forfettario=False, aliquota=22.0)

    assert imponibile == 300.0
    assert abs(totale_iva - 66.0) < 0.01
    assert abs(totale_doc - 366.0) < 0.01


def test_totali_fattura_senza_voci_usa_importo_consuntivo(db, utente_test, cliente_test, lavoro_test):
    """Senza voci, nessuna fonte alternativa: resta il dato salvato sul
    lavoro (comportamento di sempre)."""
    lavoro_test.importo_consuntivo = 200.0
    lavoro_test.totale_iva = 44.0
    lavoro_test.totale_documento = 244.0
    db.commit()

    imponibile, totale_iva, totale_doc = _totali_fattura(lavoro_test, None, forfettario=False, aliquota=22.0)

    assert imponibile == 200.0
    assert totale_iva == 44.0
    assert totale_doc == 244.0


def test_totali_fattura_regime_forfettario_niente_iva(db, utente_test, cliente_test, lavoro_test):
    """Regime forfettario: IVA sempre zero anche con voci."""
    voci = [_voce(1, "Manodopera", 2, 50.0)]
    imponibile, totale_iva, totale_doc = _totali_fattura(lavoro_test, voci, forfettario=True, aliquota=22.0)

    assert imponibile == 100.0
    assert totale_iva == 0.0
    assert totale_doc == 100.0


def test_fattura_regime_forfettario_senza_iva_e_con_bollo(db, utente_test, cliente_test, lavoro_test):
    """Regime forfettario (RF19): niente IVA, marca da bollo se imponibile > 77,47."""
    lavoro_test.numero_fattura = 5
    lavoro_test.data_fattura = oggi
    lavoro_test.importo_consuntivo = 500.0
    lavoro_test.totale_documento = 500.0
    db.commit()

    pdf = genera_pdf_fattura(lavoro_test, cliente_test, _azienda(regime_fiscale="RF19"))
    _assert_pdf_valido(pdf)


def test_fattura_con_ritenuta_acconto(db, utente_test, cliente_test, lavoro_test):
    lavoro_test.numero_fattura = 7
    lavoro_test.data_fattura = oggi
    lavoro_test.importo_consuntivo = 1000.0
    lavoro_test.ritenuta_acconto = True
    lavoro_test.aliquota_ritenuta = 20
    db.commit()

    pdf = genera_pdf_fattura(lavoro_test, cliente_test, _azienda())
    _assert_pdf_valido(pdf)


def test_fattura_senza_azienda_e_senza_cliente(lavoro_test):
    """azienda/cliente possono essere None (account senza dati azienda compilati)."""
    lavoro_test.numero_fattura = 1
    lavoro_test.data_fattura = oggi
    lavoro_test.importo_consuntivo = 100.0
    pdf = genera_pdf_fattura(lavoro_test, None, None)
    _assert_pdf_valido(pdf)


def test_fattura_cliente_azienda_con_ragione_sociale(db, lavoro_test):
    cliente_azienda = models.Cliente(
        utente_id=1, tipo_cliente="azienda", ragione_sociale="Acme Srl",
        partita_iva="98765432109", data_creazione=oggi_str,
    )
    lavoro_test.numero_fattura = 2
    lavoro_test.data_fattura = oggi
    lavoro_test.importo_consuntivo = 300.0
    pdf = genera_pdf_fattura(lavoro_test, cliente_azienda, _azienda())
    _assert_pdf_valido(pdf)


def test_fattura_con_note_consuntivo(lavoro_test, cliente_test):
    lavoro_test.numero_fattura = 3
    lavoro_test.data_fattura = oggi
    lavoro_test.importo_consuntivo = 100.0
    lavoro_test.note_consuntivo = "Pagamento a 30gg, grazie."
    pdf = genera_pdf_fattura(lavoro_test, cliente_test, _azienda())
    _assert_pdf_valido(pdf)


# ── genera_pdf_preventivo ────────────────────────────────────────────────────

def test_preventivo_senza_voci(db, utente_test, cliente_test, lavoro_test):
    lavoro_test.numero_preventivo = "P-001"
    lavoro_test.importo_preventivato = 800.0
    db.commit()

    pdf = genera_pdf_preventivo(lavoro_test, cliente_test, _azienda())
    _assert_pdf_valido(pdf)


def test_preventivo_con_voci_e_sconto(db, utente_test, cliente_test, lavoro_test):
    lavoro_test.numero_preventivo = "P-002"
    lavoro_test.sconto = 10.0
    db.commit()

    voci = [_voce(1, "Sopralluogo", 1, 80.0), _voce(2, "Materiali", 3, 40.0)]
    pdf = genera_pdf_preventivo(lavoro_test, cliente_test, _azienda(), voci=voci)
    _assert_pdf_valido(pdf)


def test_preventivo_regime_forfettario(db, utente_test, cliente_test, lavoro_test):
    lavoro_test.numero_preventivo = "P-003"
    lavoro_test.importo_preventivato = 200.0
    db.commit()

    pdf = genera_pdf_preventivo(lavoro_test, cliente_test, _azienda(regime_fiscale="RF02"))
    _assert_pdf_valido(pdf)


def test_preventivo_titolo_lungo_viene_troncato_senza_crash(db, utente_test, cliente_test, lavoro_test):
    lavoro_test.titolo = "T" * 100
    lavoro_test.importo_preventivato = 50.0
    db.commit()

    pdf = genera_pdf_preventivo(lavoro_test, cliente_test, _azienda())
    _assert_pdf_valido(pdf)


def test_preventivo_senza_azienda_e_senza_cliente(lavoro_test):
    lavoro_test.importo_preventivato = 50.0
    pdf = genera_pdf_preventivo(lavoro_test, None, None)
    _assert_pdf_valido(pdf)
