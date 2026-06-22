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

Il .env locale viene aggiornato automaticamente con gli ID dei coupon.
Resta da fare solo un passo manuale: copiare le stesse due righe anche
nelle variabili d'ambiente su Railway (stampate a fine esecuzione).
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import stripe

COUPON_ANNO_ID = "FONDATORE-ANNOGRATIS"
COUPON_POST_ID = "FONDATORE50POST"

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _aggiorna_env(percorso: Path, valori: dict[str, str]) -> None:
    """Scrive/aggiorna le righe KEY=VALUE nel .env, senza toccare il resto
    del file. Evita il copia-incolla a mano (fonte frequente di errori:
    placeholder lasciati per sbaglio, righe duplicate, valori scambiati)."""
    if not percorso.exists():
        print(f"ATTENZIONE: {percorso} non esiste, salto l'aggiornamento automatico.")
        return

    righe = percorso.read_text(encoding="utf-8").splitlines()
    trovate = set()
    for i, riga in enumerate(righe):
        for chiave, valore in valori.items():
            if riga.startswith(f"{chiave}="):
                righe[i] = f"{chiave}={valore}"
                trovate.add(chiave)

    for chiave, valore in valori.items():
        if chiave not in trovate:
            righe.append(f"{chiave}={valore}")

    percorso.write_text("\n".join(righe) + "\n", encoding="utf-8")


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

    valori = {
        "STRIPE_COUPON_FONDATORE_ANNO": id_anno,
        "STRIPE_COUPON_FONDATORE_POST": id_post,
    }
    _aggiorna_env(ENV_PATH, valori)
    print(f"\n.env aggiornato automaticamente ({ENV_PATH}).")
    print("Aggiungi anche queste righe alle variabili d'ambiente su Railway:")
    for chiave, valore in valori.items():
        print(f"{chiave}={valore}")


if __name__ == "__main__":
    main()
