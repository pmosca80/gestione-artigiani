from app import models


def calcola_totali_lavoro(db, lavoro_id: int):
    lavoro = db.query(models.Lavoro).filter(
        models.Lavoro.id == lavoro_id
    ).first()

    if not lavoro:
        return None

    materiali_usati = db.query(models.MaterialeUsatoLavoro).filter(
        models.MaterialeUsatoLavoro.lavoro_id == lavoro_id
    ).all()

    totale_costo_materiali = 0
    totale_cliente_materiali = 0

    for materiale in materiali_usati:
        quantita = materiale.quantita or 0
        costo_unitario = materiale.costo_unitario or 0
        prezzo_cliente = materiale.prezzo_unitario_cliente or 0

        totale_costo_materiali += quantita * costo_unitario
        totale_cliente_materiali += quantita * prezzo_cliente

    ore_lavoro = lavoro.ore_lavoro or 0
    costo_orario = lavoro.costo_orario or 0

    totale_manodopera = ore_lavoro * costo_orario

    lavoro.totale_materiali = totale_costo_materiali
    lavoro.totale_manodopera = totale_manodopera

    voci = db.query(models.VocePreventivo).filter(
        models.VocePreventivo.lavoro_id == lavoro_id
    ).all()

    if voci:
        # Le voci preventivo sono la fonte di verità una volta compilate:
        # preventivo e consuntivo coincidono con quanto effettivamente
        # scritto in preventivo (niente più numeri manuali scollegati
        # dalle voci, vedi ore_lavoro/costo_orario sotto usati solo come
        # fallback per i lavori che non passano dal sistema a voci).
        imponibile = sum((v.quantita or 0) * (v.prezzo_unitario or 0) for v in voci)
        lavoro.importo_preventivato = imponibile
    else:
        imponibile = totale_cliente_materiali + totale_manodopera

    aliquota_iva = lavoro.aliquota_iva or 0
    sconto = lavoro.sconto or 0

    totale_iva = imponibile * (aliquota_iva / 100)
    totale_documento = imponibile + totale_iva - sconto

    lavoro.importo_consuntivo = imponibile
    lavoro.totale_iva = totale_iva
    lavoro.totale_documento = totale_documento

    costo_reale = totale_costo_materiali + totale_manodopera
    lavoro.margine = totale_documento - costo_reale

    importo_pagato = lavoro.importo_pagato or 0

    lavoro.residuo_pagamento = max(0.0, totale_documento - importo_pagato)

    if importo_pagato <= 0:
        lavoro.stato_pagamento = "da_pagare"
    elif importo_pagato < totale_documento:
        lavoro.stato_pagamento = "acconto"
    else:
        lavoro.stato_pagamento = "pagato"

    db.commit()
    db.refresh(lavoro)

    return lavoro