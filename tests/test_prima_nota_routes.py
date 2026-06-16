"""
Test HTTP per le route /prima-nota/*.

Copre: lista, aggiunta voce (entrata/uscita, validazione importo/descrizione),
eliminazione (propria e altrui), export CSV, isolamento multi-tenant.
"""
from datetime import date

import pytest

from app import models, crud

oggi = date.today()
oggi_str = str(oggi)
anno_corrente = oggi.year
mese_corrente = oggi.month


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username):
    u = models.Utente(
        username=username, password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _voce(db, utente_id, descrizione="Carburante", importo=50.0, tipo="uscita"):
    return crud.crea_voce_prima_nota(
        db, utente_id,
        data=oggi_str,
        descrizione=descrizione,
        importo=importo,
        tipo=tipo,
        categoria="carburante",
    )


# ── GET /prima-nota/ ──────────────────────────────────────────────────────────

def test_prima_nota_lista_ok(client_http):
    """GET /prima-nota/ → 200."""
    resp = client_http.get("/prima-nota/")
    assert resp.status_code == 200


def test_prima_nota_lista_mostra_solo_proprie(client_http, db, utente_test):
    """Voci di un altro utente non appaiono nella lista."""
    altro = _utente(db, "altro1@t.it")
    _voce(db, utente_test.id, descrizione="Benzina propria XYZ")
    _voce(db, altro.id, descrizione="Benzina altrui ABC")

    resp = client_http.get("/prima-nota/")
    assert resp.status_code == 200
    assert "Benzina propria XYZ" in resp.text
    assert "Benzina altrui ABC" not in resp.text


# ── POST /prima-nota/ ────────────────────────────────────────────────────────

def test_aggiungi_voce_entrata(client_http, db, utente_test):
    """POST voce tipo=entrata → voce in DB, redirect /prima-nota/."""
    resp = client_http.post(
        "/prima-nota/",
        data={
            "data": oggi_str,
            "descrizione": "Acconto cliente",
            "importo": "200",
            "tipo": "entrata",
            "categoria": "varie",
            "lavoro_id": "0",
            "cliente_id": "0",
            "anno": str(anno_corrente),
            "mese": str(mese_corrente),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/prima-nota/" in resp.headers["location"]

    voci = crud.get_prima_nota(db, utente_test.id)
    assert len(voci) == 1
    assert voci[0].descrizione == "Acconto cliente"
    assert voci[0].tipo == "entrata"
    assert voci[0].importo == 200.0


def test_aggiungi_voce_uscita(client_http, db, utente_test):
    """POST voce tipo=uscita → tipo e importo corretti in DB."""
    client_http.post(
        "/prima-nota/",
        data={
            "data": oggi_str,
            "descrizione": "Spesa gasolio",
            "importo": "75,50",
            "tipo": "uscita",
            "categoria": "carburante",
            "lavoro_id": "0",
            "cliente_id": "0",
            "anno": str(anno_corrente),
            "mese": str(mese_corrente),
        },
        follow_redirects=False,
    )

    voci = crud.get_prima_nota(db, utente_test.id)
    assert len(voci) == 1
    assert voci[0].tipo == "uscita"
    assert abs(voci[0].importo - 75.50) < 0.01


def test_aggiungi_voce_importo_zero_saltata(client_http, db, utente_test):
    """POST con importo=0 → nessuna voce creata (filtro server-side)."""
    client_http.post(
        "/prima-nota/",
        data={
            "data": oggi_str,
            "descrizione": "Voce nulla",
            "importo": "0",
            "tipo": "uscita",
            "categoria": "",
            "lavoro_id": "0",
            "cliente_id": "0",
            "anno": str(anno_corrente),
            "mese": str(mese_corrente),
        },
        follow_redirects=False,
    )

    voci = crud.get_prima_nota(db, utente_test.id)
    assert len(voci) == 0


def test_aggiungi_voce_descrizione_vuota_saltata(client_http, db, utente_test):
    """POST con descrizione vuota → nessuna voce creata."""
    client_http.post(
        "/prima-nota/",
        data={
            "data": oggi_str,
            "descrizione": "  ",
            "importo": "100",
            "tipo": "uscita",
            "categoria": "",
            "lavoro_id": "0",
            "cliente_id": "0",
            "anno": str(anno_corrente),
            "mese": str(mese_corrente),
        },
        follow_redirects=False,
    )

    voci = crud.get_prima_nota(db, utente_test.id)
    assert len(voci) == 0


# ── POST /prima-nota/{id}/elimina ─────────────────────────────────────────────

def test_elimina_voce_propria(client_http, db, utente_test):
    """POST elimina → voce rimossa dal DB."""
    voce = _voce(db, utente_test.id)

    resp = client_http.post(
        f"/prima-nota/{voce.id}/elimina",
        data={"anno": str(anno_corrente), "mese": str(mese_corrente)},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    voci = crud.get_prima_nota(db, utente_test.id)
    assert len(voci) == 0


def test_elimina_voce_altrui_non_rimuove(client_http, db, utente_test):
    """POST elimina voce di altro utente → redirect, voce intatta."""
    altro = _utente(db, "altro2@t.it")
    voce = _voce(db, altro.id, descrizione="Spesa privata")

    resp = client_http.post(
        f"/prima-nota/{voce.id}/elimina",
        data={"anno": str(anno_corrente), "mese": str(mese_corrente)},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    voci_altro = crud.get_prima_nota(db, altro.id)
    assert len(voci_altro) == 1


# ── GET /prima-nota/export.csv ────────────────────────────────────────────────

def test_export_csv_ritorna_csv(client_http, db, utente_test):
    """GET export.csv → 200 con content-type text/csv e dati nel body."""
    _voce(db, utente_test.id, descrizione="Riga test CSV", importo=120.0)

    resp = client_http.get(f"/prima-nota/export.csv?anno={anno_corrente}")

    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "Riga test CSV" in resp.text
    assert "-120.00" in resp.text  # uscita → valore negativo nel CSV


def test_export_csv_vuoto_ok(client_http, db, utente_test):
    """Export CSV senza voci → 200 con solo intestazione."""
    resp = client_http.get(f"/prima-nota/export.csv?anno={anno_corrente}")

    assert resp.status_code == 200
    assert "Data,Descrizione" in resp.text
