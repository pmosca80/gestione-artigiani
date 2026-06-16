"""
Test HTTP per le route /scadenzario/*.

Copre: lista, filtro attivi/tutti, creazione (con e senza cliente),
toggle completa, eliminazione (propria e altrui), isolamento multi-tenant.
"""
from datetime import date, timedelta

import pytest

from app import models, crud

oggi = date.today()
oggi_str = str(oggi)
domani_str = str(oggi + timedelta(days=1))


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username):
    u = models.Utente(
        username=username, password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _promemoria(db, utente_id, titolo="Revisione caldaia", stato="attivo"):
    p = crud.crea_promemoria(
        db, utente_id,
        titolo=titolo,
        data_promemoria=domani_str,
        tipo="manutenzione",
        note="",
    )
    if stato != "attivo":
        p.stato = stato
        db.commit(); db.refresh(p)
    return p


# ── GET /scadenzario/manutenzioni ─────────────────────────────────────────────

def test_lista_manutenzioni_ok(client_http):
    """GET /scadenzario/manutenzioni → 200."""
    resp = client_http.get("/scadenzario/manutenzioni")
    assert resp.status_code == 200


def test_lista_mostra_solo_propri(client_http, db, utente_test):
    """Lista filtra per utente → promemoria altrui non appaiono."""
    altro = _utente(db, "altro1@t.it")
    _promemoria(db, utente_test.id, titolo="Boiler proprio XYZ")
    _promemoria(db, altro.id, titolo="Boiler altrui ABC")

    resp = client_http.get("/scadenzario/manutenzioni")
    assert resp.status_code == 200
    assert "Boiler proprio XYZ" in resp.text
    assert "Boiler altrui ABC" not in resp.text


# ── POST /scadenzario/manutenzioni/nuovo ──────────────────────────────────────

def test_crea_promemoria_happy_path(client_http, db, utente_test):
    """POST nuovo → promemoria in DB, redirect a /scadenzario/manutenzioni."""
    resp = client_http.post(
        "/scadenzario/manutenzioni/nuovo",
        data={
            "titolo": "Controllo impianto gas",
            "data_promemoria": domani_str,
            "tipo": "revisione",
            "note": "",
            "cliente_id": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/scadenzario/manutenzioni" in resp.headers["location"]

    promemoria = crud.get_promemoria(db, utente_test.id)
    assert len(promemoria) == 1
    assert promemoria[0].titolo == "Controllo impianto gas"
    assert promemoria[0].tipo == "revisione"
    assert promemoria[0].stato == "attivo"


def test_crea_promemoria_con_cliente(client_http, db, utente_test, cliente_test):
    """POST nuovo con cliente_id → promemoria.cliente_id impostato."""
    client_http.post(
        "/scadenzario/manutenzioni/nuovo",
        data={
            "titolo": "Assistenza cliente",
            "data_promemoria": domani_str,
            "tipo": "chiamata",
            "note": "urgente",
            "cliente_id": str(cliente_test.id),
        },
        follow_redirects=False,
    )

    promemoria = crud.get_promemoria(db, utente_test.id)
    assert len(promemoria) == 1
    assert promemoria[0].cliente_id == cliente_test.id


# ── Filtro attivi/tutti ───────────────────────────────────────────────────────

def test_filtro_attivi_esclude_completati(client_http, db, utente_test):
    """GET ?filtro=attivi → promemoria con stato=completato non appare."""
    _promemoria(db, utente_test.id, titolo="Task attiva AAA")
    _promemoria(db, utente_test.id, titolo="Task completata BBB", stato="completato")

    resp = client_http.get("/scadenzario/manutenzioni?filtro=attivi")
    assert resp.status_code == 200
    assert "Task attiva AAA" in resp.text
    assert "Task completata BBB" not in resp.text


def test_filtro_tutti_mostra_completati(client_http, db, utente_test):
    """GET ?filtro=tutti → promemoria completato appare."""
    _promemoria(db, utente_test.id, titolo="Task completata CCC", stato="completato")

    resp = client_http.get("/scadenzario/manutenzioni?filtro=tutti")
    assert resp.status_code == 200
    assert "Task completata CCC" in resp.text


# ── POST /scadenzario/manutenzioni/{id}/completa ──────────────────────────────

def test_completa_promemoria(client_http, db, utente_test):
    """POST /completa → stato diventa 'completato', redirect."""
    p = _promemoria(db, utente_test.id)

    resp = client_http.post(
        f"/scadenzario/manutenzioni/{p.id}/completa",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(p)
    assert p.stato == "completato"


def test_completa_promemoria_toggle(client_http, db, utente_test):
    """POST /completa due volte → stato torna 'attivo'."""
    p = _promemoria(db, utente_test.id)

    client_http.post(f"/scadenzario/manutenzioni/{p.id}/completa", follow_redirects=False)
    client_http.post(f"/scadenzario/manutenzioni/{p.id}/completa", follow_redirects=False)

    db.refresh(p)
    assert p.stato == "attivo"


def test_completa_promemoria_altrui_no_effetto(client_http, db, utente_test):
    """POST /completa su promemoria altrui → redirect silenzioso, stato invariato."""
    altro = _utente(db, "altro2@t.it")
    p = _promemoria(db, altro.id, titolo="Task altrui")

    resp = client_http.post(
        f"/scadenzario/manutenzioni/{p.id}/completa",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    db.refresh(p)
    assert p.stato == "attivo"


# ── POST /scadenzario/manutenzioni/{id}/elimina ───────────────────────────────

def test_elimina_promemoria_proprio(client_http, db, utente_test):
    """POST elimina → promemoria rimosso dal DB."""
    p = _promemoria(db, utente_test.id)

    resp = client_http.post(
        f"/scadenzario/manutenzioni/{p.id}/elimina",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    promemoria = crud.get_promemoria(db, utente_test.id)
    assert len(promemoria) == 0


def test_elimina_promemoria_altrui_no_effetto(client_http, db, utente_test):
    """POST elimina promemoria altrui → redirect, promemoria intatto."""
    altro = _utente(db, "altro3@t.it")
    p = _promemoria(db, altro.id)

    resp = client_http.post(
        f"/scadenzario/manutenzioni/{p.id}/elimina",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    promemoria_altro = crud.get_promemoria(db, altro.id)
    assert len(promemoria_altro) == 1
