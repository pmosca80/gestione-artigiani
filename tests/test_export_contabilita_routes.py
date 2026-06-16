"""
Test HTTP per le route /export/*.

Copre: hub export (gate piano), export XML riepilogo contabilità con
fatture e prima nota, gate piano free → redirect, parametro ?anno.
"""
from datetime import date
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app import models, crud
from app.database import get_db
from app.dependencies import get_current_user
from app.main import app

oggi_str = str(date.today())
anno_corrente = date.today().year


# ── Helper di setup ───────────────────────────────────────────────────────────

def _utente(db, username, piano="pro"):
    u = models.Utente(
        username=username, password="x", piano=piano,
        attivo=2, onboarding_done=True, data_registrazione=oggi_str,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _voce_pn(db, utente_id, descrizione="Acquisto materiale", importo=100.0, tipo="uscita"):
    return crud.crea_voce_prima_nota(
        db, utente_id,
        data=oggi_str,
        descrizione=descrizione,
        importo=importo,
        tipo=tipo,
        categoria="varie",
    )


# ── GET /export/ (hub) ────────────────────────────────────────────────────────

def test_export_hub_ok(client_http):
    """GET /export/ con piano=pro → 200."""
    resp = client_http.get("/export/")
    assert resp.status_code == 200


def test_export_hub_piano_free_redirect(db):
    """GET /export/ con piano=free → redirect a /piani?upgrade=export."""
    u_free = _utente(db, "free1@t.it", piano="free")

    def _db(): yield db
    def _user(): return u_free.id
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user

    with TestClient(app, raise_server_exceptions=True) as c:
        resp = c.get("/export/", follow_redirects=False)

    app.dependency_overrides.clear()

    assert resp.status_code == 303
    assert "/piani" in resp.headers["location"]


# ── GET /export/riepilogo.xml ─────────────────────────────────────────────────

def test_export_xml_ok(client_http):
    """GET /export/riepilogo.xml → 200 con content-type application/xml."""
    resp = client_http.get("/export/riepilogo.xml")
    assert resp.status_code == 200
    assert "xml" in resp.headers["content-type"]


def test_export_xml_piano_free_redirect(db):
    """GET /export/riepilogo.xml con piano=free → redirect a /piani."""
    u_free = _utente(db, "free2@t.it", piano="free")

    def _db(): yield db
    def _user(): return u_free.id
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user

    with TestClient(app, raise_server_exceptions=True) as c:
        resp = c.get("/export/riepilogo.xml", follow_redirects=False)

    app.dependency_overrides.clear()

    assert resp.status_code == 303
    assert "/piani" in resp.headers["location"]


def test_export_xml_struttura_base(client_http):
    """XML contiene elementi Contabilita, Fatture e PrimaNota."""
    resp = client_http.get("/export/riepilogo.xml")
    assert resp.status_code == 200

    root = ET.fromstring(resp.content)
    assert root.tag == "Contabilita"
    assert root.find("Fatture") is not None
    assert root.find("PrimaNota") is not None


def test_export_xml_anno_param(client_http):
    """GET ?anno=2024 → attributo anno='2024' nell'elemento radice."""
    resp = client_http.get("/export/riepilogo.xml?anno=2024")
    assert resp.status_code == 200

    root = ET.fromstring(resp.content)
    assert root.get("anno") == "2024"


def test_export_xml_prima_nota_totali(client_http, db, utente_test):
    """XML prima nota riflette somma entrate e uscite create in DB."""
    _voce_pn(db, utente_test.id, descrizione="Entrata A", importo=200.0, tipo="entrata")
    _voce_pn(db, utente_test.id, descrizione="Uscita B", importo=80.0, tipo="uscita")

    resp = client_http.get(f"/export/riepilogo.xml?anno={anno_corrente}")
    assert resp.status_code == 200

    root = ET.fromstring(resp.content)
    pn = root.find("PrimaNota")
    assert pn is not None
    assert float(pn.get("totale_entrate")) == 200.0
    assert float(pn.get("totale_uscite")) == 80.0
    assert float(pn.get("saldo")) == 120.0


def test_export_xml_prima_nota_voci_nel_xml(client_http, db, utente_test):
    """Ogni voce prima nota compare come elemento Voce nel XML."""
    _voce_pn(db, utente_test.id, descrizione="Gasolio furgone", importo=60.0, tipo="uscita")

    resp = client_http.get(f"/export/riepilogo.xml?anno={anno_corrente}")
    root = ET.fromstring(resp.content)

    voci = root.findall(".//Voce")
    assert len(voci) == 1
    assert voci[0].get("descrizione") == "Gasolio furgone"
    assert voci[0].get("tipo") == "uscita"
    assert float(voci[0].get("importo")) == 60.0
