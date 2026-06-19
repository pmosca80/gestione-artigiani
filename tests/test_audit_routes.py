"""Test per /audit/ (app/routes/audit.py) — unico file di route senza copertura."""
from datetime import date

from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.dependencies import get_current_user
from app.main import app

oggi_str = str(date.today())


def _voce_audit(db, utente_id, attore_id=None, attore_username="mario", azione="crea_lavoro",
                 tabella="lavori", record_id=1, ip="1.2.3.4"):
    v = models.AuditLog(
        timestamp=oggi_str,
        utente_id=utente_id,
        attore_id=attore_id if attore_id is not None else utente_id,
        attore_username=attore_username,
        azione=azione,
        tabella=tabella,
        record_id=record_id,
        dettaglio='{"chiave": "valore"}',
        ip=ip,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _client_come(db, utente_id):
    """TestClient con get_current_user forzato su un utente specifico."""
    def _db():
        yield db

    def _user():
        return utente_id

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    client = TestClient(app, raise_server_exceptions=True)
    return client


def test_lista_audit_mostra_solo_i_propri_eventi(client_http, db, utente_test):
    """Un titolare non deve vedere gli eventi di audit di un altro utente."""
    altro = models.Utente(username="altro@example.com", password="x", attivo=1)
    db.add(altro)
    db.commit()

    _voce_audit(db, utente_test.id, azione="crea_lavoro", tabella="lavori")
    _voce_audit(db, altro.id, azione="emette_fattura", tabella="fatture_emesse")

    resp = client_http.get("/audit/")
    assert resp.status_code == 200
    assert ">1 eventi<" in resp.text


def test_lista_audit_filtro_tabella(client_http, db, utente_test):
    _voce_audit(db, utente_test.id, azione="crea_lavoro", tabella="lavori")
    _voce_audit(db, utente_test.id, azione="emette_fattura", tabella="fatture_emesse")

    resp = client_http.get("/audit/", params={"tabella": "fatture_emesse"})
    assert resp.status_code == 200
    assert ">1 eventi<" in resp.text


def test_lista_audit_filtro_azione(client_http, db, utente_test):
    _voce_audit(db, utente_test.id, azione="crea_lavoro", tabella="lavori")
    _voce_audit(db, utente_test.id, azione="modifica_lavoro", tabella="lavori")

    resp = client_http.get("/audit/", params={"azione": "modifica_lavoro"})
    assert resp.status_code == 200
    assert ">1 eventi<" in resp.text


def test_lista_audit_filtro_attore(client_http, db, utente_test):
    _voce_audit(db, utente_test.id, attore_username="mario.rossi", azione="crea_lavoro")
    _voce_audit(db, utente_test.id, attore_username="luigi.bianchi", azione="crea_lavoro")

    resp = client_http.get("/audit/", params={"attore": "luigi"})
    assert resp.status_code == 200
    assert ">1 eventi<" in resp.text
    assert "luigi.bianchi" in resp.text
    assert "mario.rossi" not in resp.text


def test_collaboratore_non_accede_ad_audit(db, utente_test):
    """Un collaboratore (titolare_id impostato) viene rimandato alla home,
    non vede l'audit log del proprio titolare."""
    collaboratore = models.Utente(
        username="collab@example.com", password="x", attivo=1,
        titolare_id=utente_test.id, ruolo="collaboratore",
    )
    db.add(collaboratore)
    db.commit()

    client = _client_come(db, collaboratore.id)
    try:
        resp = client.get("/audit/", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_lista_audit_dettaglio_json_decodificato(client_http, db, utente_test):
    """Il campo dettaglio (JSON in Text) deve arrivare in pagina come dato
    leggibile, senza far fallire la route se il JSON è malformato."""
    _voce_audit(db, utente_test.id, azione="crea_lavoro")
    v = models.AuditLog(
        timestamp=oggi_str, utente_id=utente_test.id, attore_id=utente_test.id,
        attore_username="mario", azione="crea_lavoro", tabella="lavori",
        dettaglio="non-e-json-valido",
    )
    db.add(v)
    db.commit()

    resp = client_http.get("/audit/")
    assert resp.status_code == 200
