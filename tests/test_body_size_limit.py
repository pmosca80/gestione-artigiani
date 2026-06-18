"""Il middleware limit_body_size (app/main.py) deve lasciare passare upload
realistici (foto/allegati, qualche MB) e bloccare solo payload abnormi.

Regressione: il limite era impostato a 512 KB, sotto la dimensione di una
qualunque foto scattata con un telefono — bloccava di fatto l'upload foto
sui lavori prima ancora che la richiesta raggiungesse la route."""


def test_payload_da_pochi_mb_non_bloccato(client_http):
    """Una foto tipica (qui simulata, 2MB) deve superare il middleware:
    la risposta non deve essere 413, qualunque sia l'esito applicativo."""
    payload = b"x" * (2 * 1024 * 1024)
    resp = client_http.post("/lavori/1/foto", content=payload)
    assert resp.status_code != 413


def test_payload_eccessivo_bloccato(client_http):
    """Un payload molto oltre qualunque upload legittimo deve restare bloccato."""
    payload = b"x" * (20 * 1024 * 1024)
    resp = client_http.post("/lavori/1/foto", content=payload)
    assert resp.status_code == 413
