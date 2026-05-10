from app.database import SessionLocal
from app.models import Utente
from app.security import hash_password

db = SessionLocal()

username = "admin"
password = "admin"

utente = db.query(Utente).filter(Utente.username == username).first()

if utente:
    utente.password = hash_password(password)
    print("Admin già esistente: password aggiornata")
else:
    utente = Utente(
        username=username,
        password=hash_password(password)
    )
    db.add(utente)
    print("Admin creato")

db.commit()

print("ID admin:", utente.id)
print("Totale utenti:", db.query(Utente).count())

db.close()