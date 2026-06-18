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
    """Creazione via form cliente → redirect a /clienti/{id}."""
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
    assert f"/clienti/{cliente_test.id}" in resp.headers["location"]

    lavori = db.query(models.Lavoro).filter(models.Lavoro.utente_id == utente_test.id).all()
    assert len(lavori) == 1
    assert lavori[0].titolo == "Nuovo impianto"


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

    lavoro_id = int(loc.split("/lavori/")[1].rstrip("/"))
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
