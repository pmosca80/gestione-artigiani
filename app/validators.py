"""Costanti di lunghezza e helper di sanitizzazione per i campi Form."""

# Campi identità
USERNAME_MAX = 50
PASSWORD_MAX = 128
EMAIL_MAX = 200

# Campi anagrafici
NOME_MAX = 100
RAGIONE_SOCIALE_MAX = 200
TELEFONO_MAX = 30
INDIRIZZO_MAX = 200
CITTA_MAX = 100
PROVINCIA_MAX = 5
CAP_MAX = 10

# Campi fiscali strutturati (lunghezze normative)
PARTITA_IVA_MAX = 13     # 11 cifre IT + prefisso paese
CODICE_FISCALE_MAX = 20
CODICE_DEST_MAX = 7      # SDI codice destinatario
PEC_MAX = 200
REGIME_FISCALE_MAX = 10  # RF01, RF19 …
NUMERO_FATTURA_MAX = 30

# Campi liberi
TITOLO_MAX = 200
DESCRIZIONE_MAX = 2000
NOTE_MAX = 1000
CATEGORIA_MAX = 50
UNITA_MISURA_MAX = 20


# Magic bytes per validazione MIME lato server (indipendente dall'estensione dichiarata)
_MAGIC_BYTES: dict[str, bytes] = {
    ".jpg":  b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png":  b"\x89PNG\r\n\x1a\n",
    ".webp": b"RIFF",
    ".pdf":  b"%PDF",
    ".doc":  b"\xd0\xcf\x11\xe0",
    ".xls":  b"\xd0\xcf\x11\xe0",
    ".docx": b"PK\x03\x04",
    ".xlsx": b"PK\x03\x04",
    ".db":   b"SQLite format 3\x00",
}


def check_magic(contenuto: bytes, estensione: str) -> bool:
    """Verifica che i magic bytes corrispondano all'estensione dichiarata."""
    firma = _MAGIC_BYTES.get(estensione)
    if firma is None:
        return False
    return contenuto[: len(firma)] == firma


def clean(s: str | None, max_len: int) -> str:
    """Strip whitespace e tronca silenziosamente a max_len caratteri."""
    if not s:
        return ""
    return s.strip()[:max_len]


def safe_redirect(url: str, default: str = "/") -> str:
    """Restituisce url solo se è un path relativo sicuro, altrimenti default."""
    url = (url or "").strip()
    if not url.startswith("/") or url.startswith("//") or "://" in url:
        return default
    return url
