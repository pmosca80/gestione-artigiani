"""
Test permessi granulari collaboratore vs titolare.

Usa sessioni reali (login HTTP) perché is_collaboratore()/scope_collaboratore()
leggono request.session.get("user_id") direttamente, non la dependency
get_current_user (che in client_http è overridata e quindi non rifletterebbe
la differenza titolare/collaboratore).
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import get_db
from app.main import app
from app.security import hash_password

oggi = date.today()
oggi_str = str(oggi)


@pytest.fixture(autouse=True)
def patch_bcrypt(monkeypatch):
    """Bypassa bcrypt (incompatibile su Python 3.14 + bcrypt>=4)."""
    from passlib.context import CryptContext
    import app.security
    ctx = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    monkeypatch.setattr(app.security, "pwd_context", ctx)


@pytest.fixture
def client_sessione(db):
    """TestClient con sessioni reali (nessun override di get_current_user)."""
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _titolare(db, username="titolare@test.it", password="password123"):
    u = models.Utente(
        username=username, password=hash_password(password),
        data_registrazione=oggi_str, attivo=2, piano="pro",
        email_verificato=True, onboarding_done=True, ruolo="titolare",
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _collaboratore(db, titolare_id, username="collab@test.it", password="password123"):
    u = models.Utente(
        username=username, password=hash_password(password),
        data_registrazione=oggi_str, attivo=2, piano="free",
        titolare_id=titolare_id, ruolo="collaboratore",
        email_verificato=True, onboarding_done=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


_login_counter = [0]


def _login(client, username, password="password123"):
    # IP fittizio univoco per chiamata: evita di incappare nel rate limit
    # 5/minuto su /login (keyed per IP) con tanti login nello stesso test run.
    _login_counter[0] += 1
    n = _login_counter[0]
    ip = f"10.{(n // 256) % 256}.{n % 256}.1"
    resp = client.post(
        "/login", data={"username": username, "password": password},
        headers={"X-Forwarded-For": ip}, follow_redirects=False,
    )
    assert resp.status_code == 303, f"login fallito: {resp.text[:300]}"
    assert resp.headers["location"] == "/"
    return resp


def _cliente(db, utente_id, nome="Mario"):
    c = models.Cliente(
        utente_id=utente_id, tipo_cliente="privato", nome=nome, cognome="Rossi",
        data_creazione=oggi_str,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _lavoro(db, utente_id, cliente_id, titolo="Lavoro test", assegnato_a_id=None):
    l = models.Lavoro(
        utente_id=utente_id, cliente_id=cliente_id, titolo=titolo,
        data_lavoro=oggi, stato="in_corso", priorita="normale",
        importo_preventivato=1000.0, assegnato_a_id=assegnato_a_id,
        data_creazione=oggi_str,
    )
    db.add(l); db.commit(); db.refresh(l)
    return l


# ── Router interamente bloccati per il collaboratore ─────────────────────────

@pytest.mark.parametrize("path", [
    "/impostazioni/azienda",
    "/impostazioni/profilo",
    "/prima-nota/",
    "/fatture-acquisto/",
    "/export/",
    "/piani",
])
def test_collaboratore_bloccato_su_aree_riservate(client_sessione, db, path):
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    _login(client_sessione, "collab@test.it")

    resp = client_sessione.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert "area_riservata" in resp.headers["location"]


@pytest.mark.parametrize("path", [
    "/impostazioni/azienda",
    "/prima-nota/",
    "/fatture-acquisto/",
    "/export/",
    "/piani",
])
def test_titolare_non_bloccato_su_stesse_aree(client_sessione, db, path):
    tit = _titolare(db)
    _login(client_sessione, "titolare@test.it")

    resp = client_sessione.get(path, follow_redirects=False)
    assert resp.status_code == 200


def test_liquidazione_iva_bloccata_per_collaboratore(client_sessione, db):
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    _login(client_sessione, "collab@test.it")

    resp = client_sessione.get("/fatture/liquidazione-iva", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/fatture/"


# ── Scoping lavori ─────────────────────────────────────────────────────────────

def test_collaboratore_vede_solo_lavori_assegnati(client_sessione, db):
    tit = _titolare(db)
    collab = _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    mio = _lavoro(db, tit.id, cli.id, titolo="Lavoro mio", assegnato_a_id=collab.id)
    _lavoro(db, tit.id, cli.id, titolo="Lavoro altrui", assegnato_a_id=None)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.get("/lavori/")
    assert resp.status_code == 200
    assert "Lavoro mio" in resp.text
    assert "Lavoro altrui" not in resp.text


def test_titolare_vede_tutti_i_lavori(client_sessione, db):
    tit = _titolare(db)
    collab = _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    _lavoro(db, tit.id, cli.id, titolo="Lavoro A", assegnato_a_id=collab.id)
    _lavoro(db, tit.id, cli.id, titolo="Lavoro B", assegnato_a_id=None)

    _login(client_sessione, "titolare@test.it")
    resp = client_sessione.get("/lavori/")
    assert resp.status_code == 200
    assert "Lavoro A" in resp.text
    assert "Lavoro B" in resp.text


def test_collaboratore_404_su_lavoro_non_assegnato(client_sessione, db):
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    altrui = _lavoro(db, tit.id, cli.id, titolo="Non mio", assegnato_a_id=None)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.get(f"/lavori/{altrui.id}")
    assert resp.status_code == 404


def test_collaboratore_accede_a_lavoro_assegnato(client_sessione, db):
    tit = _titolare(db)
    collab = _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    mio = _lavoro(db, tit.id, cli.id, titolo="Mio lavoro", assegnato_a_id=collab.id)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.get(f"/lavori/{mio.id}")
    assert resp.status_code == 200


def test_collaboratore_crea_lavoro_si_auto_assegna(client_sessione, db):
    tit = _titolare(db)
    collab = _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.post(
        f"/lavori/nuovo/{cli.id}",
        data={
            "data_lavoro": oggi_str, "titolo": "Creato da collab",
            "stato": "preventivo", "aliquota_iva": "22", "sconto": "0",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    nuovo = db.query(models.Lavoro).filter(models.Lavoro.titolo == "Creato da collab").first()
    assert nuovo is not None
    assert nuovo.assegnato_a_id == collab.id


def test_collaboratore_non_puo_agire_su_lavoro_altrui_via_url(client_sessione, db):
    """IDOR: anche conoscendo l'ID, il collaboratore non può agire su un lavoro non suo."""
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    altrui = _lavoro(db, tit.id, cli.id, titolo="Non mio", assegnato_a_id=None)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.post(f"/lavori/{altrui.id}/timer/inizia", follow_redirects=False)
    assert resp.status_code == 404


# ── Scoping clienti ────────────────────────────────────────────────────────────

def test_collaboratore_vede_cliente_con_lavoro_assegnato(client_sessione, db):
    tit = _titolare(db)
    collab = _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id, nome="ClienteAssegnato")
    _lavoro(db, tit.id, cli.id, assegnato_a_id=collab.id)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.get(f"/clienti/{cli.id}")
    assert resp.status_code == 200


def test_collaboratore_non_vede_cliente_di_altro_collaboratore(client_sessione, db):
    tit = _titolare(db)
    collab1 = _collaboratore(db, tit.id, username="collab1@test.it")
    collab2 = _collaboratore(db, tit.id, username="collab2@test.it")
    cli = _cliente(db, tit.id, nome="ClienteDiCollab2")
    _lavoro(db, tit.id, cli.id, assegnato_a_id=collab2.id)

    _login(client_sessione, "collab1@test.it")
    resp = client_sessione.get(f"/clienti/{cli.id}")
    assert resp.status_code == 404


def test_collaboratore_vede_cliente_senza_lavori(client_sessione, db):
    """Cliente non ancora 'reclamato' da nessun lavoro è visibile a tutti i collaboratori."""
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id, nome="ClienteNuovo")

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.get(f"/clienti/{cli.id}")
    assert resp.status_code == 200


# ── Scoping fatture ──────────────────────────────────────────────────────────

def test_collaboratore_non_elimina_rapportino_su_lavoro_altrui(client_sessione, db):
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    altrui = _lavoro(db, tit.id, cli.id, titolo="Non mio", assegnato_a_id=None)
    rapportino = models.RapportinoLavoro(
        utente_id=tit.id, lavoro_id=altrui.id, data=oggi_str,
        ore_lavorate=2, descrizione_attivita="Test", data_creazione=oggi_str,
    )
    db.add(rapportino); db.commit(); db.refresh(rapportino)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.post(
        f"/lavori/{altrui.id}/rapportini/{rapportino.id}/elimina", follow_redirects=False,
    )
    assert resp.status_code == 404
    assert db.query(models.RapportinoLavoro).filter_by(id=rapportino.id).first() is not None


def test_collaboratore_non_elimina_sal_su_lavoro_altrui(client_sessione, db):
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    altrui = _lavoro(db, tit.id, cli.id, titolo="Non mio", assegnato_a_id=None)
    sal = models.SalLavoro(
        utente_id=tit.id, lavoro_id=altrui.id, numero=1, data=oggi_str,
        percentuale=50, importo_richiesto=500, data_creazione=oggi_str,
    )
    db.add(sal); db.commit(); db.refresh(sal)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.post(
        f"/lavori/{altrui.id}/sal/{sal.id}/elimina", follow_redirects=False,
    )
    assert resp.status_code == 404
    resp2 = client_sessione.post(
        f"/lavori/{altrui.id}/sal/{sal.id}/stato", follow_redirects=False,
    )
    assert resp2.status_code == 404
    assert db.query(models.SalLavoro).filter_by(id=sal.id).first() is not None


def test_collaboratore_non_elimina_timesheet_su_lavoro_altrui(client_sessione, db):
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    altrui = _lavoro(db, tit.id, cli.id, titolo="Non mio", assegnato_a_id=None)
    entry = models.TimesheetCollab(
        utente_id=tit.id, lavoro_id=altrui.id, nome_operaio="Mario",
        data=oggi_str, ore=4, costo_orario=15, data_creazione=oggi_str,
    )
    db.add(entry); db.commit(); db.refresh(entry)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.post(
        f"/lavori/{altrui.id}/timesheet/{entry.id}/elimina", follow_redirects=False,
    )
    assert resp.status_code == 404
    assert db.query(models.TimesheetCollab).filter_by(id=entry.id).first() is not None


def test_collaboratore_non_modifica_fattura_su_lavoro_altrui(client_sessione, db):
    """IDOR: un collaboratore non può cambiare stato/inviare una fattura di un lavoro non suo."""
    tit = _titolare(db)
    _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    altrui = _lavoro(db, tit.id, cli.id, titolo="Non mio", assegnato_a_id=None)
    fattura = models.FatturaEmessa(
        utente_id=tit.id, lavoro_id=altrui.id, numero=1, anno=oggi.year,
        data_emissione=oggi_str, importo_imponibile=100, importo_iva=22,
        importo_totale=122, nome_file="f1.xml", data_creazione=oggi_str, stato="emessa",
    )
    db.add(fattura); db.commit(); db.refresh(fattura)

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.post(
        f"/fatture/{fattura.id}/stato", data={"stato": "pagata"}, follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "errore=fattura_non_trovata" in resp.headers["location"]
    db.refresh(fattura)
    assert fattura.stato == "emessa"


def test_collaboratore_vede_solo_fatture_dei_propri_lavori(client_sessione, db):
    tit = _titolare(db)
    collab = _collaboratore(db, tit.id)
    cli = _cliente(db, tit.id)
    mio = _lavoro(db, tit.id, cli.id, titolo="Lavoro fatturato mio", assegnato_a_id=collab.id)
    altrui = _lavoro(db, tit.id, cli.id, titolo="Lavoro fatturato altrui", assegnato_a_id=None)

    db.add(models.FatturaEmessa(
        utente_id=tit.id, lavoro_id=mio.id, numero=1, anno=oggi.year,
        data_emissione=oggi_str, importo_imponibile=100, importo_iva=22,
        importo_totale=122, nome_file="f1.xml", data_creazione=oggi_str,
    ))
    db.add(models.FatturaEmessa(
        utente_id=tit.id, lavoro_id=altrui.id, numero=2, anno=oggi.year,
        data_emissione=oggi_str, importo_imponibile=200, importo_iva=44,
        importo_totale=244, nome_file="f2.xml", data_creazione=oggi_str,
    ))
    db.commit()

    _login(client_sessione, "collab@test.it")
    resp = client_sessione.get("/fatture/")
    assert resp.status_code == 200
    assert "f1.xml" in resp.text or "122" in resp.text
    assert "f2.xml" not in resp.text
