import sqlite3

db_path = "artigiani.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE lavori ADD COLUMN data_scadenza_pagamento TEXT")
    print("Aggiunta colonna: data_scadenza_pagamento")
except sqlite3.OperationalError as e:
    print(f"Colonna già presente o errore: {e}")

conn.commit()
conn.close()

print("Migrazione scadenza pagamento completata.")