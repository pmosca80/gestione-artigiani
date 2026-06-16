"""
Test HTTP per le route /preventivi/template/*.

Copre: lista, form nuovo, creazione, form modifica (proprio e altrui),
modifica (propria e altrui), eliminazione (propria e altrui), multi-tenant.
"""
from datetime import date

import pytest

from app import models, crud

oggi_str = str(date.today())


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username):
    u = models.Utente(
        username=username, password="x", piano="pro",
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _template(db, utente_id, nome="Manutenzione base"):
    return crud.crea_template_preventivo(
        db, utente_id,
        nome=nome,
        titolo="Intervento di manutenzione",
        descrizione="Descrizione standard",
        importo_preventivato=500.0,
        aliquota_iva=22.0,
        sconto=0.0,
        note_consuntivo="",
    )


# ── GET /preventivi/template/ ─────────────────────────────────────────────────

def test_lista_template_ok(client_http):
    """GET /preventivi/template/ → 200."""
    resp = client_http.get("/preventivi/template/")
    assert resp.status_code == 200


def test_lista_mostra_solo_propri(client_http, db, utente_test):
    """Lista filtra per utente → template altrui non appaiono."""
    altro = _utente(db, "altro1@t.it")
    _template(db, utente_test.id, nome="Template proprio XYZ")
    _template(db, altro.id, nome="Template altrui ABC")

    resp = client_http.get("/preventivi/template/")
    assert resp.status_code == 200
    assert "Template proprio XYZ" in resp.text
    assert "Template altrui ABC" not in resp.text


# ── GET /preventivi/template/nuovo ────────────────────────────────────────────

def test_form_nuovo_template_ok(client_http):
    """GET /preventivi/template/nuovo → 200."""
    resp = client_http.get("/preventivi/template/nuovo")
    assert resp.status_code == 200


# ── POST /preventivi/template/nuovo ───────────────────────────────────────────

def test_crea_template_happy_path(client_http, db, utente_test):
    """POST nuovo → template in DB, redirect a /preventivi/template/."""
    resp = client_http.post(
        "/preventivi/template/nuovo",
        data={
            "nome": "Caldaia standard",
            "titolo": "Sostituzione caldaia murale",
            "descrizione": "Rimozione vecchia caldaia e installazione nuova",
            "importo_preventivato": "1200.00",
            "aliquota_iva": "22",
            "sconto": "5",
            "note_consuntivo": "Verificare collaudo",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/preventivi/template/" in resp.headers["location"]

    tmpl = crud.get_template_preventivi(db, utente_test.id)
    assert len(tmpl) == 1
    assert tmpl[0].nome == "Caldaia standard"
    assert tmpl[0].importo_preventivato == 1200.0
    assert tmpl[0].sconto == 5.0
    assert tmpl[0].utente_id == utente_test.id


def test_crea_template_valori_iva_sconto(client_http, db, utente_test):
    """POST con aliquota IVA e sconto → salvati correttamente in DB."""
    client_http.post(
        "/preventivi/template/nuovo",
        data={
            "nome": "Pronto intervento",
            "titolo": "",
            "descrizione": "",
            "importo_preventivato": "300",
            "aliquota_iva": "10",
            "sconto": "0",
            "note_consuntivo": "",
        },
        follow_redirects=False,
    )

    tmpl = crud.get_template_preventivi(db, utente_test.id)
    assert len(tmpl) == 1
    assert tmpl[0].aliquota_iva == 10.0


# ── GET /preventivi/template/{id}/modifica ────────────────────────────────────

def test_form_modifica_template_proprio_ok(client_http, db, utente_test):
    """GET /{id}/modifica template proprio → 200."""
    t = _template(db, utente_test.id)

    resp = client_http.get(f"/preventivi/template/{t.id}/modifica")
    assert resp.status_code == 200


def test_form_modifica_template_altrui_redirect(client_http, db, utente_test):
    """GET /{id}/modifica template altrui → redirect a /preventivi/template/."""
    altro = _utente(db, "altro2@t.it")
    t = _template(db, altro.id)

    resp = client_http.get(f"/preventivi/template/{t.id}/modifica", follow_redirects=False)
    assert resp.status_code == 303
    assert "/preventivi/template/" in resp.headers["location"]


# ── POST /preventivi/template/{id}/modifica ───────────────────────────────────

def test_modifica_template_proprio(client_http, db, utente_test):
    """POST /{id}/modifica → campi aggiornati in DB."""
    t = _template(db, utente_test.id)

    client_http.post(
        f"/preventivi/template/{t.id}/modifica",
        data={
            "nome": "Manutenzione avanzata",
            "titolo": "Intervento completo",
            "descrizione": "Nuovo testo descrizione",
            "importo_preventivato": "800.00",
            "aliquota_iva": "22",
            "sconto": "10",
            "note_consuntivo": "Note aggiornate",
        },
        follow_redirects=False,
    )

    db.refresh(t)
    assert t.nome == "Manutenzione avanzata"
    assert t.importo_preventivato == 800.0
    assert t.sconto == 10.0


def test_modifica_template_altrui_no_effetto(client_http, db, utente_test):
    """POST modifica template altrui → nome invariato."""
    altro = _utente(db, "altro3@t.it")
    t = _template(db, altro.id, nome="Originale DEF")

    client_http.post(
        f"/preventivi/template/{t.id}/modifica",
        data={
            "nome": "Alterato GHI",
            "titolo": "",
            "descrizione": "",
            "importo_preventivato": "0",
            "aliquota_iva": "22",
            "sconto": "0",
            "note_consuntivo": "",
        },
        follow_redirects=False,
    )

    db.refresh(t)
    assert t.nome == "Originale DEF"


# ── POST /preventivi/template/{id}/elimina ────────────────────────────────────

def test_elimina_template_proprio(client_http, db, utente_test):
    """POST /{id}/elimina → template rimosso dal DB."""
    t = _template(db, utente_test.id)

    resp = client_http.post(
        f"/preventivi/template/{t.id}/elimina",
        follow_redirects=False,
    )
    assert resp.status_code == 303

    tmpl = crud.get_template_preventivi(db, utente_test.id)
    assert len(tmpl) == 0


def test_elimina_template_altrui_no_effetto(client_http, db, utente_test):
    """POST elimina template altrui → redirect, template intatto."""
    altro = _utente(db, "altro4@t.it")
    t = _template(db, altro.id)

    client_http.post(f"/preventivi/template/{t.id}/elimina", follow_redirects=False)

    tmpl_altro = crud.get_template_preventivi(db, altro.id)
    assert len(tmpl_altro) == 1
