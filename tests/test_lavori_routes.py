"""
Test HTTP per le route /lavori/*.

Copre: creazione lavoro (form cliente e rapido), modifica, voci preventivo,
filtri lista, pagine aggregate (agenda, calendario, analisi, preventivi)
e isolamento multi-tenant.
"""
from datetime import date

import pytest

from app import models, crud
from app.models import VocePreventivo
from app.services.calcoli import calcola_totali_lavoro
from app.routes.lavori import _riga_totale_voci_pdf, _mostra_sezione_materiali_usati_pdf

oggi = date.today()
oggi_str = str(oggi)


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username, piano="pro"):
    u = models.Utente(
        username=username, password="x", piano=piano,
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _cliente(db, utente_id):
    c = models.Cliente(
        utente_id=utente_id, tipo_cliente="privato",
        nome="Mario", cognome="Rossi",
        data_creazione=oggi_str,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _lavoro(db, utente_id, cliente_id, *, titolo="Impianto gas", stato="in_corso"):
    l = models.Lavoro(
        utente_id=utente_id, cliente_id=cliente_id,
        titolo=titolo, data_lavoro=oggi, stato=stato,
        priorita="normale", aliquota_iva=22.0, sconto=0.0,
        importo_pagato=0.0, data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


def _voce(db, utente_id, lavoro_id, descrizione="Manodopera", prezzo=100.0):
    return crud.crea_voce_preventivo(
        db, utente_id, lavoro_id,
        descrizione=descrizione, quantita=1.0,
        unita_misura="ore", prezzo_unitario=prezzo,
    )


# ── POST /lavori/nuovo/{cliente_id} ──────────────────────────────────────────

def test_crea_lavoro_happy_path(client_http, db, utente_test, cliente_test):
    """Creazione via form cliente → redirect diretto alla schermata voci
    (materiale/manodopera/lavori da fare si aggiungono lì), non più alla
    scheda cliente: prima il preventivo si creava in un passo separato
    dall'aggiunta delle voci, costringendo l'utente a navigare altrove."""
    resp = client_http.post(
        f"/lavori/nuovo/{cliente_test.id}",
        data={
            "data_lavoro": oggi_str,
            "titolo": "Nuovo impianto",
            "descrizione": "",
            "stato": "preventivo",
            "importo_preventivato": "800",
            "importo_consuntivo": "",
            "note_consuntivo": "",
            "aliquota_iva": "22",
            "sconto": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    lavori = db.query(models.Lavoro).filter(models.Lavoro.utente_id == utente_test.id).all()
    assert len(lavori) == 1
    assert lavori[0].titolo == "Nuovo impianto"
    assert resp.headers["location"] == f"/lavori/{lavori[0].id}/voci?toast=Lavoro%20creato"


def test_crea_lavoro_cliente_inesistente(client_http, db, utente_test):
    """Cliente non trovato → 404."""
    resp = client_http.post(
        "/lavori/nuovo/999999",
        data={
            "data_lavoro": oggi_str,
            "titolo": "Test",
            "stato": "preventivo",
            "aliquota_iva": "22",
            "sconto": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


def test_crea_lavoro_cliente_altrui_404(client_http, db, utente_test):
    """Cliente di un altro utente → 404 (isolamento multi-tenant)."""
    altro = _utente(db, "altro@t.it")
    cli = _cliente(db, altro.id)

    resp = client_http.post(
        f"/lavori/nuovo/{cli.id}",
        data={
            "data_lavoro": oggi_str,
            "titolo": "Tentativo",
            "stato": "preventivo",
            "aliquota_iva": "22",
            "sconto": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── POST /lavori/nuovo-rapido ─────────────────────────────────────────────────

def test_crea_lavoro_rapido(client_http, db, utente_test, cliente_test):
    """Creazione rapida → redirect al dettaglio del nuovo lavoro."""
    resp = client_http.post(
        "/lavori/nuovo-rapido",
        data={
            "cliente_id": str(cliente_test.id),
            "titolo": "Lavoro rapido",
            "data_lavoro": oggi_str,
            "stato": "da_fare",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith("/lavori/")
    assert "toast=Lavoro%20creato" in loc

    lavoro_id = int(loc.split("/lavori/")[1].split("?")[0].rstrip("/"))
    lavoro = db.get(models.Lavoro, lavoro_id)
    assert lavoro is not None
    assert lavoro.titolo == "Lavoro rapido"
    assert lavoro.utente_id == utente_test.id


def test_crea_lavoro_rapido_cliente_altrui_404(client_http, db, utente_test):
    """Lavoro rapido con cliente altrui → 404."""
    altro = _utente(db, "altro2@t.it")
    cli = _cliente(db, altro.id)

    resp = client_http.post(
        "/lavori/nuovo-rapido",
        data={
            "cliente_id": str(cli.id),
            "titolo": "Tentativo",
            "data_lavoro": oggi_str,
            "stato": "da_fare",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── POST /lavori/{lavoro_id}/modifica ────────────────────────────────────────

def test_modifica_lavoro_aggiorna_titolo(client_http, db, utente_test, cliente_test, lavoro_test):
    """Modifica titolo e stato → redirect a /clienti/{id}, campo aggiornato."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/modifica",
        data={
            "data_lavoro": oggi_str,
            "titolo": "Titolo aggiornato",
            "descrizione": "",
            "stato": "completato",
            "importo_preventivato": "2000",
            "importo_consuntivo": "1800",
            "ore_lavoro": "8",
            "costo_orario": "35",
            "aliquota_iva": "22",
            "sconto": "0",
            "data_scadenza_pagamento": "",
            "note_consuntivo": "",
            "numero_fattura": "",
            "data_fattura": "",
            "ritenuta_acconto": "0",
            "aliquota_ritenuta": "20",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/clienti/{cliente_test.id}" in resp.headers["location"]
    assert "toast=Lavoro%20aggiornato" in resp.headers["location"]

    db.refresh(lavoro_test)
    assert lavoro_test.titolo == "Titolo aggiornato"
    assert lavoro_test.stato == "completato"


def test_modifica_lavoro_altrui_404(client_http, db, utente_test):
    """Modifica di un lavoro altrui → 404."""
    altro = _utente(db, "altro3@t.it")
    cli = _cliente(db, altro.id)
    lav = _lavoro(db, altro.id, cli.id)

    resp = client_http.post(
        f"/lavori/{lav.id}/modifica",
        data={
            "data_lavoro": oggi_str,
            "titolo": "Tentativo",
            "stato": "in_corso",
            "importo_preventivato": "",
            "importo_consuntivo": "",
            "ore_lavoro": "0",
            "costo_orario": "0",
            "aliquota_iva": "22",
            "sconto": "0",
            "data_scadenza_pagamento": "",
            "note_consuntivo": "",
            "numero_fattura": "",
            "data_fattura": "",
            "ritenuta_acconto": "0",
            "aliquota_ritenuta": "20",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ── POST /lavori/{lavoro_id}/elimina ─────────────────────────────────────────

def test_elimina_lavoro_proprio(client_http, db, utente_test, cliente_test, lavoro_test):
    """Elimina lavoro → rimosso dal DB, redirect alla scheda cliente con toast."""
    resp = client_http.post(f"/lavori/{lavoro_test.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303
    assert f"/clienti/{cliente_test.id}" in resp.headers["location"]
    assert "toast=Lavoro%20eliminato" in resp.headers["location"]

    rimasto = db.get(models.Lavoro, lavoro_test.id)
    assert rimasto is None


def test_elimina_lavoro_altrui_404(client_http, db, utente_test):
    """Elimina lavoro di un altro utente → 404."""
    altro = _utente(db, "altro5@t.it")
    cli = _cliente(db, altro.id)
    lav = _lavoro(db, altro.id, cli.id)

    resp = client_http.post(f"/lavori/{lav.id}/elimina", follow_redirects=False)
    assert resp.status_code == 404


def test_elimina_lavoro_con_voci_e_sottorisorse(client_http, db, utente_test, cliente_test, lavoro_test):
    """Regressione: in produzione (Postgres) il vincolo di foreign key
    impediva di eliminare un lavoro che avesse voci preventivo o altre
    sotto-risorse, perché nessuno le rimuoveva prima — SQLite (usato nei
    test) non applica il vincolo e quindi non lo segnalava. Le
    sotto-risorse senza significato proprio devono sparire col lavoro; i
    record fiscali indipendenti (prima nota) devono solo scollegarsi."""
    voce = _voce(db, utente_test.id, lavoro_test.id, "Voce", prezzo=100.0)
    voce_id = voce.id

    nota = models.VocePrimaNota(
        utente_id=utente_test.id, lavoro_id=lavoro_test.id,
        data=oggi_str, descrizione="Acconto cliente", importo=100.0, tipo="entrata",
        data_creazione=oggi_str,
    )
    db.add(nota); db.commit(); db.refresh(nota)

    resp = client_http.post(f"/lavori/{lavoro_test.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303

    assert db.get(models.Lavoro, lavoro_test.id) is None
    assert db.query(VocePreventivo).filter(VocePreventivo.id == voce_id).count() == 0

    db.refresh(nota)
    assert db.get(models.VocePrimaNota, nota.id) is not None
    assert nota.lavoro_id is None


# ── Filtri GET /lavori/ ───────────────────────────────────────────────────────

def test_filtra_lavori_per_stato(client_http, db, utente_test, cliente_test):
    """Filtro ?stato=completato → 200, mostra solo i lavori completati."""
    _lavoro(db, utente_test.id, cliente_test.id, titolo="Posa piastrelle XYZ", stato="completato")
    _lavoro(db, utente_test.id, cliente_test.id, titolo="Sostituzione caldaia ABC", stato="in_corso")

    resp = client_http.get("/lavori/?stato=completato")
    assert resp.status_code == 200
    assert "Posa piastrelle XYZ" in resp.text
    assert "Sostituzione caldaia ABC" not in resp.text


def test_lista_lavori_con_ricerca(client_http, db, utente_test, cliente_test):
    """Ricerca testuale → 200 con risultati filtrati."""
    _lavoro(db, utente_test.id, cliente_test.id, titolo="Impianto caldaia")
    _lavoro(db, utente_test.id, cliente_test.id, titolo="Revisione tetto")

    resp = client_http.get("/lavori/?ricerca=caldaia")
    assert resp.status_code == 200
    assert "Impianto caldaia" in resp.text
    assert "Revisione tetto" not in resp.text


def test_lista_lavori_vuota_senza_filtri_invita_a_creare(client_http, db, utente_test):
    """Regressione: con zero lavori e nessun filtro attivo, lo stato vuoto
    parlava di 'filtri selezionati' e offriva solo 'Reset filtri' - testo
    fuorviante per chi non ha mai creato nulla, senza alcuna call-to-action
    per creare il primo lavoro."""
    resp = client_http.get("/lavori/")
    assert resp.status_code == 200
    assert "Non hai ancora nessun lavoro" in resp.text
    assert "Crea il primo lavoro" in resp.text
    assert "filtri selezionati" not in resp.text


def test_lista_lavori_vuota_con_filtro_mostra_reset(client_http, db, utente_test, cliente_test):
    """Quando invece il filtro è la causa reale dell'elenco vuoto (esiste
    almeno un lavoro, ma non corrisponde ai filtri), il messaggio deve
    restare quello sui filtri con il bottone di reset."""
    _lavoro(db, utente_test.id, cliente_test.id, titolo="Impianto caldaia")

    resp = client_http.get("/lavori/?ricerca=parola-che-non-esiste-mai")
    assert resp.status_code == 200
    assert "filtri selezionati" in resp.text
    assert "Reset filtri" in resp.text
    assert "Non hai ancora nessun lavoro" not in resp.text


# ── Voci preventivo ───────────────────────────────────────────────────────────

def test_lista_voci_lavoro_ok(client_http, db, utente_test, cliente_test, lavoro_test):
    """GET /lavori/{id}/voci → 200."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}/voci")
    assert resp.status_code == 200


def test_aggiungi_voce_lavoro(client_http, db, utente_test, cliente_test, lavoro_test):
    """POST voce → voce presente in DB, redirect alla pagina voci."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/voci",
        data={
            "descrizione": "Manodopera specializzata",
            "quantita": "2",
            "unita_misura": "ore",
            "prezzo_unitario": "60",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/lavori/{lavoro_test.id}/voci" in resp.headers["location"]

    voci = crud.get_voci_preventivo(db, utente_test.id, lavoro_test.id)
    assert len(voci) == 1
    assert voci[0].descrizione == "Manodopera specializzata"
    assert voci[0].prezzo_unitario == 60.0


def test_elimina_voce_preventivo(client_http, db, utente_test, cliente_test, lavoro_test):
    """Elimina voce → rimossa dal DB, redirect alle voci del lavoro."""
    voce = _voce(db, utente_test.id, lavoro_test.id, "Voce da eliminare")

    resp = client_http.post(
        f"/lavori/voci-preventivo/{voce.id}/elimina",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    voci_rimaste = crud.get_voci_preventivo(db, utente_test.id, lavoro_test.id)
    assert len(voci_rimaste) == 0


def test_aggiungi_voce_ricalcola_importo_consuntivo(client_http, db, utente_test, cliente_test, lavoro_test):
    """Regressione: aggiungere una voce non aggiornava importo_consuntivo
    finché non si salvava separatamente la scheda "modifica lavoro" — la
    parte economica (e i PDF) restava scollegata dalle voci appena
    inserite. POST /voci deve ricalcolare subito il totale."""
    assert (lavoro_test.importo_consuntivo or 0) == 0

    client_http.post(
        f"/lavori/{lavoro_test.id}/voci",
        data={"descrizione": "Caldaia", "quantita": "1", "unita_misura": "pz", "prezzo_unitario": "450"},
        follow_redirects=False,
    )

    db.refresh(lavoro_test)
    assert lavoro_test.importo_consuntivo == 450.0


def test_elimina_voce_ricalcola_importo_consuntivo(client_http, db, utente_test, cliente_test, lavoro_test):
    """Eliminare l'ultima voce deve far ricadere il consuntivo sul vecchio
    calcolo (ore×tariffa, qui 8h×35€=280 dalla fixture), non lasciare il
    valore della voce appena rimossa (450€)."""
    voce = _voce(db, utente_test.id, lavoro_test.id, "Voce", prezzo=450.0)
    calcola_totali_lavoro(db, lavoro_test.id)
    db.refresh(lavoro_test)
    assert lavoro_test.importo_consuntivo == 450.0

    client_http.post(f"/lavori/voci-preventivo/{voce.id}/elimina", follow_redirects=False)

    db.refresh(lavoro_test)
    assert lavoro_test.importo_consuntivo == 280.0


# ── GET /lavori/{id}/pdf (stampa completa) ───────────────────────────────────
# Nota: questo PDF usa stream compressi (ASCII85+Flate), quindi il testo non
# è cercabile nei byte grezzi della risposta HTTP — la logica di formattazione
# è estratta in funzioni pure (_riga_totale_voci_pdf,
# _mostra_sezione_materiali_usati_pdf) testate direttamente; la route resta
# verificata solo come smoke test (200 + PDF valido), come da convenzione
# già usata in test_pdf_fattura.py.

def test_riga_totale_voci_pdf_senza_markup_html_grezzo():
    """Regressione: la riga era costruita con <b>...</b> dentro una cella
    di Table (non Paragraph) — ReportLab non interpreta quel markup lì, lo
    disegna come testo letterale visibile ("<b>Totale voci</b>"). Il
    grassetto è già dato dalla TableStyle della riga, niente markup serve."""
    riga = _riga_totale_voci_pdf(265.0)
    assert riga == ["", "", "", "Totale voci", "EUR 265.00"]
    assert "<" not in "".join(riga)


def test_mostra_sezione_materiali_con_scarico_reale():
    assert _mostra_sezione_materiali_usati_pdf(materiali_usati=["x"], voci_preventivo=[]) is True
    assert _mostra_sezione_materiali_usati_pdf(materiali_usati=["x"], voci_preventivo=["y"]) is True


def test_nasconde_sezione_materiali_con_voci_e_senza_scarico_reale():
    """Regressione: con voci compilate ma senza scarico reale, il PDF
    mostrava "Nessun materiale associato al lavoro" subito sotto una
    tabella che invece elenca chiaramente i materiali (come voci) —
    messaggio contraddittorio."""
    assert _mostra_sezione_materiali_usati_pdf(materiali_usati=[], voci_preventivo=["y"]) is False


def test_mostra_sezione_materiali_senza_voci_e_senza_scarico_reale():
    """Senza voci e senza materiali reali, la sezione resta (nessuna
    regressione per i lavori che non usano il sistema a voci)."""
    assert _mostra_sezione_materiali_usati_pdf(materiali_usati=[], voci_preventivo=[]) is True


def test_pdf_lavoro_con_voci_smoke(client_http, db, utente_test, cliente_test, lavoro_test):
    """La route deve generare un PDF valido quando il lavoro ha voci
    preventivo (percorso toccato dalla fix sopra)."""
    _voce(db, utente_test.id, lavoro_test.id, "Piastrelle", prezzo=5.0)
    calcola_totali_lavoro(db, lavoro_test.id)

    resp = client_http.get(f"/lavori/{lavoro_test.id}/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_voci_lavoro_mostra_catalogo_magazzino(client_http, db, utente_test, cliente_test, lavoro_test):
    """La pagina voci preventivo deve offrire un selettore rapido dei
    materiali a magazzino (prezzo/unità di misura precompilati), in modo
    da poterli aggiungere come stima al preventivo senza scaricare le
    scorte (lo scarico reale resta legato alla scheda /materiali)."""
    _materiale(db, utente_test.id)

    resp = client_http.get(f"/lavori/{lavoro_test.id}/voci")
    assert resp.status_code == 200
    assert "Scegli dal magazzino" in resp.text
    assert "Tubo PVC" in resp.text


def test_voci_lavoro_senza_materiali_non_mostra_selettore_magazzino(client_http, db, utente_test, cliente_test, lavoro_test):
    """Senza materiali a catalogo, il selettore non deve apparire (nulla da scegliere)."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}/voci")
    assert resp.status_code == 200
    assert "Scegli dal magazzino" not in resp.text


def test_voci_lavoro_genera_link_pubblico_e_bottone_whatsapp(client_http, db, utente_test, cliente_test, lavoro_test):
    """Regressione: la pagina voci deve generare in automatico il token
    pubblico /firma/{token} (senza un'azione separata) e mostrare un
    bottone WhatsApp con quel link, così l'utente può condividere il
    preventivo senza uscire dalla schermata dove lo compone."""
    assert lavoro_test.token_firma is None

    resp = client_http.get(f"/lavori/{lavoro_test.id}/voci")
    assert resp.status_code == 200

    db.refresh(lavoro_test)
    assert lavoro_test.token_firma is not None
    assert f"/firma/{lavoro_test.token_firma}" in resp.text
    assert "data-wa-tipo=\"preventivo\"" in resp.text


def test_voci_lavoro_riusa_token_firma_esistente(client_http, db, utente_test, cliente_test, lavoro_test):
    """Se il token esiste già (generato altrove), la pagina voci non deve
    rigenerarlo — il link condiviso in precedenza deve restare valido."""
    crud.genera_token_firma(db, lavoro_test.id, utente_test.id)
    db.refresh(lavoro_test)
    token_originale = lavoro_test.token_firma

    client_http.get(f"/lavori/{lavoro_test.id}/voci")

    db.refresh(lavoro_test)
    assert lavoro_test.token_firma == token_originale


def test_dashboard_preventivi_whatsapp_include_link_firma(client_http, db, utente_test, cliente_test):
    """Regressione: il bottone WhatsApp nella dashboard preventivi mandava
    un messaggio che affermava di allegare il PDF, cosa che wa.me non fa
    mai — deve invece includere il link pubblico /firma/{token}."""
    lavoro = _lavoro(db, utente_test.id, cliente_test.id, stato="preventivo")
    lavoro.importo_preventivato = 500.0
    db.commit()

    resp = client_http.get("/lavori/preventivi/dashboard")
    assert resp.status_code == 200

    db.refresh(lavoro)
    assert lavoro.token_firma is not None
    assert f"/firma/{lavoro.token_firma}" in resp.text


# ── Modifica lavoro: importo da voci preventivo ──────────────────────────────

def test_modifica_lavoro_con_voci_mostra_importo_da_voci_disabilitato(client_http, db, utente_test, cliente_test, lavoro_test):
    """Se il lavoro ha voci preventivo, il campo "Preventivo cliente" deve
    diventare di sola lettura (l'importo arriva dalle voci, non si digita
    più a mano un numero che può disallinearsi)."""
    _voce(db, utente_test.id, lavoro_test.id, "Voce A", prezzo=200.0)

    resp = client_http.get(f"/lavori/{lavoro_test.id}/modifica")
    assert resp.status_code == 200
    assert "da voci" in resp.text
    assert 'name="importo_preventivato"' not in resp.text
    assert "Modifica voci preventivo" in resp.text


def test_modifica_lavoro_senza_voci_mostra_campo_manuale(client_http, db, utente_test, cliente_test, lavoro_test):
    """Senza voci preventivo, il campo importo resta modificabile a mano
    come prima (nessuna regressione per i lavori che non usano le voci)."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}/modifica")
    assert resp.status_code == 200
    assert 'name="importo_preventivato"' in resp.text


def test_modifica_lavoro_con_voci_aggiorna_importo_consuntivo(client_http, db, utente_test, cliente_test, lavoro_test):
    """POST /modifica su un lavoro con voci deve calcolare importo_consuntivo
    dalla somma delle voci, ignorando ore_lavoro/costo_orario del form."""
    _voce(db, utente_test.id, lavoro_test.id, "Voce A", prezzo=300.0)

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/modifica",
        data={
            "data_lavoro": str(oggi),
            "titolo": lavoro_test.titolo,
            "descrizione": "",
            "stato": "in_corso",
            "ore_lavoro": "100",       # se usato darebbe un importo enorme
            "costo_orario": "100",
            "aliquota_iva": "0",
            "sconto": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(lavoro_test)
    assert lavoro_test.importo_consuntivo == 300.0
    assert lavoro_test.importo_preventivato == 300.0


# ── FAB azioni rapide ─────────────────────────────────────────────────────────

def test_fab_homepage_include_nuovo_preventivo(client_http, db, utente_test, cliente_test, lavoro_test):
    """Il pulsante azioni rapide (navbar, presente su tutte le pagine
    interne) deve includere "Nuovo Preventivo" accanto a Nuovo Cliente e
    Nuovo Lavoro."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}")
    assert resp.status_code == 200
    assert "Nuovo Preventivo" in resp.text
    assert '/lavori/nuovo-rapido?tipo=preventivo' in resp.text


def test_voci_lavoro_altrui_404(client_http, db, utente_test):
    """GET voci di un lavoro altrui → 404."""
    altro = _utente(db, "altro4@t.it")
    cli = _cliente(db, altro.id)
    lav = _lavoro(db, altro.id, cli.id)

    resp = client_http.get(f"/lavori/{lav.id}/voci")
    assert resp.status_code == 404


def test_timer_inizia_e_ferma(client_http, db, lavoro_test):
    """Avvia e ferma il timer di lavoro: regressione per data_creazione/inizio
    diventati datetime (non più stringa) dopo la migrazione j4k5l6m7n8o9 —
    chiudi_sessione() chiamava strptime() su un valore già datetime."""
    resp = client_http.post(f"/lavori/{lavoro_test.id}/timer/inizia", follow_redirects=False)
    assert resp.status_code == 303

    sessione = crud.get_sessione_aperta(db, lavoro_test.utente_id, lavoro_test.id)
    assert sessione is not None

    resp = client_http.post(f"/lavori/{lavoro_test.id}/timer/ferma", follow_redirects=False)
    assert resp.status_code == 303

    db.refresh(sessione)
    assert sessione.fine is not None
    assert sessione.ore_calcolate is not None


# ── Pagine aggregate ──────────────────────────────────────────────────────────

def test_agenda_scadenzario_ok(client_http):
    """GET /lavori/agenda/scadenzario → 200."""
    resp = client_http.get("/lavori/agenda/scadenzario")
    assert resp.status_code == 200


def test_agenda_settimana_ok(client_http):
    """GET /lavori/agenda/settimana → 200."""
    resp = client_http.get("/lavori/agenda/settimana")
    assert resp.status_code == 200


def test_calendario_lavori_ok(client_http):
    """GET /lavori/calendario → 200."""
    resp = client_http.get("/lavori/calendario")
    assert resp.status_code == 200


def test_preventivi_dashboard_ok(client_http):
    """GET /lavori/preventivi/dashboard → 200."""
    resp = client_http.get("/lavori/preventivi/dashboard")
    assert resp.status_code == 200


def test_analisi_economica_ok(client_http):
    """GET /lavori/analisi/economica → 200."""
    resp = client_http.get("/lavori/analisi/economica")
    assert resp.status_code == 200


def test_form_nuovo_rapido_ok(client_http):
    """GET /lavori/nuovo-rapido → 200."""
    resp = client_http.get("/lavori/nuovo-rapido")
    assert resp.status_code == 200


# ── Validazione importi negativi (pagamenti, materiali, SAL) ─────────────────

def test_pagamento_importo_negativo_non_registrato(client_http, db, lavoro_test):
    """Regressione: un importo negativo veniva registrato come un pagamento
    valido, falsificando la contabilità (sembra un rimborso al cliente)."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/pagamenti",
        data={"data_pagamento": str(date.today()), "importo": "-500", "metodo": "contanti"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=importo" in resp.headers["location"]
    assert db.query(models.PagamentoLavoro).filter(
        models.PagamentoLavoro.lavoro_id == lavoro_test.id
    ).count() == 0


def test_pagamento_importo_zero_non_registrato(client_http, db, lavoro_test):
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/pagamenti",
        data={"data_pagamento": str(date.today()), "importo": "0", "metodo": "contanti"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert db.query(models.PagamentoLavoro).filter(
        models.PagamentoLavoro.lavoro_id == lavoro_test.id
    ).count() == 0


def test_pagamento_importo_positivo_registrato(client_http, db, lavoro_test):
    """Controllo di non-regressione: un importo valido deve continuare a funzionare."""
    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/pagamenti",
        data={"data_pagamento": str(date.today()), "importo": "500", "metodo": "contanti"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore" not in resp.headers["location"]
    assert db.query(models.PagamentoLavoro).filter(
        models.PagamentoLavoro.lavoro_id == lavoro_test.id
    ).count() == 1


def _materiale(db, utente_id, quantita=100):
    m = models.Materiale(
        utente_id=utente_id, nome="Tubo PVC", quantita=quantita,
        data_creazione=str(date.today()),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    # Lo scarico materiale richiede un carico con scorta residua disponibile.
    db.add(models.CaricoMateriale(
        utente_id=utente_id, materiale_id=m.id,
        quantita_iniziale=quantita, quantita_residua=quantita,
        prezzo_acquisto=5.0, data_carico=date.today(),
    ))
    db.commit()
    return m


def test_materiale_quantita_negativa_non_registrato(client_http, db, utente_test, lavoro_test):
    """Regressione: una quantità negativa abbassava artificialmente il
    totale fatturabile del lavoro invece di essere rifiutata."""
    materiale = _materiale(db, utente_test.id)

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/materiali",
        data={"materiale_id": materiale.id, "quantita": "-5", "prezzo_unitario_cliente": "10"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=quantita" in resp.headers["location"]
    assert db.query(models.MaterialeUsatoLavoro).filter(
        models.MaterialeUsatoLavoro.lavoro_id == lavoro_test.id
    ).count() == 0


def test_materiale_prezzo_negativo_non_registrato(client_http, db, utente_test, lavoro_test):
    materiale = _materiale(db, utente_test.id)

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/materiali",
        data={"materiale_id": materiale.id, "quantita": "2", "prezzo_unitario_cliente": "-10"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=quantita" in resp.headers["location"]
    assert db.query(models.MaterialeUsatoLavoro).filter(
        models.MaterialeUsatoLavoro.lavoro_id == lavoro_test.id
    ).count() == 0


def test_materiale_quantita_positiva_registrato(client_http, db, utente_test, lavoro_test):
    materiale = _materiale(db, utente_test.id)

    resp = client_http.post(
        f"/lavori/{lavoro_test.id}/materiali",
        data={"materiale_id": materiale.id, "quantita": "2", "prezzo_unitario_cliente": "10"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore" not in resp.headers["location"]
    assert db.query(models.MaterialeUsatoLavoro).filter(
        models.MaterialeUsatoLavoro.lavoro_id == lavoro_test.id
    ).count() == 1


def test_modifica_materiale_usato_quantita_negativa_ignorata(client_http, db, utente_test, lavoro_test):
    """La modifica con quantità negativa non deve alterare la riga esistente."""
    materiale = _materiale(db, utente_test.id)
    usato = models.MaterialeUsatoLavoro(
        utente_id=utente_test.id, lavoro_id=lavoro_test.id, materiale_id=materiale.id,
        quantita=3, costo_unitario=5, prezzo_unitario_cliente=10,
        data_creazione=str(date.today()),
    )
    db.add(usato)
    db.commit()
    db.refresh(usato)

    resp = client_http.post(
        f"/lavori/materiali-usati/{usato.id}/modifica",
        data={"quantita": "-99", "prezzo_unitario_cliente": "10"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(usato)
    assert usato.quantita == 3  # invariata
