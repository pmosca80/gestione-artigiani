import sqlite3

DB_PATH = "artigiani.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    cursor.execute(
        "ALTER TABLE materiali_usati_lavoro "
        "ADD COLUMN prezzo_unitario_cliente REAL DEFAULT 0"
    )
    print("Colonna aggiunta: prezzo_unitario_cliente")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("Colonna già esistente: prezzo_unitario_cliente")
    else:
        raise

conn.commit()
conn.close()

print("Database aggiornato correttamente.")