"""Garantisce che la catena di migrazioni Alembic abbia una sola head.

Due incidenti di produzione (2026-06-17) sono stati causati da revision id
scritti a mano che collidevano tra loro, creando due head e bloccando
"alembic upgrade head" all'avvio del container. Questo test fallisce subito
in CI/locale se si ripete lo stesso errore, invece di scoprirlo al deploy.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BASE_DIR = Path(__file__).resolve().parent.parent


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_una_sola_head_alembic():
    script = _script_directory()
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"Trovate {len(heads)} head invece di 1: {heads}. "
        "Probabile revision id duplicato o down_revision errato — "
        "genera i nuovi file con 'alembic revision -m \"...\"', non a mano."
    )


def test_nessun_revision_id_duplicato():
    script = _script_directory()
    ids = [rev.revision for rev in script.walk_revisions()]
    duplicati = {rid for rid in ids if ids.count(rid) > 1}
    assert not duplicati, f"Revision id duplicati tra i file di migrazione: {duplicati}"
