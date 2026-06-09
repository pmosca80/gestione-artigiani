import sqlite3

DB_PATH = "artigiani.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

colonne = [
    ("prezzo_acquisto_pieno", "REAL DEFAULT 0"),
    ("prezzo_acquisto_scontato", "REAL DEFAULT 0"),
    ("prezzo_vendita_default", "REAL DEFAULT 0"),
]

for nome, tipo in colonne:
    try:
        cursor.execute(f"ALTER TABLE materiali ADD COLUMN {nome} {tipo}")
        print(f"Colonna aggiunta: {nome}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"Colonna già esistente: {nome}")
        else:
            raise

conn.commit()
conn.close()

print("Database aggiornato correttamente.")