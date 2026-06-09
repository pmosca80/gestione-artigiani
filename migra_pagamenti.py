import sqlite3

db_path = "artigiani.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

colonne = [
    ("stato_pagamento", "TEXT DEFAULT 'da_pagare'"),
    ("importo_pagato", "REAL DEFAULT 0"),
    ("residuo_pagamento", "REAL DEFAULT 0"),
]

for nome, tipo in colonne:
    try:
        cur.execute(f"ALTER TABLE lavori ADD COLUMN {nome} {tipo}")
        print(f"Aggiunta colonna: {nome}")
    except sqlite3.OperationalError as e:
        print(f"{nome}: {e}")

conn.commit()
conn.close()

print("Migrazione pagamenti completata.")