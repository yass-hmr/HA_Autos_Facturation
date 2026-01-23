from __future__ import annotations

import re


def euros_to_cents(text: str) -> int:
    """
    Convertit une saisie utilisateur en centimes.
    Accepte: "12", "12.5", "12,50", "  12,50 € "
    """
    s = (text or "").strip().replace("€", "").strip()
    if not s:
        return 0
    s = s.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{0,2})?", s):
        raise ValueError("Prix invalide. Exemple: 12,50")
    if "." in s:
        euros, dec = s.split(".", 1)
        dec = (dec + "00")[:2]
    else:
        euros, dec = s, "00"
    return int(euros) * 100 + int(dec)


def cents_to_euros(cents: int) -> str:
    cents = int(cents)
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d} €"
