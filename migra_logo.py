import sqlite3
import os

db_path = "artigiani.db"

if not os.path.exists(db_path):
    db_path = "gestione_artigiani.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE impostazioni_azienda ADD COLUMN logo_path TEXT")
    conn.commit()
    print("Colonna logo_path aggiunta con successo.")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e):
        print("Colonna già esistente, nessuna modifica necessaria.")
    else:
        raise
finally:
    conn.close()