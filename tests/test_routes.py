"""
Test HTTP per le route principali.
Usa client_http (TestClient con get_current_user e get_db sostituiti).
Verifica: status code, isolamento dati, redirect post-form.
"""
from datetime import date
from app import models


def test_health_check(client_http):
    """/health deve rispondere senza sessione e senza dipendere dal DB."""
    resp = client_http.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── /clienti/ ────────────────────────────────────────────────────────────────

def test_lista_clienti_vuota(client_http):
    resp = client_http.get("/clienti/")
    assert resp.status_code == 200


def test_lista_clienti_vuota_senza_ricerca_invita_a_creare(client_http):
    """Regressione: con zero clienti e nessuna ricerca attiva, lo stato
    vuoto deve invitare a creare il primo cliente."""
    resp = client_http.get("/clienti/")
    assert resp.status_code == 200
    assert "Non hai ancora nessun cliente" in resp.text
    assert "Aggiungi il primo cliente" in resp.text


def test_lista_clienti_con_ricerca_senza_risultati_mostra_reset(client_http, db, utente_test):
    """Regressione: se esiste già almeno un cliente ma la ricerca non
    trova corrispondenze, il messaggio non deve invitare a creare il
    primo cliente (ce ne sono già) ma a resettare la ricerca."""
    db.add(models.Cliente(
        utente_id=utente_test.id,
        tipo_cliente="privato",
        nome="Mario",
        cognome="Rossi",
        data_creazione=str(date.today()),
    ))
    db.commit()

    resp = client_http.get("/clienti/?cerca=parola-che-non-esiste-mai")
    assert resp.status_code == 200
    assert "Reset ricerca" in resp.text
    assert "Non hai ancora nessun cliente" not in resp.text


def test_lista_clienti_mostra_solo_propri(client_http, db, utente_test):
    """Cliente di un altro utente non deve apparire nella lista."""
    altro = models.Utente(
        username="altro2@example.com",
        password="x",
        attivo=1,
        onboarding_done=True,
        data_registrazione=str(date.today()),
    )
    db.add(altro)
    db.commit()

    db.add(models.Cliente(
        utente_id=altro.id,
        tipo_cliente="privato",
        nome="Utente Altrui",
        cognome="Segreto",
        data_creazione=str(date.today()),
    ))
    db.add(models.Cliente(
        utente_id=utente_test.id,
        tipo_cliente="privato",
        nome="Cliente Mio",
        cognome="Visibile",
        data_creazione=str(date.today()),
    ))
    db.commit()

    resp = client_http.get("/clienti/")

    assert resp.status_code == 200
    assert "Cliente Mio" in resp.text
    assert "Utente Altrui" not in resp.text


def test_crea_cliente(client_http):
    resp = client_http.post("/clienti/nuovo", data={
        "tipo_cliente": "privato",
        "nome": "Luigi",
        "cognome": "Bianchi",
        "telefono": "3339876543",
    }, follow_redirects=False)

    assert resp.status_code in (302, 303)
    assert "toast=Cliente%20salvato" in resp.headers["location"]


def test_cliente_inesistente_404(client_http):
    resp = client_http.get("/clienti/999999")
    assert resp.status_code == 404


# ── /lavori/ ─────────────────────────────────────────────────────────────────

def test_lista_lavori_vuota(client_http):
    resp = client_http.get("/lavori/")
    assert resp.status_code == 200


def test_lavoro_altrui_404(client_http, db):
    """GET /lavori/<id> di un altro utente deve restituire 404."""
    altro = models.Utente(
        username="altro3@example.com",
        password="x",
        attivo=1,
        onboarding_done=True,
        data_registrazione=str(date.today()),
    )
    db.add(altro)
    db.commit()

    cli = models.Cliente(
        utente_id=altro.id,
        tipo_cliente="privato",
        nome="X",
        cognome="Y",
        data_creazione=str(date.today()),
    )
    db.add(cli)
    db.commit()

    lavoro = models.Lavoro(
        utente_id=altro.id,
        cliente_id=cli.id,
        titolo="Lavoro segreto",
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        data_creazione=str(date.today()),
    )
    db.add(lavoro)
    db.commit()

    resp = client_http.get(f"/lavori/{lavoro.id}")
    assert resp.status_code == 404


def test_lavoro_dettaglio(client_http, lavoro_test):
    """GET /lavori/<id> di un lavoro proprio restituisce 200."""
    resp = client_http.get(f"/lavori/{lavoro_test.id}")
    assert resp.status_code == 200
    assert lavoro_test.titolo in resp.text


# ── /scadenzario/manutenzioni ────────────────────────────────────────────────

def test_lista_promemoria(client_http):
    resp = client_http.get("/scadenzario/manutenzioni")
    assert resp.status_code == 200


def test_crea_promemoria(client_http):
    resp = client_http.post("/scadenzario/manutenzioni/nuovo", data={
        "titolo": "Revisione caldaia Sig. Bianchi",
        "data_promemoria": str(date.today()),
        "tipo": "manutenzione",
        "cliente_id": "",
        "note": "",
    }, follow_redirects=False)

    assert resp.status_code in (302, 303)


# ── /lavori/ — eliminazione ───────────────────────────────────────────────────

def test_elimina_lavoro_proprio(client_http, lavoro_test):
    """DELETE di un lavoro proprio deve riuscire (redirect 303)."""
    resp = client_http.post(f"/lavori/{lavoro_test.id}/elimina", follow_redirects=False)
    assert resp.status_code == 303


def test_elimina_lavoro_altrui_404(client_http, db):
    """DELETE di un lavoro di un altro utente deve restituire 404."""
    altro = models.Utente(
        username="altro_del@example.com",
        password="x",
        attivo=1,
        onboarding_done=True,
        data_registrazione=str(date.today()),
    )
    db.add(altro)
    db.commit()

    cli = models.Cliente(
        utente_id=altro.id,
        tipo_cliente="privato",
        nome="A",
        cognome="B",
        data_creazione=str(date.today()),
    )
    db.add(cli)
    db.commit()

    lav = models.Lavoro(
        utente_id=altro.id,
        cliente_id=cli.id,
        titolo="Lavoro altrui da non eliminare",
        data_lavoro=date.today(),
        stato="in_corso",
        priorita="normale",
        data_creazione=str(date.today()),
    )
    db.add(lav)
    db.commit()

    resp = client_http.post(f"/lavori/{lav.id}/elimina", follow_redirects=False)
    assert resp.status_code == 404


# ── /materiali/ ───────────────────────────────────────────────────────────────

def test_lista_materiali(client_http):
    resp = client_http.get("/materiali/")
    assert resp.status_code == 200
