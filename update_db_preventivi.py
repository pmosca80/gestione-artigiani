import sqlite3

conn = sqlite3.connect("artigiani.db")
cursor = conn.cursor()

def colonna_esiste(tabella, colonna):
    cursor.execute(f"PRAGMA table_info({tabella})")
    colonne = [riga[1] for riga in cursor.fetchall()]
    return colonna in colonne

if not colonna_esiste("lavori", "numero_preventivo"):
    cursor.execute("""
    ALTER TABLE lavori
    ADD COLUMN numero_preventivo VARCHAR
    """)
    print("Colonna lavori.numero_preventivo aggiunta.")
else:
    print("Colonna lavori.numero_preventivo già presente.")

if not colonna_esiste("impostazioni_azienda", "ultimo_numero_preventivo"):
    cursor.execute("""
    ALTER TABLE impostazioni_azienda
    ADD COLUMN ultimo_numero_preventivo INTEGER DEFAULT 0 NOT NULL
    """)
    print("Colonna impostazioni_azienda.ultimo_numero_preventivo aggiunta.")
else:
    print("Colonna impostazioni_azienda.ultimo_numero_preventivo già presente.")

conn.commit()
conn.close()

print("Aggiornamento database completato.")