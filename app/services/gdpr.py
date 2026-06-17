"""
Servizi GDPR: export dati (art. 20 — portabilità) e cancellazione (art. 17 — oblio).

Cancellazione: i dati senza vincolo di conservazione fiscale vengono eliminati
definitivamente. Clienti, lavori, fatture (emesse/acquisto) e prima nota sono
soggetti a conservazione obbligatoria di 10 anni (art. 2220 c.c., DPR 600/73):
vengono anonimizzati nei campi PII ma le righe e gli importi restano, perché i
documenti fiscali già emessi (PDF/XML) ne dipendono per la validità storica.
"""

from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.logger import get_logger

logger = get_logger("gdpr")

# Tabelle senza vincolo di conservazione fiscale: eliminazione definitiva per utente_id
_TABELLE_DA_ELIMINARE = [
    models.CaricoMateriale,
    models.MovimentoMagazzino,
    models.MaterialeUsatoLavoro,
    models.Materiale,
    models.ListinoVoce,
    models.PromemoriaCliente,
    models.SessioneLavoro,
    models.TimesheetCollab,
    models.RapportinoLavoro,
    models.SalLavoro,
    models.TemplatePreventivo,
    models.VocePreventivo,
    models.Garanzia,
    models.PushSubscription,
    models.ImpostazioniAzienda,
]


def _serializza(obj) -> dict:
    out = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        out[col.name] = val
    return out


def esporta_dati_utente(db: Session, utente_id: int) -> dict:
    """Raccoglie tutti i dati riconducibili all'utente in struttura JSON-serializzabile."""
    utente = db.query(models.Utente).filter(models.Utente.id == utente_id).first()

    def _tutti(model, campo="utente_id"):
        return [
            _serializza(r)
            for r in db.query(model).filter(getattr(model, campo) == utente_id).all()
        ]

    return {
        "esportato_il": datetime.now(timezone.utc).isoformat(),
        "utente": _serializza(utente) if utente else None,
        "impostazioni_azienda": _tutti(models.ImpostazioniAzienda),
        "clienti": _tutti(models.Cliente),
        "lavori": _tutti(models.Lavoro),
        "fornitori": _tutti(models.Fornitore),
        "materiali": _tutti(models.Materiale),
        "carichi_materiale": _tutti(models.CaricoMateriale),
        "movimenti_magazzino": _tutti(models.MovimentoMagazzino),
        "materiali_usati_lavoro": _tutti(models.MaterialeUsatoLavoro),
        "documenti_pdf": _tutti(models.DocumentoPDF),
        "foto_lavori": _tutti(models.FotoLavoro),
        "pagamenti_lavoro": _tutti(models.PagamentoLavoro),
        "allegati_lavoro": _tutti(models.AllegatoLavoro),
        "fatture_emesse": _tutti(models.FatturaEmessa),
        "template_preventivi": _tutti(models.TemplatePreventivo),
        "voci_preventivo": _tutti(models.VocePreventivo),
        "sessioni_lavoro": _tutti(models.SessioneLavoro),
        "garanzie": _tutti(models.Garanzia),
        "prima_nota": _tutti(models.VocePrimaNota),
        "fatture_acquisto": _tutti(models.FatturaAcquisto),
        "listino_voci": _tutti(models.ListinoVoce),
        "sal_lavoro": _tutti(models.SalLavoro),
        "rapportini_lavoro": _tutti(models.RapportinoLavoro),
        "promemoria_clienti": _tutti(models.PromemoriaCliente),
        "timesheet_collab": _tutti(models.TimesheetCollab),
        "audit_log": _tutti(models.AuditLog),
    }


def _elimina_file_fisico(percorso: str | None, tipo: str = "image") -> None:
    if not percorso:
        return
    try:
        if percorso.startswith("http"):
            from app.services.cloudinary_service import elimina_immagine, elimina_file
            if tipo == "image":
                elimina_immagine(percorso)
            else:
                elimina_file(percorso)
        else:
            Path(percorso).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Impossibile eliminare file fisico {percorso}: {e}")


def cancella_dati_utente(db: Session, utente_id: int) -> None:
    """Cancellazione GDPR (art. 17): elimina i dati senza vincolo fiscale, anonimizza il resto."""
    for foto in db.query(models.FotoLavoro).filter(models.FotoLavoro.utente_id == utente_id).all():
        _elimina_file_fisico(foto.percorso_file, "image")
    for allegato in db.query(models.AllegatoLavoro).filter(models.AllegatoLavoro.utente_id == utente_id).all():
        _elimina_file_fisico(allegato.percorso_file, "file")
    for doc in db.query(models.DocumentoPDF).filter(models.DocumentoPDF.utente_id == utente_id).all():
        _elimina_file_fisico(doc.percorso_file, "file")
    impostazioni = (
        db.query(models.ImpostazioniAzienda)
        .filter(models.ImpostazioniAzienda.utente_id == utente_id)
        .first()
    )
    if impostazioni and impostazioni.logo_path:
        _elimina_file_fisico(impostazioni.logo_path, "image")

    db.query(models.FotoLavoro).filter(models.FotoLavoro.utente_id == utente_id).delete()
    db.query(models.AllegatoLavoro).filter(models.AllegatoLavoro.utente_id == utente_id).delete()
    db.query(models.DocumentoPDF).filter(models.DocumentoPDF.utente_id == utente_id).delete()
    db.query(models.PagamentoLavoro).filter(models.PagamentoLavoro.utente_id == utente_id).delete()
    db.query(models.InvitoAccount).filter(models.InvitoAccount.titolare_id == utente_id).delete()

    for model in _TABELLE_DA_ELIMINARE:
        db.query(model).filter(model.utente_id == utente_id).delete()

    # Fornitori: nessun vincolo fiscale diretto; sganciati dai documenti conservati
    db.query(models.VocePrimaNota).filter(models.VocePrimaNota.utente_id == utente_id).update(
        {"fornitore_id": None}
    )
    db.query(models.FatturaAcquisto).filter(models.FatturaAcquisto.utente_id == utente_id).update(
        {"fornitore_id": None}
    )
    db.query(models.Fornitore).filter(models.Fornitore.utente_id == utente_id).delete()

    # Conservazione fiscale obbligatoria: anonimizza i campi PII, mantiene righe e importi
    db.query(models.Cliente).filter(models.Cliente.utente_id == utente_id).update({
        "nome": "Cliente",
        "cognome": "anonimizzato",
        "ragione_sociale": None,
        "telefono": None,
        "email": None,
        "indirizzo": None,
        "citta": None,
        "provincia": None,
        "cap": None,
        "partita_iva": None,
        "codice_fiscale": None,
        "codice_destinatario": None,
        "pec_destinatario": None,
        "note": None,
        "token_portale": None,
        "token_portale_scadenza": None,
    })

    db.query(models.Lavoro).filter(models.Lavoro.utente_id == utente_id).update({
        "titolo": "[anonimizzato]",
        "descrizione": None,
        "note_consuntivo": None,
        "firma_nome_cliente": None,
        "firma_ip": None,
        "token_firma": None,
    })

    db.commit()
    logger.info(f"Dati utente {utente_id} cancellati/anonimizzati per richiesta GDPR")
