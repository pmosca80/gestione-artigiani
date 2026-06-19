"""Test per app/services/cloudinary_service.py.

Nessuna chiamata di rete reale: cloudinary.uploader è mockato. Il punto più
delicato è la regex che estrae il public_id dall'URL per le cancellazioni —
un public_id sbagliato cancella il file sbagliato (o nessuno) su Cloudinary,
senza che la route che chiama elimina_immagine/elimina_file se ne accorga.
"""
from unittest.mock import MagicMock, patch

from app.services import cloudinary_service as svc


# ── cloudinary_configurato ───────────────────────────────────────────────────

def test_non_configurato_se_env_assente(monkeypatch):
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)
    assert svc.cloudinary_configurato() is False


def test_configurato_se_env_presente(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key:secret@cloud")
    assert svc.cloudinary_configurato() is True


# ── carica_immagine / carica_file ────────────────────────────────────────────

def test_carica_immagine_ritorna_secure_url():
    mock_upload = MagicMock(return_value={"secure_url": "https://res.cloudinary.com/demo/image/upload/v1/lavori/foto.jpg"})
    with patch("cloudinary.uploader.upload", mock_upload):
        url = svc.carica_immagine(b"contenuto-finto", "foto.jpg")

    assert url == "https://res.cloudinary.com/demo/image/upload/v1/lavori/foto.jpg"
    _, kwargs = mock_upload.call_args
    assert kwargs["resource_type"] == "image"
    assert kwargs["folder"] == "lavori"


def test_carica_immagine_usa_folder_personalizzato():
    mock_upload = MagicMock(return_value={"secure_url": "https://res.cloudinary.com/x"})
    with patch("cloudinary.uploader.upload", mock_upload):
        svc.carica_immagine(b"x", "foto.jpg", folder="loghi")

    _, kwargs = mock_upload.call_args
    assert kwargs["folder"] == "loghi"


def test_carica_file_resource_type_auto():
    mock_upload = MagicMock(return_value={"secure_url": "https://res.cloudinary.com/demo/raw/upload/v1/allegati/doc.pdf"})
    with patch("cloudinary.uploader.upload", mock_upload):
        url = svc.carica_file(b"contenuto-finto", "doc.pdf")

    assert url.endswith("doc.pdf")
    _, kwargs = mock_upload.call_args
    assert kwargs["resource_type"] == "auto"
    assert kwargs["folder"] == "allegati"


# ── elimina_immagine / elimina_file (estrazione public_id) ──────────────────

def test_elimina_immagine_estrae_public_id_con_versione():
    mock_destroy = MagicMock()
    url = "https://res.cloudinary.com/demo/image/upload/v1234567890/lavori/5/foto.jpg"
    with patch("cloudinary.uploader.destroy", mock_destroy):
        svc.elimina_immagine(url)

    mock_destroy.assert_called_once_with("lavori/5/foto")


def test_elimina_immagine_estrae_public_id_senza_versione():
    mock_destroy = MagicMock()
    url = "https://res.cloudinary.com/demo/image/upload/lavori/5/foto.png"
    with patch("cloudinary.uploader.destroy", mock_destroy):
        svc.elimina_immagine(url)

    mock_destroy.assert_called_once_with("lavori/5/foto")


def test_elimina_immagine_url_non_riconosciuto_non_chiama_destroy():
    """Un URL che non corrisponde al pattern Cloudinary non deve cancellare
    nulla (né far esplodere la funzione con un'eccezione)."""
    mock_destroy = MagicMock()
    with patch("cloudinary.uploader.destroy", mock_destroy):
        svc.elimina_immagine("https://example.com/non-cloudinary/foto")

    mock_destroy.assert_not_called()


def test_elimina_file_usa_resource_type_raw():
    mock_destroy = MagicMock()
    url = "https://res.cloudinary.com/demo/raw/upload/v123/allegati/7/contratto.pdf"
    with patch("cloudinary.uploader.destroy", mock_destroy):
        svc.elimina_file(url)

    mock_destroy.assert_called_once_with("allegati/7/contratto", resource_type="raw")
