import sqlite3

conn = sqlite3.connect("artigiani.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS allegati_lavoro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    utente_id INTEGER NOT NULL,
    lavoro_id INTEGER NOT NULL,
    nome_file VARCHAR NOT NULL,
    percorso_file VARCHAR NOT NULL,
    tipo_file VARCHAR,
    descrizione TEXT,
    data_creazione VARCHAR NOT NULL,
    FOREIGN KEY(utente_id) REFERENCES utenti(id),
    FOREIGN KEY(lavoro_id) REFERENCES lavori(id)
)
""")

conn.commit()
conn.close()

print("Tabella allegati_lavoro creata correttamente.")