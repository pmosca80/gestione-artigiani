import sqlite3

db_path = "artigiani.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS pagamenti_lavoro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    utente_id INTEGER NOT NULL,
    lavoro_id INTEGER NOT NULL,
    data_pagamento TEXT NOT NULL,
    importo REAL DEFAULT 0,
    metodo TEXT,
    note TEXT,
    data_creazione TEXT NOT NULL
)
""")

conn.commit()
conn.close()

print("Tabella pagamenti_lavoro creata.")