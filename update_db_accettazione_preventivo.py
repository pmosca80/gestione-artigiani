import sqlite3

conn = sqlite3.connect("artigiani.db")
cursor = conn.cursor()

def colonna_esiste(tabella, colonna):
    cursor.execute(f"PRAGMA table_info({tabella})")
    colonne = [riga[1] for riga in cursor.fetchall()]
    return colonna in colonne

if not colonna_esiste("lavori", "data_accettazione_preventivo"):
    cursor.execute("""
    ALTER TABLE lavori
    ADD COLUMN data_accettazione_preventivo VARCHAR
    """)
    print("Colonna lavori.data_accettazione_preventivo aggiunta.")
else:
    print("Colonna già presente.")

conn.commit()
conn.close()

print("Aggiornamento completato.")