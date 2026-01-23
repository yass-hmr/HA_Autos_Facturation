from __future__ import annotations

from typing import List, Tuple


def calc_totals(lines: List[Tuple[int, int]]) -> tuple[int, int, int]:
    """
    lines: list of (qty, unit_price_cents)
    returns: subtotal_cents, vat_cents, total_cents
    """
    subtotal = 0
    for qty, up in lines:
        subtotal += int(qty) * int(up)

    vat = (subtotal * 20) // 100
    total = subtotal + vat
    return subtotal, vat, total
