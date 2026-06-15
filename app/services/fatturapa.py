from xml.sax.saxutils import escape as _esc

# Regimi fiscali dove l'IVA non si applica → AliquotaIVA=0, Natura=N2.2
_REGIMI_SENZA_IVA = {"RF02", "RF04", "RF05", "RF06", "RF07", "RF08", "RF09",
                     "RF10", "RF11", "RF12", "RF13", "RF14", "RF15", "RF16",
                     "RF17", "RF18", "RF19"}

_SOGLIA_BOLLO  = 77.47
_IMPORTO_BOLLO = 2.00


def bollo_dovuto(regime_senza_iva: bool, imponibile: float) -> float:
    """€2 di bollo virtuale su fatture esenti IVA con imponibile > €77,47."""
    return _IMPORTO_BOLLO if (regime_senza_iva and imponibile > _SOGLIA_BOLLO) else 0.0


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


def genera_xml_fatturapa(
    lavoro, cliente, azienda, voci=None,
    tipo_documento="TD01",
    fattura_rif_numero=None, fattura_rif_anno=None,
) -> bytes:
    """
    Genera XML FatturaPA formato FPR12.
    tipo_documento: TD01 = fattura, TD04 = nota di credito.
    Se voci viene passata, genera una riga per voce.
    """

    def e(v):
        return _esc(str(v).strip()) if v else ""

    # ── Cedente (emittente) ──────────────────────────────────────────────────
    piva_az  = e(azienda.partita_iva)
    cf_az    = e(azienda.codice_fiscale)
    regime   = e(azienda.regime_fiscale or "RF01")
    nome_az  = e(azienda.nome_azienda)
    ind_az   = e(azienda.indirizzo)
    cap_az   = e(azienda.cap or "00000")
    citta_az = e(azienda.citta)
    prov_az  = e((azienda.provincia or "")[:2])

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

    regime_senza_iva = (azienda.regime_fiscale or "RF01").strip().upper() in _REGIMI_SENZA_IVA
    aliquota = 0.0 if regime_senza_iva else float(lavoro.aliquota_iva or 22)
    iva_amt  = 0.0 if (regime_senza_iva or aliquota == 0) else float(
        lavoro.totale_iva or round(imponibile * aliquota / 100, 2)
    )

    if regime_senza_iva:
        totale = imponibile

    usa_natura        = (aliquota == 0.0)
    natura_block      = "\n        <Natura>N2.2</Natura>" if usa_natura else ""
    esigibilita_block = "\n        <EsigibilitaIVA>I</EsigibilitaIVA>" if not usa_natura else ""

    # Bollo virtuale €2 su fatture esenti IVA > €77,47 (art. 6 Tariffa DPR 642/1972)
    bollo = bollo_dovuto(regime_senza_iva, imponibile)
    totale_con_bollo = round(totale + bollo, 2)
    dati_bollo_block = (
        f"        <DatiBollo>\n"
        f"          <BolloVirtuale>SI</BolloVirtuale>\n"
        f"          <ImportoBollo>{bollo:.2f}</ImportoBollo>\n"
        f"        </DatiBollo>\n"
    ) if bollo > 0 else ""

    # Ritenuta d'acconto (art. 25 DPR 600/73) — sottratta da ImportoTotaleDocumento e ImportoPagamento
    applica_ritenuta = bool(getattr(lavoro, "ritenuta_acconto", False))
    aliquota_rit = float(getattr(lavoro, "aliquota_ritenuta", None) or 20.0)
    importo_ritenuta = round(imponibile * aliquota_rit / 100, 2) if applica_ritenuta else 0.0
    totale_netto = round(totale_con_bollo - importo_ritenuta, 2)
    dati_ritenuta_block = (
        f"        <DatiRitenuta>\n"
        f"          <TipoRitenuta>RT01</TipoRitenuta>\n"
        f"          <ImportoRitenuta>{importo_ritenuta:.2f}</ImportoRitenuta>\n"
        f"          <AliquotaRitenuta>{aliquota_rit:.2f}</AliquotaRitenuta>\n"
        f"          <CausalePagamento>A</CausalePagamento>\n"
        f"        </DatiRitenuta>\n"
    ) if applica_ritenuta else ""

    # ── Documento ────────────────────────────────────────────────────────────
    num_fattura  = getattr(lavoro, "numero_fattura", None) or lavoro.id
    data_fattura = getattr(lavoro, "data_fattura", None) or lavoro.data_lavoro
    try:
        anno_fattura = int(str(data_fattura)[:4])
    except (ValueError, TypeError):
        from datetime import date
        anno_fattura = date.today().year
    numero_formattato = f"{anno_fattura}/{str(num_fattura).zfill(3)}"
    progressivo = str(num_fattura).zfill(5)

    # ── DettaglioLinee ───────────────────────────────────────────────────────
    if voci:
        voci_ordinate = sorted(voci, key=lambda v: (v.ordine or 0))
        linee = []
        for i, v in enumerate(voci_ordinate, start=1):
            qtq = round(float(v.quantita or 1), 2)
            pu  = round(float(v.prezzo_unitario or 0), 2)
            pt  = round(qtq * pu, 2)
            um  = e(v.unita_misura or "")
            um_tag = f"        <UnitaMisura>{um}</UnitaMisura>\n" if um else ""
            linee.append({
                "n": i, "desc": e(v.descrizione or "Prestazione")[:1000],
                "um_tag": um_tag, "qtq": qtq, "pu": pu, "pt": pt,
            })

        # Aggiusta eventuali differenze da sconto/arrotondamento
        lordo_voci = round(sum(l["pt"] for l in linee), 2)
        diff = round(lordo_voci - imponibile, 2)
        if abs(diff) > 0.001:
            sconto_pct = float(lavoro.sconto or 0)
            label = f"Sconto {sconto_pct:.0f}%" if sconto_pct > 0 else "Arrotondamento"
            linee.append({
                "n": len(linee) + 1, "desc": e(label),
                "um_tag": "", "qtq": 1.0, "pu": round(-diff, 2), "pt": round(-diff, 2),
            })

        dettaglio_xml = ""
        for l in linee:
            dettaglio_xml += (
                f"      <DettaglioLinee>\n"
                f"        <NumeroLinea>{l['n']}</NumeroLinea>\n"
                f"        <Descrizione>{l['desc']}</Descrizione>\n"
                + l["um_tag"]
                + f"        <Quantita>{l['qtq']:.2f}</Quantita>\n"
                f"        <PrezzoUnitario>{l['pu']:.2f}</PrezzoUnitario>\n"
                f"        <PrezzoTotale>{l['pt']:.2f}</PrezzoTotale>\n"
                f"        <AliquotaIVA>{aliquota:.2f}</AliquotaIVA>{natura_block}\n"
                f"      </DettaglioLinee>\n"
            )
    else:
        desc = e(lavoro.descrizione or lavoro.titolo or "Prestazione di servizi")[:1000]
        dettaglio_xml = (
            f"      <DettaglioLinee>\n"
            f"        <NumeroLinea>1</NumeroLinea>\n"
            f"        <Descrizione>{desc}</Descrizione>\n"
            f"        <Quantita>1.00</Quantita>\n"
            f"        <PrezzoUnitario>{imponibile:.2f}</PrezzoUnitario>\n"
            f"        <PrezzoTotale>{imponibile:.2f}</PrezzoTotale>\n"
            f"        <AliquotaIVA>{aliquota:.2f}</AliquotaIVA>{natura_block}\n"
            f"      </DettaglioLinee>\n"
        )

    # ── DatiPagamento (omesso per le note di credito TD04) ───────────────────
    if tipo_documento == "TD04":
        dati_pagamento = ""
    else:
        data_scad = (lavoro.data_scadenza_pagamento or "").strip()
        scad_tag  = f"        <DataScadenzaPagamento>{data_scad}</DataScadenzaPagamento>\n" if data_scad else ""
        dati_pagamento = (
            "    <DatiPagamento>\n"
            "      <CondizioniPagamento>TP02</CondizioniPagamento>\n"
            "      <DettaglioPagamento>\n"
            "        <ModalitaPagamento>MP05</ModalitaPagamento>\n"
            + scad_tag
            + f"        <ImportoPagamento>{totale_netto:.2f}</ImportoPagamento>\n"
            "      </DettaglioPagamento>\n"
            "    </DatiPagamento>\n"
        )

    # ── DatiFattureCollegate (solo per TD04 — nota di credito) ───────────────
    dati_rif_block = ""
    if tipo_documento == "TD04" and fattura_rif_numero:
        rif_anno = fattura_rif_anno or anno_fattura
        rif_id   = f"{rif_anno}/{str(fattura_rif_numero).zfill(3)}"
        dati_rif_block = (
            "    <DatiFattureCollegate>\n"
            f"      <IdDocumento>{_esc(rif_id)}</IdDocumento>\n"
            f"      <Anno>{rif_anno}</Anno>\n"
            "    </DatiFattureCollegate>\n"
        )

    # ── Assemblaggio XML ─────────────────────────────────────────────────────
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
        f"        <TipoDocumento>{tipo_documento}</TipoDocumento>\n"
        "        <Divisa>EUR</Divisa>\n"
        f"        <Data>{data_fattura}</Data>\n"
        f"        <Numero>{numero_formattato}</Numero>\n"
        f"        <ImportoTotaleDocumento>{totale_netto:.2f}</ImportoTotaleDocumento>\n"
        + dati_bollo_block
        + dati_ritenuta_block
        + "      </DatiGeneraliDocumento>\n"
        + dati_rif_block
        + "    </DatiGenerali>\n"
        "    <DatiBeniServizi>\n"
        + dettaglio_xml
        + "      <DatiRiepilogo>\n"
        f"        <AliquotaIVA>{aliquota:.2f}</AliquotaIVA>{natura_block}\n"
        f"        <ImponibileImporto>{imponibile:.2f}</ImponibileImporto>\n"
        f"        <Imposta>{iva_amt:.2f}</Imposta>{esigibilita_block}\n"
        "      </DatiRiepilogo>\n"
        "    </DatiBeniServizi>\n"
        + dati_pagamento
        + "  </FatturaElettronicaBody>\n"
        "</p:FatturaElettronica>"
    )

    return xml.encode("utf-8")


def nome_file_fatturapa(azienda, lavoro) -> str:
    """Nome file FatturaPA: IT{PIVA}_{NUMERO}.xml  (progressivo 5 cifre, spec SDI)"""
    piva = (azienda.partita_iva or "XXXXXXXX").strip().replace(" ", "")
    num  = getattr(lavoro, "numero_fattura", None) or lavoro.id
    return f"IT{piva}_{str(num).zfill(5)}.xml"
