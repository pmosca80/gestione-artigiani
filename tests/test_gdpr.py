"""Test per app/services/gdpr.py — export (art. 20) e cancellazione (art. 17)."""

from datetime import date

from app import models
from app.services.gdpr import cancella_dati_utente, esporta_dati_utente


# ── esporta_dati_utente ──────────────────────────────────────────────────────

def test_esporta_dati_contiene_utente_e_clienti(db, utente_test, cliente_test, lavoro_test):
    dati = esporta_dati_utente(db, utente_test.id)

    assert dati["utente"]["username"] == utente_test.username
    assert len(dati["clienti"]) == 1
    assert dati["clienti"][0]["nome"] == "Mario"
    assert len(dati["lavori"]) == 1
    assert dati["lavori"][0]["titolo"] == "Installazione impianto idraulico"
    assert "esportato_il" in dati


def test_esporta_dati_serializza_date_come_stringhe(db, utente_test, lavoro_test):
    dati = esporta_dati_utente(db, utente_test.id)
    assert isinstance(dati["lavori"][0]["data_lavoro"], str)


def test_esporta_dati_non_include_credenziali(db, utente_test):
    """Regressione: l'export GDPR (art. 20) decifrava e includeva in chiaro
    la password hash e il secret TOTP del 2FA — chiunque intercettasse il
    file scaricato avrebbe potuto bypassare il 2FA per sempre o tentare un
    attacco offline sulla password. Questi campi sono materiale
    d'autenticazione, non "dati personali" nel senso dell'art. 20."""
    utente_test.totp_secret = "JBSWY3DPEHPK3PXP"
    utente_test.totp_abilitato = True
    utente_test.token_verifica = "token-verifica-segreto"
    utente_test.token_reset = "token-reset-segreto"
    db.commit()

    dati = esporta_dati_utente(db, utente_test.id)
    utente_esportato = dati["utente"]

    for campo in ("password", "totp_secret", "token_verifica", "token_reset", "token_reset_scadenza"):
        assert campo not in utente_esportato, f"'{campo}' non deve comparire nell'export GDPR"

    # i campi non sensibili restano presenti
    assert utente_esportato["username"] == utente_test.username
    assert utente_esportato["totp_abilitato"] is True


def test_esporta_dati_non_include_password_pec(db, utente_test):
    """Regressione: pec_smtp_password è cifrata in DB ma l'ORM la decifra in
    lettura — l'export non deve includerla in chiaro."""
    db.add(models.ImpostazioniAzienda(
        utente_id=utente_test.id,
        nome_azienda="Idraulica Rossi",
        pec_smtp_password="superSegretaPEC123",
    ))
    db.commit()

    dati = esporta_dati_utente(db, utente_test.id)

    assert len(dati["impostazioni_azienda"]) == 1
    assert "pec_smtp_password" not in dati["impostazioni_azienda"][0]


def test_esporta_dati_non_include_dati_di_altri_utenti(db, utente_test, cliente_test):
    altro = models.Utente(username="altro@example.com", password="x", attivo=1)
    db.add(altro)
    db.commit()
    db.add(models.Cliente(
        utente_id=altro.id, tipo_cliente="privato", nome="Luigi",
        data_creazione=str(date.today()),
    ))
    db.commit()

    dati = esporta_dati_utente(db, utente_test.id)
    nomi = [c["nome"] for c in dati["clienti"]]
    assert "Luigi" not in nomi
    assert "Mario" in nomi


# ── cancella_dati_utente ─────────────────────────────────────────────────────

def _crea_materiale(db, utente_id):
    m = models.Materiale(
        utente_id=utente_id, nome="Tubo PVC", categoria="idraulica",
        quantita=10, data_creazione=str(date.today()),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _crea_fornitore(db, utente_id):
    f = models.Fornitore(
        utente_id=utente_id, nome="Fornitore SRL", email="f@example.com",
        data_creazione=str(date.today()),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _crea_fattura_emessa(db, utente_id, lavoro_id):
    fe = models.FatturaEmessa(
        utente_id=utente_id, lavoro_id=lavoro_id, numero=1, anno=2026,
        data_emissione=date.today(), importo_imponibile=1000, importo_iva=220,
        importo_totale=1220, data_creazione=str(date.today()),
    )
    db.add(fe)
    db.commit()
    db.refresh(fe)
    return fe


def test_cancella_elimina_materiale(db, utente_test):
    _crea_materiale(db, utente_test.id)
    cancella_dati_utente(db, utente_test.id)
    assert db.query(models.Materiale).filter(models.Materiale.utente_id == utente_test.id).count() == 0


def test_cancella_elimina_fornitore_e_nulla_fk_prima_nota(db, utente_test):
    fornitore = _crea_fornitore(db, utente_test.id)
    voce = models.VocePrimaNota(
        utente_id=utente_test.id, data=date.today(), descrizione="Acquisto materiali",
        importo=100, tipo="uscita", fornitore_id=fornitore.id,
        data_creazione=str(date.today()),
    )
    db.add(voce)
    db.commit()
    db.refresh(voce)

    cancella_dati_utente(db, utente_test.id)

    assert db.query(models.Fornitore).filter(models.Fornitore.utente_id == utente_test.id).count() == 0
    db.refresh(voce)
    assert voce.fornitore_id is None
    # la voce di prima nota resta (vincolo fiscale)
    assert db.query(models.VocePrimaNota).filter(models.VocePrimaNota.id == voce.id).count() == 1


def test_cancella_anonimizza_cliente_ma_non_lo_elimina(db, utente_test, cliente_test):
    cliente_id = cliente_test.id
    cancella_dati_utente(db, utente_test.id)

    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    assert cliente is not None  # riga conservata (vincolo fiscale)
    assert cliente.nome == "Cliente"
    assert cliente.cognome == "anonimizzato"
    assert cliente.telefono is None
    assert cliente.email is None


def test_cancella_anonimizza_lavoro_ma_conserva_importi(db, utente_test, lavoro_test):
    lavoro_id = lavoro_test.id
    importo_originale = lavoro_test.importo_preventivato

    cancella_dati_utente(db, utente_test.id)

    lavoro = db.query(models.Lavoro).filter(models.Lavoro.id == lavoro_id).first()
    assert lavoro is not None
    assert lavoro.titolo == "[anonimizzato]"
    assert lavoro.descrizione is None
    assert lavoro.importo_preventivato == importo_originale  # importi conservati


def test_cancella_non_elimina_fatture_emesse(db, utente_test, lavoro_test):
    fattura = _crea_fattura_emessa(db, utente_test.id, lavoro_test.id)
    fattura_id = fattura.id

    cancella_dati_utente(db, utente_test.id)

    assert db.query(models.FatturaEmessa).filter(models.FatturaEmessa.id == fattura_id).count() == 1


def test_cancella_elimina_garanzie_e_promemoria(db, utente_test, cliente_test, lavoro_test):
    db.add(models.Garanzia(
        utente_id=utente_test.id, cliente_id=cliente_test.id, lavoro_id=lavoro_test.id,
        descrizione="Caldaia", data_installazione=date.today(), durata_mesi=24,
        data_scadenza=date.today(), data_creazione=str(date.today()),
    ))
    db.add(models.PromemoriaCliente(
        utente_id=utente_test.id, cliente_id=cliente_test.id, titolo="Manutenzione",
        data_promemoria=date.today(), data_creazione=str(date.today()),
    ))
    db.commit()

    cancella_dati_utente(db, utente_test.id)

    assert db.query(models.Garanzia).filter(models.Garanzia.utente_id == utente_test.id).count() == 0
    assert db.query(models.PromemoriaCliente).filter(models.PromemoriaCliente.utente_id == utente_test.id).count() == 0


def test_cancella_elimina_impostazioni_azienda(db, utente_test):
    db.add(models.ImpostazioniAzienda(utente_id=utente_test.id, nome_azienda="Mastro SRL"))
    db.commit()

    cancella_dati_utente(db, utente_test.id)

    assert db.query(models.ImpostazioniAzienda).filter(
        models.ImpostazioniAzienda.utente_id == utente_test.id
    ).count() == 0


# ── route HTTP ───────────────────────────────────────────────────────────────

def test_export_route_restituisce_json_scaricabile(client_http, cliente_test):
    resp = client_http.get("/impostazioni/gdpr/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "attachment" in resp.headers["content-disposition"]
    body = resp.json()
    assert body["clienti"][0]["nome"] == "Mario"


def test_cancella_account_route_anonimizza_e_cancella_dati(client_http, db, utente_test, cliente_test):
    resp = client_http.post(
        "/impostazioni/cancella-account",
        data={"conferma_testo": "CANCELLA"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "account_cancellato" in resp.headers["location"]

    db.expire_all()
    utente = db.query(models.Utente).filter(models.Utente.id == utente_test.id).first()
    assert utente.attivo == 0
    assert utente.email is None

    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_test.id).first()
    assert cliente.nome == "Cliente"  # anonimizzato, non eliminato


def test_export_route_registra_audit_log(client_http, db, utente_test):
    """Per accountability (art. 5(2) GDPR) ogni export deve restare
    tracciato: chi, quando, su quale account."""
    utente_id = utente_test.id
    client_http.get("/impostazioni/gdpr/export")

    voce = db.query(models.AuditLog).filter(
        models.AuditLog.utente_id == utente_id,
        models.AuditLog.azione == "export_dati_gdpr",
    ).first()
    assert voce is not None


def test_cancella_account_route_registra_audit_log(client_http, db, utente_test):
    """La cancellazione GDPR deve restare tracciata nell'audit log, che
    sopravvive alla cancellazione dell'account (non è soggetto a oblio:
    serve come prova che la richiesta è stata eseguita)."""
    utente_id = utente_test.id
    client_http.post(
        "/impostazioni/cancella-account",
        data={"conferma_testo": "CANCELLA"},
        follow_redirects=False,
    )

    voce = db.query(models.AuditLog).filter(
        models.AuditLog.utente_id == utente_id,
        models.AuditLog.azione == "cancellazione_account_gdpr",
    ).first()
    assert voce is not None
