import os
import stripe


def stripe_configurato() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def crea_payment_link(
    numero_fmt: str,
    importo_totale: float,
    fattura_id: int,
    utente_id: int,
) -> tuple[str, str]:
    """Crea un Stripe Payment Link per la fattura. Ritorna (link_id, link_url)."""
    api_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not api_key:
        raise RuntimeError("STRIPE_SECRET_KEY non configurata")
    stripe.api_key = api_key

    price = stripe.Price.create(
        unit_amount=round(importo_totale * 100),
        currency="eur",
        product_data={"name": f"Fattura {numero_fmt}"},
    )
    link = stripe.PaymentLink.create(
        line_items=[{"price": price.id, "quantity": 1}],
        metadata={
            "fattura_id": str(fattura_id),
            "utente_id": str(utente_id),
        },
    )
    return link.id, link.url
