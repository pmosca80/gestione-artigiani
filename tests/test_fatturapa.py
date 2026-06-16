"""
Test unitari per app/services/fatturapa.py.

Le funzioni sono pure (nessun accesso al DB): si usano SimpleNamespace come
sostituti leggeri degli oggetti ORM, testando solo la logica fiscale.
"""
from types import SimpleNamespace
from datetime import date
import xml.etree.ElementTree as ET

import pytest

from app.services.fatturapa import (
    bollo_dovuto,
    errori_fatturapa,
    genera_xml_fatturapa,
    nome_file_fatturapa,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _azienda(**kw):
    defaults = dict(
        partita_iva="12345678901",
        codice_fiscale=None,
        nome_azienda="Test Srl",
        indirizzo="Via Roma 1",
        cap="00100",
        citta="Roma",
        provincia="RM",
        regime_fiscale="RF01",
        email="owner@test.it",
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _cliente(**kw):
    defaults = dict(
        tipo_cliente="privato",
        nome="Mario",
        cognome="Rossi",
        ragione_sociale=None,
        partita_iva=None,
        codice_fiscale="RSSMRA80A01H501U",
        indirizzo="Via Verdi 5",
        cap="00200",
        citta="Milano",
        provincia="MI",
        codice_destinatario="0000000",
        pec_destinatario=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _lavoro(**kw):
    defaults = dict(
        id=1,
        titolo="Lavoro di test",
        descrizione=None,
        importo_consuntivo=500.0,
        totale_iva=110.0,
        totale_documento=610.0,
        aliquota_iva=22.0,
        data_lavoro=date(2025, 3, 15),
        data_fattura=None,
        data_scadenza_pagamento=date(2025, 4, 15),
        numero_fattura=1,
        stato_pagamento="da_pagare",
        sconto=0.0,
        ritenuta_acconto=False,
        aliquota_ritenuta=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _voce(n, desc, qtq=1.0, pu=100.0, um=None, ordine=None):
    return SimpleNamespace(
        descrizione=desc,
        quantita=qtq,
        prezzo_unitario=pu,
        unita_misura=um,
        ordine=ordine or n,
    )


def _parse(xml_bytes: bytes) -> ET.Element:
    """Verifica che l'XML sia ben formato (parser namespace-aware nativo)."""
    return ET.fromstring(xml_bytes.decode("utf-8"))


# ── bollo_dovuto ──────────────────────────────────────────────────────────────

def test_bollo_dovuto_sopra_soglia():
    """Regime esente + imponibile > €77,47 → bollo €2,00."""
    assert bollo_dovuto(True, 100.0) == 2.0


def test_bollo_dovuto_sotto_soglia():
    """Regime esente ma imponibile ≤ €77,47 → nessun bollo."""
    assert bollo_dovuto(True, 50.0) == 0.0


def test_bollo_dovuto_regime_con_iva():
    """Regime con IVA → mai bollo, qualunque sia l'imponibile."""
    assert bollo_dovuto(False, 500.0) == 0.0


# ── errori_fatturapa ──────────────────────────────────────────────────────────

def test_errori_fatturapa_tutto_ok():
    """Dati completi e validi → zero errori."""
    errs = errori_fatturapa(_lavoro(), _cliente(), _azienda())
    assert errs == []


def test_errori_fatturapa_manca_piva_azienda():
    az = _azienda(partita_iva="")
    errs = errori_fatturapa(_lavoro(), _cliente(), az)
    assert any("Partita IVA" in e for e in errs)


def test_errori_fatturapa_manca_indirizzo_azienda():
    az = _azienda(indirizzo="", cap="", citta="")
    errs = errori_fatturapa(_lavoro(), _cliente(), az)
    assert any("Indirizzo" in e or "CAP" in e for e in errs)


def test_errori_fatturapa_imponibile_zero():
    lav = _lavoro(importo_consuntivo=0, totale_documento=0)
    errs = errori_fatturapa(lav, _cliente(), _azienda())
    assert any("mponibile" in e for e in errs)


def test_errori_fatturapa_cliente_senza_identificativo():
    """CF e PIVA cliente entrambi assenti → errore bloccante."""
    cl = _cliente(codice_fiscale="", partita_iva=None)
    errs = errori_fatturapa(_lavoro(), cl, _azienda())
    assert any("Codice Fiscale" in e for e in errs)


# ── genera_xml_fatturapa — struttura base ─────────────────────────────────────

def test_genera_xml_td01_struttura_base():
    """XML TD01: attributo versione FPR12, TipoDocumento, Numero formattato."""
    xml = genera_xml_fatturapa(_lavoro(), _cliente(), _azienda())
    assert b"FPR12" in xml
    assert b"TD01" in xml
    assert b"2025/001" in xml  # numero_fattura=1, data_lavoro 2025


def test_genera_xml_e_xml_valido():
    """L'output deve essere un XML ben formato (parse senza eccezioni)."""
    xml = genera_xml_fatturapa(_lavoro(), _cliente(), _azienda())
    root = _parse(xml)
    assert root is not None


def test_genera_xml_piva_cedente():
    """La P.IVA dell'azienda deve comparire nell'IdCodice del cedente."""
    xml = genera_xml_fatturapa(_lavoro(), _cliente(), _azienda())
    assert b"12345678901" in xml


def test_genera_xml_cliente_privato_nome_cognome():
    """Cliente privato → Nome + Cognome nel cessionario."""
    xml = genera_xml_fatturapa(_lavoro(), _cliente(), _azienda())
    assert b"Mario" in xml
    assert b"Rossi" in xml


def test_genera_xml_cliente_azienda_denominazione():
    """Cliente azienda → Denominazione (ragione sociale) nel cessionario."""
    cl = _cliente(tipo_cliente="azienda", ragione_sociale="Acme Srl",
                  nome=None, cognome=None, partita_iva="98765432101", codice_fiscale=None)
    xml = genera_xml_fatturapa(_lavoro(), cl, _azienda())
    assert b"Acme Srl" in xml
    assert b"<Denominazione>" in xml


# ── TD04 nota di credito ──────────────────────────────────────────────────────

def test_genera_xml_td04_no_dati_pagamento():
    """TD04 non deve contenere DatiPagamento (non si paga una nota di credito)."""
    xml = genera_xml_fatturapa(_lavoro(), _cliente(), _azienda(), tipo_documento="TD04")
    assert b"DatiPagamento" not in xml


def test_genera_xml_td04_con_riferimento_fattura():
    """TD04 con fattura_rif_numero → DatiFattureCollegate con IdDocumento."""
    xml = genera_xml_fatturapa(
        _lavoro(), _cliente(), _azienda(),
        tipo_documento="TD04",
        fattura_rif_numero=3,
        fattura_rif_anno=2025,
    )
    assert b"DatiFattureCollegate" in xml
    assert b"2025/003" in xml


# ── Regime fiscale forfettario / esente ──────────────────────────────────────

def test_genera_xml_regime_forfettario_aliquota_zero():
    """RF02 (minimi) → AliquotaIVA=0.00 e Natura=N2.2 in ogni blocco IVA."""
    az = _azienda(regime_fiscale="RF02")
    xml = genera_xml_fatturapa(_lavoro(), _cliente(), az)
    assert b"<AliquotaIVA>0.00</AliquotaIVA>" in xml
    assert b"<Natura>N2.2</Natura>" in xml
    assert b"<EsigibilitaIVA>" not in xml


def test_genera_xml_bollo_virtuale_esente():
    """RF02 + imponibile > €77,47 → blocco DatiBollo SI nell'XML."""
    az = _azienda(regime_fiscale="RF02")
    lav = _lavoro(importo_consuntivo=100.0, totale_documento=100.0, totale_iva=0.0)
    xml = genera_xml_fatturapa(lav, _cliente(), az)
    assert b"<BolloVirtuale>SI</BolloVirtuale>" in xml
    assert b"<ImportoBollo>2.00</ImportoBollo>" in xml


def test_genera_xml_no_bollo_regime_iva():
    """RF01 (regime ordinario) → nessun blocco DatiBollo."""
    xml = genera_xml_fatturapa(_lavoro(), _cliente(), _azienda())
    assert b"DatiBollo" not in xml


# ── Ritenuta d'acconto ────────────────────────────────────────────────────────

def test_genera_xml_ritenuta_acconto():
    """ritenuta_acconto=True → DatiRitenuta RT01 nell'XML."""
    lav = _lavoro(ritenuta_acconto=True, aliquota_ritenuta=20.0)
    xml = genera_xml_fatturapa(lav, _cliente(), _azienda())
    assert b"<TipoRitenuta>RT01</TipoRitenuta>" in xml
    assert b"<AliquotaRitenuta>20.00</AliquotaRitenuta>" in xml
    assert b"<CausalePagamento>A</CausalePagamento>" in xml


def test_genera_xml_ritenuta_sottrae_da_totale():
    """ImportoPagamento deve essere imponibile×1.22 meno la ritenuta."""
    lav = _lavoro(
        importo_consuntivo=1000.0,
        totale_iva=220.0,
        totale_documento=1220.0,
        ritenuta_acconto=True,
        aliquota_ritenuta=20.0,
    )
    xml = genera_xml_fatturapa(lav, _cliente(), _azienda())
    # Totale netto = 1220.00 - 200.00 (ritenuta 20%) = 1020.00
    assert b"<ImportoPagamento>1020.00</ImportoPagamento>" in xml


# ── Voci preventivo ───────────────────────────────────────────────────────────

def test_genera_xml_con_voci_multiple():
    """Con voci → un DettaglioLinee per ogni voce."""
    voci = [_voce(1, "Manodopera", qtq=2.0, pu=50.0), _voce(2, "Materiali", qtq=1.0, pu=400.0)]
    lav = _lavoro(importo_consuntivo=500.0)
    xml = genera_xml_fatturapa(lav, _cliente(), _azienda(), voci=voci)
    assert xml.count(b"<DettaglioLinee>") == 2
    assert b"Manodopera" in xml
    assert b"Materiali" in xml


def test_genera_xml_voci_sconto_aggiunto_come_riga():
    """Se la somma delle voci ≠ imponibile, aggiunge una riga sconto/arrotondamento."""
    # Voci totale = 600, imponibile = 500 → riga sconto −100
    voci = [_voce(1, "Lavoro", qtq=1.0, pu=600.0)]
    lav = _lavoro(importo_consuntivo=500.0, sconto=16.67)
    xml = genera_xml_fatturapa(lav, _cliente(), _azienda(), voci=voci)
    # Deve esserci almeno una riga aggiuntiva (Sconto ... %)
    assert xml.count(b"<DettaglioLinee>") >= 2


# ── Escape caratteri speciali ─────────────────────────────────────────────────

def test_genera_xml_escape_caratteri_speciali():
    """Descrizione con & e < deve essere escaped correttamente nell'XML."""
    lav = _lavoro(descrizione="Lavoro & Ristrutturazione <extra>")
    xml = genera_xml_fatturapa(lav, _cliente(), _azienda())
    assert b"&amp;" in xml
    assert b"&lt;" in xml
    assert b"<extra>" not in xml  # non deve comparire raw


# ── nome_file_fatturapa ───────────────────────────────────────────────────────

def test_nome_file_fatturapa_formato():
    """Nome file: IT{PIVA}_{numero 5 cifre}.xml"""
    az = _azienda(partita_iva="12345678901")
    lav = _lavoro(numero_fattura=7)
    assert nome_file_fatturapa(az, lav) == "IT12345678901_00007.xml"


def test_nome_file_fatturapa_senza_piva():
    """Senza P.IVA usa placeholder XXXXXXXX."""
    az = _azienda(partita_iva=None)
    lav = _lavoro(numero_fattura=1)
    nome = nome_file_fatturapa(az, lav)
    assert nome.startswith("ITXXXXXXXX")
    assert nome.endswith(".xml")
