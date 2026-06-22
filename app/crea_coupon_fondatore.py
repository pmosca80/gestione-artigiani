"""
Crea il coupon Stripe "Piano Fondatore" (50% di sconto a vita).

Da lanciare UNA SOLA VOLTA, con le tue chiavi Stripe (test o live) già
impostate in .env (STRIPE_SECRET_KEY). Il coupon creato è permanente
(duration="forever") e si applica automaticamente in fase di checkout
ai soli utenti con piano_fondatore=True (i primi 100 registrati, vedi
auth.py::register).

Uso:
    python -m app.crea_coupon_fondatore

Dopo l'esecuzione, copia l'ID del coupon stampato a schermo nella
variabile d'ambiente STRIPE_COUPON_FONDATORE (in .env e su Railway).
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import stripe

COUPON_ID = "FONDATORE50"


def main():
    secret_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not secret_key:
        print("ERRORE: STRIPE_SECRET_KEY non impostata in .env")
        sys.exit(1)

    modalita = "LIVE (account reale, pagamenti veri)" if secret_key.startswith("sk_live_") else "TEST (sandbox, nessun pagamento reale)"
    print(f"Modalità Stripe rilevata: {modalita}")
    risposta = input(f"Confermi la creazione del coupon '{COUPON_ID}' (50% sconto a vita) su questo account? [si/no] ").strip().lower()
    if risposta not in ("si", "s", "yes", "y"):
        print("Annullato.")
        sys.exit(0)

    stripe.api_key = secret_key

    try:
        esistente = stripe.Coupon.retrieve(COUPON_ID)
        print(f"Il coupon '{COUPON_ID}' esiste già su questo account (creato il {esistente.created}).")
        print(f"STRIPE_COUPON_FONDATORE={esistente.id}")
        return
    except stripe.error.InvalidRequestError:
        pass  # non esiste ancora, lo creiamo

    coupon = stripe.Coupon.create(
        id=COUPON_ID,
        name="Piano Fondatore — 50% a vita",
        percent_off=50,
        duration="forever",
    )
    print("Coupon creato con successo.")
    print(f"STRIPE_COUPON_FONDATORE={coupon.id}")
    print("\nAggiungi questa riga a .env (e alle variabili d'ambiente su Railway):")
    print(f"STRIPE_COUPON_FONDATORE={coupon.id}")


if __name__ == "__main__":
    main()
