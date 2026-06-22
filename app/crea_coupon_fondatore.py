"""
Crea i due coupon Stripe della promo "Piano Fondatore":
  1) FONDATORE-ANNOGRATIS — 100% di sconto per i primi 12 mesi (al checkout)
  2) FONDATORE50POST      — 50% di sconto a vita, applicato in automatico
                             da app/services/fondatore.py quando il primo
                             coupon scade

Da lanciare UNA SOLA VOLTA, con le tue chiavi Stripe (test o live) già
impostate in .env (STRIPE_SECRET_KEY).

Uso:
    python -m app.crea_coupon_fondatore

Dopo l'esecuzione, copia gli ID stampati a schermo nelle variabili
d'ambiente STRIPE_COUPON_FONDATORE_ANNO e STRIPE_COUPON_FONDATORE_POST
(in .env e su Railway).
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import stripe

COUPON_ANNO_ID = "FONDATORE-ANNOGRATIS"
COUPON_POST_ID = "FONDATORE50POST"


def _crea_o_recupera(coupon_id: str, **params) -> str:
    try:
        esistente = stripe.Coupon.retrieve(coupon_id)
        print(f"Il coupon '{coupon_id}' esiste già (creato il {esistente.created}).")
        return esistente.id
    except stripe.error.InvalidRequestError:
        pass  # non esiste ancora, lo creiamo

    coupon = stripe.Coupon.create(id=coupon_id, **params)
    print(f"Coupon '{coupon_id}' creato con successo.")
    return coupon.id


def main():
    secret_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not secret_key:
        print("ERRORE: STRIPE_SECRET_KEY non impostata in .env")
        sys.exit(1)

    modalita = "LIVE (account reale, pagamenti veri)" if secret_key.startswith("sk_live_") else "TEST (sandbox, nessun pagamento reale)"
    print(f"Modalità Stripe rilevata: {modalita}")
    print(f"Verranno creati due coupon: '{COUPON_ANNO_ID}' (100% per 12 mesi) e '{COUPON_POST_ID}' (50% a vita).")
    risposta = input("Confermi la creazione su questo account? [si/no] ").strip().lower()
    if risposta not in ("si", "s", "yes", "y"):
        print("Annullato.")
        sys.exit(0)

    stripe.api_key = secret_key

    id_anno = _crea_o_recupera(
        COUPON_ANNO_ID,
        name="Piano Fondatore — primo anno gratis",
        percent_off=100,
        duration="repeating",
        duration_in_months=12,
    )
    id_post = _crea_o_recupera(
        COUPON_POST_ID,
        name="Piano Fondatore — 50% a vita",
        percent_off=50,
        duration="forever",
    )

    print("\nAggiungi queste righe a .env (e alle variabili d'ambiente su Railway):")
    print(f"STRIPE_COUPON_FONDATORE_ANNO={id_anno}")
    print(f"STRIPE_COUPON_FONDATORE_POST={id_post}")


if __name__ == "__main__":
    main()
