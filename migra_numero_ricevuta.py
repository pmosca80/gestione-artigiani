import sqlite3

db_path = "artigiani.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE pagamenti_lavoro ADD COLUMN numero_ricevuta INTEGER")
    print("Colonna numero_ricevuta aggiunta.")
except sqlite3.OperationalError as e:
    print(f"Colonna già presente o errore: {e}")

conn.commit()
conn.close()

print("Migrazione completata.")