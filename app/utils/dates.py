from __future__ import annotations

import re
from datetime import date as _date, datetime

_DATE_FR_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def today_fr() -> str:
    return _date.today().strftime("%d/%m/%Y")


def fr_to_iso(d: str) -> str:
    d = (d or "").strip()
    if not d:
        return _date.today().isoformat()
    m = _DATE_FR_RE.match(d)
    if not m:
        raise ValueError("Date invalide. Format attendu : jj/mm/aaaa")
    dd, mm, yyyy = m.groups()
    dt = datetime(int(yyyy), int(mm), int(dd))
    return dt.date().isoformat()


def iso_to_fr(d: str) -> str:
    d = (d or "").strip()
    if not d:
        return today_fr()
    if _DATE_FR_RE.match(d):
        return d
    try:
        y, m, dd = d.split("-")
        return f"{dd}/{m}/{y}"
    except Exception:
        return d
