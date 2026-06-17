"""Test per app/services/sdi.py — invio automatico a SDI."""
from datetime import date
from unittest.mock import patch

from app import models
from app.services.sdi import invia_automatico

oggi = date.today()


def _azienda(db, utente_id, *, pec=True, auto=True):
    az = models.ImpostazioniAzienda(
        utente_id=utente_id, nome_azienda="Test Srl", partita_iva="12345678901",
        indirizzo="Via Roma 1", cap="00100", citta="Roma", provincia="RM",
        regime_fiscale="RF01",
        pec_indirizzo="azienda@pec.it" if pec else None,
        pec_smtp_host="smtp.pec.it" if pec else None,
        pec_smtp_password="segreta" if pec else None,
        invio_automatico_sdi=auto,
    )
    db.add(az)
    db.commit()
    db.refresh(az)
    return az


def _fattura(db, utente_id, lavoro_id):
    f = models.FatturaEmessa(
        utente_id=utente_id, lavoro_id=lavoro_id, numero=1, anno=oggi.year,
        data_emissione=oggi, importo_imponibile=500, importo_iva=110,
        importo_totale=610, nome_file="IT12345678901_00001.xml", stato="emessa",
        data_creazione=str(oggi),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def test_invia_automatico_non_fa_nulla_se_disabilitato(db, utente_test, cliente_test, lavoro_test):
    azienda = _azienda(db, utente_test.id, pec=True, auto=False)
    fattura = _fattura(db, utente_test.id, lavoro_test.id)

    with patch("app.services.sdi.invia_xml_a_sdi") as mock_invia:
        invia_automatico(db, azienda, lavoro_test, fattura)

    mock_invia.assert_not_called()
    assert fattura.stato == "emessa"


def test_invia_automatico_non_fa_nulla_se_pec_non_configurata(db, utente_test, cliente_test, lavoro_test):
    azienda = _azienda(db, utente_test.id, pec=False, auto=True)
    fattura = _fattura(db, utente_test.id, lavoro_test.id)

    with patch("app.services.sdi.invia_xml_a_sdi") as mock_invia:
        invia_automatico(db, azienda, lavoro_test, fattura)

    mock_invia.assert_not_called()
    assert fattura.stato == "emessa"


def test_invia_automatico_invia_e_aggiorna_stato(db, utente_test, cliente_test, lavoro_test):
    azienda = _azienda(db, utente_test.id, pec=True, auto=True)
    fattura = _fattura(db, utente_test.id, lavoro_test.id)

    with patch("app.services.sdi.invia_xml_a_sdi") as mock_invia, \
         patch("app.services.fatturapa.genera_xml_fatturapa", return_value=b"<xml/>"):
        invia_automatico(db, azienda, lavoro_test, fattura)

    mock_invia.assert_called_once()
    assert fattura.stato == "inviata_sdi"


def test_invia_automatico_non_lancia_se_invio_fallisce(db, utente_test, cliente_test, lavoro_test):
    azienda = _azienda(db, utente_test.id, pec=True, auto=True)
    fattura = _fattura(db, utente_test.id, lavoro_test.id)

    with patch("app.services.sdi.invia_xml_a_sdi", side_effect=RuntimeError("PEC down")), \
         patch("app.services.fatturapa.genera_xml_fatturapa", return_value=b"<xml/>"):
        invia_automatico(db, azienda, lavoro_test, fattura)  # non deve sollevare

    assert fattura.stato == "emessa"  # stato non aggiornato in caso di fallimento


def test_invia_automatico_passa_tipo_documento_td04(db, utente_test, cliente_test, lavoro_test):
    azienda = _azienda(db, utente_test.id, pec=True, auto=True)
    fattura = _fattura(db, utente_test.id, lavoro_test.id)

    with patch("app.services.sdi.invia_xml_a_sdi") as mock_invia, \
         patch("app.services.fatturapa.genera_xml_fatturapa", return_value=b"<xml/>") as mock_genera:
        invia_automatico(
            db, azienda, lavoro_test, fattura,
            tipo_documento="TD04", fattura_rif_numero=1, fattura_rif_anno=oggi.year,
        )

    assert mock_genera.call_args.kwargs["tipo_documento"] == "TD04"
    mock_invia.assert_called_once()
