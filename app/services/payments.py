"""Moyasar payments (Saudi gateway: Mada, Visa/Mastercard, Apple Pay, STC Pay).

Flow: invoice page embeds Moyasar's hosted form (publishable key) → client pays → Moyasar redirects to
/inv/<token>/callback?id=<payment_id> → we VERIFY the payment server-side with the secret key (never trust
the redirect) → amount & currency must match → invoice marked paid. Webhook does the same for robustness.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from ..config import settings

API = "https://api.moyasar.com/v1"


def configured() -> bool:
    return bool(settings.MOYASAR_PUBLISHABLE_KEY and settings.MOYASAR_SECRET_KEY)


def halalas(inv) -> int:
    return int(inv.amount + inv.vat) * 100


async def fetch_payment(payment_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20, auth=(settings.MOYASAR_SECRET_KEY, "")) as client:
        r = await client.get(f"{API}/payments/{payment_id}")
        r.raise_for_status()
        return r.json()


def matches(payment: dict, inv) -> tuple[bool, str]:
    """True when the gateway says PAID for exactly this invoice's amount in SAR."""
    if payment.get("status") != "paid":
        return False, f"status={payment.get('status')}"
    if payment.get("currency", "SAR") != "SAR":
        return False, "currency"
    if int(payment.get("amount", 0)) != halalas(inv):
        return False, f"amount {payment.get('amount')} != {halalas(inv)}"
    meta = payment.get("metadata") or {}
    if meta.get("invoice_token") != inv.token:  # a payment created for another invoice (or outside our form) never counts
        return False, "token mismatch"
    return True, "ok"


def apply_paid(inv, payment: dict, via: str = "moyasar") -> bool:
    """Idempotent: marks the invoice paid once."""
    if inv.status == "paid":
        return False
    inv.status = "paid"
    inv.paid_at = datetime.utcnow()
    inv.paid_via = via
    inv.payment_id = str(payment.get("id", ""))[:80]
    if inv.client.status == "onboarding":
        inv.client.status = "active"
    return True
