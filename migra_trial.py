import sqlite3
import os
from datetime import datetime

db_path = "artigiani.db"
if not os.path.exists(db_path):
    db_path = "gestione_artigiani.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

oggi = datetime.now().strftime("%Y-%m-%d")

try:
    cursor.execute("ALTER TABLE utenti ADD COLUMN data_registrazione TEXT")
    print("Colonna data_registrazione aggiunta.")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e):
        print("data_registrazione già esistente.")
    else:
        raise

try:
    cursor.execute("ALTER TABLE utenti ADD COLUMN attivo INTEGER NOT NULL DEFAULT 1")
    print("Colonna attivo aggiunta.")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e):
        print("attivo già esistente.")
    else:
        raise

cursor.execute(
    "UPDATE utenti SET data_registrazione = ?, attivo = 1 WHERE data_registrazione IS NULL",
    (oggi,)
)
print(f"Utenti esistenti aggiornati con data_registrazione = {oggi} e attivo = 1.")

conn.commit()
conn.close()
print("Migrazione completata.")