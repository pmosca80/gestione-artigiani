from app.database import SessionLocal
from app.models import Utente
from app.security import verify_password

db = SessionLocal()

utente = db.query(Utente).filter(
    Utente.username == "admin"
).first()

if not utente:
    print("Admin NON trovato")
else:
    print("Admin trovato")
    print("ID:", utente.id)
    print("Username:", utente.username)
    print("Password salvata:", utente.password)

    try:
        risultato = verify_password(
            "admin",
            utente.password
        )

        print("Verifica admin/admin:", risultato)

    except Exception as e:
        print("Errore:", e)

db.close()
