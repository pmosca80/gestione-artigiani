from xml.sax.saxutils import escape as _esc

# Regimi fiscali dove l'IVA non si applica → AliquotaIVA=0, Natura=N2.2
_REGIMI_SENZA_IVA = {"RF02", "RF04", "RF05", "RF06", "RF07", "RF08", "RF09",
                     "RF10", "RF11", "RF12", "RF13", "RF14", "RF15", "RF16",
                     "RF17", "RF18", "RF19"}


def errori_fatturapa(lavoro, cliente, azienda) -> list:
    """Ritorna lista di errori bloccanti prima di generare l'XML."""
    errori = []

    if not (azienda.partita_iva or "").strip():
        errori.append("Partita IVA azienda mancante → Impostazioni › Azienda")

    if not (azienda.indirizzo or "").strip():
        errori.append("Indirizzo sede azienda mancante → Impostazioni › Azienda")

    if not (azienda.cap or "").strip() or not (azienda.citta or "").strip():
        errori.append("CAP / Città sede azienda mancanti → Impostazioni › Azienda")

    imponibile = float(lavoro.importo_consuntivo or 0)
    totale     = float(lavoro.totale_documento or 0)

    if imponibile <= 0:
        errori.append("Imponibile (importo consuntivo) è zero — modifica il lavoro e inserisci i valori economici")

    if totale <= 0:
        errori.append("Totale documento è zero o negativo — calcola i totali salvando il lavoro")

    if not (cliente.codice_fiscale or "").strip() and not (cliente.partita_iva or "").strip():
        errori.append("Cliente senza Codice Fiscale né Partita IVA — modifica la scheda cliente")

    if not (cliente.indirizzo or "").strip():
        errori.append("Indirizzo cliente mancante — modifica la scheda cliente")

    return errori


def genera_xml_fatturapa(lavoro, cliente, azienda) -> bytes:
    """Genera XML FatturaPA formato FPR12 (Livello 1 — solo download, senza invio SDI)."""

    def e(v):
        return _esc(str(v).strip()) if v else ""

    # ── Cedente (emittente) ──────────────────────────────────────────────────
    piva_az   = e(azienda.partita_iva)
    cf_az     = e(azienda.codice_fiscale)
    regime    = e(azienda.regime_fiscale or "RF01")
    nome_az   = e(azienda.nome_azienda)
    ind_az    = e(azienda.indirizzo)
    cap_az    = e(azienda.cap or "00000")
    citta_az  = e(azienda.citta)
    prov_az   = e((azienda.provincia or "")[:2])

    cf_cedente_block = f"\n        <CodiceFiscale>{cf_az}</CodiceFiscale>" if cf_az else ""

    # ── Cessionario (destinatario) ───────────────────────────────────────────
    codice_dest = (getattr(cliente, "codice_destinatario", None) or "0000000").strip()
    codice_dest = (codice_dest + "0000000")[:7]
    pec_dest    = e(getattr(cliente, "pec_destinatario", None))
    piva_cl     = e(getattr(cliente, "partita_iva", None))
    cf_cl       = e(getattr(cliente, "codice_fiscale", None))
    ind_cl      = e(cliente.indirizzo or "ND")
    cap_cl      = e(cliente.cap or "00000")
    citta_cl    = e(cliente.citta)
    prov_cl     = e((cliente.provincia or "")[:2])

    pec_block = (
        f"\n    <PECDestinatario>{pec_dest}</PECDestinatario>"
        if (codice_dest == "0000000" and pec_dest)
        else ""
    )

    # Per i privati senza P.IVA non includiamo IdFiscaleIVA
    id_fiscale_cl_block = (
        f"<IdFiscaleIVA>\n          <IdPaese>IT</IdPaese>\n"
        f"          <IdCodice>{piva_cl}</IdCodice>\n        </IdFiscaleIVA>\n        "
        if piva_cl else ""
    )
    cf_cl_block = f"<CodiceFiscale>{cf_cl}</CodiceFiscale>\n        " if cf_cl else ""

    if cliente.tipo_cliente == "azienda":
        anagrafica_cl = f"<Denominazione>{e(cliente.ragione_sociale)}</Denominazione>"
    else:
        anagrafica_cl = (
            f"<Nome>{e(cliente.nome)}</Nome>\n"
            f"          <Cognome>{e(cliente.cognome)}</Cognome>"
        )

    # ── Importi ──────────────────────────────────────────────────────────────
    imponibile = float(lavoro.importo_consuntivo or 0)
    totale     = float(lavoro.totale_documento or 0)

    # Regime senza IVA (forfettario RF19, minimi RF02, ecc.) → forza 0%
    regime_senza_iva = (azienda.regime_fiscale or "RF01").strip().upper() in _REGIMI_SENZA_IVA
    aliquota = 0.0 if regime_senza_iva else float(lavoro.aliquota_iva or 22)
    iva_amt  = 0.0 if (regime_senza_iva or aliquota == 0) else float(
        lavoro.totale_iva or round(imponibile * aliquota / 100, 2)
    )

    # Ricalcola totale per regime senza IVA (non applicare IVA al totale)
    if regime_senza_iva:
        totale = imponibile

    # ── Elemento Natura (obbligatorio quando AliquotaIVA = 0) ────────────────
    usa_natura = (aliquota == 0.0)
    natura_block  = "\n        <Natura>N2.2</Natura>" if usa_natura else ""
    esigibilita_block = "\n        <EsigibilitaIVA>I</EsigibilitaIVA>" if not usa_natura else ""

    # ── Documento ────────────────────────────────────────────────────────────
    num_fattura  = getattr(lavoro, "numero_fattura", None) or lavoro.id
    data_fattura = getattr(lavoro, "data_fattura", None) or lavoro.data_lavoro
    progressivo  = str(num_fattura).zfill(5)

    desc = e(lavoro.descrizione or lavoro.titolo or "Prestazione di servizi")[:1000]

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<p:FatturaElettronica versione="FPR12"\n'
        '  xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"\n'
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '  xsi:schemaLocation="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2'
        ' http://www.fatturapa.gov.it/export/fatturazione/sdi/fatturapa/v1.2/'
        'Schema_del_file_xml_FatturaPA_versione_1.2.xsd">\n'
        "  <FatturaElettronicaHeader>\n"
        "    <DatiTrasmissione>\n"
        "      <IdTrasmittente>\n"
        f"        <IdPaese>IT</IdPaese>\n"
        f"        <IdCodice>{piva_az}</IdCodice>\n"
        "      </IdTrasmittente>\n"
        f"      <ProgressivoInvio>{progressivo}</ProgressivoInvio>\n"
        "      <FormatoTrasmissione>FPR12</FormatoTrasmissione>\n"
        f"      <CodiceDestinatario>{codice_dest}</CodiceDestinatario>{pec_block}\n"
        "    </DatiTrasmissione>\n"
        "    <CedentePrestatore>\n"
        "      <DatiAnagrafici>\n"
        "        <IdFiscaleIVA>\n"
        "          <IdPaese>IT</IdPaese>\n"
        f"          <IdCodice>{piva_az}</IdCodice>\n"
        "        </IdFiscaleIVA>"
        f"{cf_cedente_block}\n"
        "        <Anagrafica>\n"
        f"          <Denominazione>{nome_az}</Denominazione>\n"
        "        </Anagrafica>\n"
        f"        <RegimeFiscale>{regime}</RegimeFiscale>\n"
        "      </DatiAnagrafici>\n"
        "      <Sede>\n"
        f"        <Indirizzo>{ind_az}</Indirizzo>\n"
        f"        <CAP>{cap_az}</CAP>\n"
        f"        <Comune>{citta_az}</Comune>\n"
        f"        <Provincia>{prov_az}</Provincia>\n"
        "        <Nazione>IT</Nazione>\n"
        "      </Sede>\n"
        "    </CedentePrestatore>\n"
        "    <CessionarioCommittente>\n"
        "      <DatiAnagrafici>\n"
        f"        {id_fiscale_cl_block}{cf_cl_block}<Anagrafica>\n"
        f"          {anagrafica_cl}\n"
        "        </Anagrafica>\n"
        "      </DatiAnagrafici>\n"
        "      <Sede>\n"
        f"        <Indirizzo>{ind_cl}</Indirizzo>\n"
        f"        <CAP>{cap_cl}</CAP>\n"
        f"        <Comune>{citta_cl}</Comune>\n"
        f"        <Provincia>{prov_cl}</Provincia>\n"
        "        <Nazione>IT</Nazione>\n"
        "      </Sede>\n"
        "    </CessionarioCommittente>\n"
        "  </FatturaElettronicaHeader>\n"
        "  <FatturaElettronicaBody>\n"
        "    <DatiGenerali>\n"
        "      <DatiGeneraliDocumento>\n"
        "        <TipoDocumento>TD01</TipoDocumento>\n"
        "        <Divisa>EUR</Divisa>\n"
        f"        <Data>{data_fattura}</Data>\n"
        f"        <Numero>{num_fattura}</Numero>\n"
        f"        <ImportoTotaleDocumento>{totale:.2f}</ImportoTotaleDocumento>\n"
        "      </DatiGeneraliDocumento>\n"
        "    </DatiGenerali>\n"
        "    <DatiBeniServizi>\n"
        "      <DettaglioLinee>\n"
        "        <NumeroLinea>1</NumeroLinea>\n"
        f"        <Descrizione>{desc}</Descrizione>\n"
        "        <Quantita>1.00</Quantita>\n"
        f"        <PrezzoUnitario>{imponibile:.2f}</PrezzoUnitario>\n"
        f"        <PrezzoTotale>{imponibile:.2f}</PrezzoTotale>\n"
        f"        <AliquotaIVA>{aliquota:.2f}</AliquotaIVA>{natura_block}\n"
        "      </DettaglioLinee>\n"
        "      <DatiRiepilogo>\n"
        f"        <AliquotaIVA>{aliquota:.2f}</AliquotaIVA>{natura_block}\n"
        f"        <ImponibileImporto>{imponibile:.2f}</ImponibileImporto>\n"
        f"        <Imposta>{iva_amt:.2f}</Imposta>{esigibilita_block}\n"
        "      </DatiRiepilogo>\n"
        "    </DatiBeniServizi>\n"
        "  </FatturaElettronicaBody>\n"
        "</p:FatturaElettronica>"
    )

    return xml.encode("utf-8")


def nome_file_fatturapa(azienda, lavoro) -> str:
    """Nome file standard FatturaPA: IT{PIVA}_{NUMERO}.xml"""
    piva = (azienda.partita_iva or "XXXXXXXX").strip().replace(" ", "")
    num  = getattr(lavoro, "numero_fattura", None) or lavoro.id
    return f"IT{piva}_{str(num).zfill(5)}.xml"
