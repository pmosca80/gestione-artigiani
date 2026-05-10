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

    totale_materiali = 0

    for materiale in materiali_usati:
        quantita = materiale.quantita or 0
        costo_unitario = materiale.costo_unitario or 0
        totale_materiali += quantita * costo_unitario

    ore_lavoro = lavoro.ore_lavoro or 0
    costo_orario = lavoro.costo_orario or 0

    totale_manodopera = ore_lavoro * costo_orario
    importo_consuntivo = totale_materiali + totale_manodopera

    lavoro.totale_materiali = totale_materiali
    lavoro.totale_manodopera = totale_manodopera
    lavoro.importo_consuntivo = importo_consuntivo

    preventivo = lavoro.importo_preventivato or 0
    lavoro.margine = preventivo - importo_consuntivo

    db.commit()
    db.refresh(lavoro)

    return lavoro