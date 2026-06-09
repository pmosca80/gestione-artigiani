import sqlite3

conn = sqlite3.connect("artigiani.db")

cursor = conn.cursor()

cursor.execute("""
ALTER TABLE impostazioni_azienda
ADD COLUMN obiettivo_mensile FLOAT DEFAULT 5000
""")

conn.commit()

print("Colonna aggiunta correttamente.")

conn.close()