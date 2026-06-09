import sqlite3

db_path = "artigiani.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

colonne = [
    ("aliquota_iva", "REAL DEFAULT 22"),
    ("sconto", "REAL DEFAULT 0"),
    ("totale_iva", "REAL DEFAULT 0"),
    ("totale_documento", "REAL DEFAULT 0"),
]

for nome, tipo in colonne:
    try:
        cur.execute(f"ALTER TABLE lavori ADD COLUMN {nome} {tipo}")
        print(f"Aggiunta colonna: {nome}")
    except sqlite3.OperationalError as e:
        print(f"{nome}: {e}")

conn.commit()
conn.close()

print("Migrazione completata.")