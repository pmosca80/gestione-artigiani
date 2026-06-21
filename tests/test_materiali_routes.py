"""
Test HTTP per le route /materiali/*.

Copre: lista, form nuovo, creazione, lista acquisti, storico movimenti,
form/POST movimento, form/POST carico, storico per materiale,
isolamento multi-tenant (redirect silenzioso per risorse altrui).
"""
from datetime import date

import pytest

from app import models, crud

oggi = date.today()
oggi_str = str(oggi)


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username):
    u = models.Utente(
        username=username, password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _materiale(db, utente_id, nome="Tubo rame", quantita=10.0):
    return crud.crea_materiale(
        db, utente_id,
        nome=nome,
        categoria="idraulica",
        unita_misura="m",
        quantita=quantita,
        scorta_minima=2.0,
        prezzo_acquisto_pieno=5.0,
        prezzo_acquisto_scontato=4.5,
        prezzo_vendita_default=8.0,
        note="",
    )


# ── GET /materiali/nuovo ──────────────────────────────────────────────────────

def test_form_nuovo_materiale_ok(client_http):
    """GET /materiali/nuovo → 200."""
    resp = client_http.get("/materiali/nuovo")
    assert resp.status_code == 200


# ── POST /materiali/nuovo ─────────────────────────────────────────────────────

def test_crea_materiale_happy_path(client_http, db, utente_test):
    """POST crea materiale → materiale in DB, redirect a /materiali/."""
    resp = client_http.post(
        "/materiali/nuovo",
        data={
            "nome": "Raccordo ottone",
            "categoria": "idraulica",
            "unita_misura": "pz",
            "quantita": "50",
            "scorta_minima": "10",
            "prezzo_acquisto_pieno": "2.50",
            "prezzo_acquisto_scontato": "2.00",
            "prezzo_vendita_default": "4.00",
            "note": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/materiali/" in resp.headers["location"]
    assert "toast=Materiale%20salvato" in resp.headers["location"]

    materiali = crud.get_materiali(db, utente_test.id)
    assert len(materiali) == 1
    assert materiali[0].nome == "Raccordo ottone"
    assert materiali[0].quantita == 50.0


def test_lista_materiali_mostra_solo_propri(client_http, db, utente_test):
    """Lista materiali filtra per utente → materiali altrui non appaiono."""
    altro = _utente(db, "altro1@t.it")
    _materiale(db, utente_test.id, nome="Tubo rame proprio XYZ")
    _materiale(db, altro.id, nome="Tubo rame altrui ABC")

    resp = client_http.get("/materiali/")
    assert resp.status_code == 200
    assert "Tubo rame proprio XYZ" in resp.text
    assert "Tubo rame altrui ABC" not in resp.text


def test_lista_materiali_vuota_senza_ricerca_invita_a_creare(client_http):
    """Regressione: con zero materiali e nessuna ricerca attiva, lo stato
    vuoto deve invitare a creare il primo materiale."""
    resp = client_http.get("/materiali/")
    assert resp.status_code == 200
    assert "Nessun materiale inserito ancora" in resp.text
    assert "Aggiungi il primo materiale" in resp.text


def test_lista_materiali_con_ricerca_senza_risultati_mostra_reset(client_http, db, utente_test):
    """Regressione: se esiste già almeno un materiale ma la ricerca non
    trova corrispondenze, il messaggio non deve invitare a creare il
    primo materiale (ce ne sono già) ma a resettare la ricerca."""
    _materiale(db, utente_test.id, nome="Tubo rame")

    resp = client_http.get("/materiali/?cerca=parola-che-non-esiste-mai")
    assert resp.status_code == 200
    assert "Reset ricerca" in resp.text
    assert "Aggiungi il primo materiale" not in resp.text


# ── GET /materiali/lista-acquisti ─────────────────────────────────────────────

def test_lista_acquisti_ok(client_http):
    """GET /materiali/lista-acquisti → 200."""
    resp = client_http.get("/materiali/lista-acquisti")
    assert resp.status_code == 200


def test_lista_acquisti_mostra_sotto_scorta(client_http, db, utente_test):
    """Materiale con quantita <= scorta_minima appare nella lista acquisti."""
    mat = _materiale(db, utente_test.id, nome="Valvola esaurita", quantita=1.0)
    # scorta_minima=2, quantita=1 → da riordinare

    resp = client_http.get("/materiali/lista-acquisti")
    assert resp.status_code == 200
    assert "Valvola esaurita" in resp.text


# ── GET /materiali/movimenti/storico ──────────────────────────────────────────

def test_storico_movimenti_ok(client_http):
    """GET /materiali/movimenti/storico → 200."""
    resp = client_http.get("/materiali/movimenti/storico")
    assert resp.status_code == 200


# ── GET /materiali/{id}/movimento ────────────────────────────────────────────

def test_form_movimento_proprio_ok(client_http, db, utente_test):
    """GET form movimento materiale proprio → 200."""
    mat = _materiale(db, utente_test.id)

    resp = client_http.get(f"/materiali/{mat.id}/movimento")
    assert resp.status_code == 200


def test_form_movimento_altrui_redirect(client_http, db, utente_test):
    """GET form movimento materiale altrui → redirect silenzioso a /materiali/."""
    altro = _utente(db, "altro2@t.it")
    mat = _materiale(db, altro.id)

    resp = client_http.get(f"/materiali/{mat.id}/movimento", follow_redirects=False)
    assert resp.status_code == 303
    assert "/materiali/" in resp.headers["location"]


# ── POST /materiali/{id}/movimento ───────────────────────────────────────────

def test_salva_movimento_carico(client_http, db, utente_test):
    """POST movimento tipo=carico → quantità materiale aumentata."""
    mat = _materiale(db, utente_test.id, quantita=10.0)

    resp = client_http.post(
        f"/materiali/{mat.id}/movimento",
        data={"tipo": "carico", "quantita": "5", "note": "riordine"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(mat)
    assert mat.quantita == 15.0


def test_salva_movimento_scarico(client_http, db, utente_test):
    """POST movimento tipo=scarico → quantità materiale diminuita."""
    mat = _materiale(db, utente_test.id, quantita=20.0)

    client_http.post(
        f"/materiali/{mat.id}/movimento",
        data={"tipo": "scarico", "quantita": "3", "note": "usato in lavoro"},
        follow_redirects=False,
    )

    db.refresh(mat)
    assert mat.quantita == 17.0


# ── GET /materiali/{id}/movimenti ────────────────────────────────────────────

def test_storico_movimenti_materiale_ok(client_http, db, utente_test):
    """GET storico movimenti materiale proprio → 200."""
    mat = _materiale(db, utente_test.id)

    resp = client_http.get(f"/materiali/{mat.id}/movimenti")
    assert resp.status_code == 200


def test_storico_movimenti_materiale_altrui_redirect(client_http, db, utente_test):
    """GET storico movimenti materiale altrui → redirect silenzioso."""
    altro = _utente(db, "altro3@t.it")
    mat = _materiale(db, altro.id)

    resp = client_http.get(f"/materiali/{mat.id}/movimenti", follow_redirects=False)
    assert resp.status_code == 303


# ── GET /materiali/{id}/carico ───────────────────────────────────────────────

def test_form_carico_materiale_ok(client_http, db, utente_test):
    """GET form carico materiale proprio → 200."""
    mat = _materiale(db, utente_test.id)

    resp = client_http.get(f"/materiali/{mat.id}/carico")
    assert resp.status_code == 200


def test_form_carico_materiale_altrui_redirect(client_http, db, utente_test):
    """GET form carico materiale altrui → redirect silenzioso."""
    altro = _utente(db, "altro4@t.it")
    mat = _materiale(db, altro.id)

    resp = client_http.get(f"/materiali/{mat.id}/carico", follow_redirects=False)
    assert resp.status_code == 303


# ── POST /materiali/{id}/carico ──────────────────────────────────────────────

def test_salva_carico_materiale(client_http, db, utente_test):
    """POST carico → quantità materiale aumentata, redirect a /materiali/."""
    mat = _materiale(db, utente_test.id, quantita=10.0)
    qt_iniziale = mat.quantita

    resp = client_http.post(
        f"/materiali/{mat.id}/carico",
        data={
            "quantita": "20",
            "prezzo_acquisto": "4.50",
            "prezzo_vendita_default": "8.00",
            "note": "nuovo arrivo",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/materiali/" in resp.headers["location"]

    db.refresh(mat)
    assert mat.quantita == qt_iniziale + 20.0


def test_carico_materiale_quantita_negativa_non_registrato(client_http, db, utente_test):
    """Regressione: una quantità negativa nel carico abbassava lo stock
    invece di aumentarlo, falsificando l'inventario."""
    mat = _materiale(db, utente_test.id, quantita=10.0)
    carichi_iniziali = db.query(models.CaricoMateriale).filter(
        models.CaricoMateriale.materiale_id == mat.id
    ).count()

    resp = client_http.post(
        f"/materiali/{mat.id}/carico",
        data={"quantita": "-5", "prezzo_acquisto": "4.50", "prezzo_vendita_default": "8.00"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=quantita" in resp.headers["location"]

    db.refresh(mat)
    assert mat.quantita == 10.0
    assert db.query(models.CaricoMateriale).filter(
        models.CaricoMateriale.materiale_id == mat.id
    ).count() == carichi_iniziali


def test_carico_materiale_prezzo_negativo_non_registrato(client_http, db, utente_test):
    mat = _materiale(db, utente_test.id, quantita=10.0)

    resp = client_http.post(
        f"/materiali/{mat.id}/carico",
        data={"quantita": "5", "prezzo_acquisto": "-1", "prezzo_vendita_default": "8.00"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=quantita" in resp.headers["location"]

    db.refresh(mat)
    assert mat.quantita == 10.0


# ── POST /materiali/{id}/movimento ───────────────────────────────────────────

def test_movimento_quantita_negativa_non_registrato(client_http, db, utente_test):
    """Regressione: un 'carico' con quantità negativa diminuiva lo stock (e
    viceversa per 'scarico'), in contraddizione con l'etichetta del movimento."""
    mat = _materiale(db, utente_test.id, quantita=10.0)

    resp = client_http.post(
        f"/materiali/{mat.id}/movimento",
        data={"tipo": "carico", "quantita": "-3", "note": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=quantita" in resp.headers["location"]

    db.refresh(mat)
    assert mat.quantita == 10.0
    assert db.query(models.MovimentoMagazzino).filter(
        models.MovimentoMagazzino.materiale_id == mat.id
    ).count() == 0


def test_movimento_tipo_non_valido_non_registrato(client_http, db, utente_test):
    """Regressione: un 'tipo' arbitrario creava comunque una riga di
    movimento senza alterare lo stock — un audit trail fuorviante."""
    mat = _materiale(db, utente_test.id, quantita=10.0)

    resp = client_http.post(
        f"/materiali/{mat.id}/movimento",
        data={"tipo": "qualcosaltro", "quantita": "3", "note": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=quantita" in resp.headers["location"]

    assert db.query(models.MovimentoMagazzino).filter(
        models.MovimentoMagazzino.materiale_id == mat.id
    ).count() == 0


def test_movimento_carico_positivo_registrato(client_http, db, utente_test):
    """Controllo di non-regressione: un movimento valido deve continuare a funzionare."""
    mat = _materiale(db, utente_test.id, quantita=10.0)

    resp = client_http.post(
        f"/materiali/{mat.id}/movimento",
        data={"tipo": "carico", "quantita": "3", "note": "rifornimento"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore" not in resp.headers["location"]

    db.refresh(mat)
    assert mat.quantita == 13.0
