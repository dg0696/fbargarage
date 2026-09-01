"""SKU prefix → store stream / inventory category."""

from __future__ import annotations

CATEGORIES = (
    "fashion",
    "electronics",
    "moto",
    "auto",
    "art",
    "workshop",
    "other",
)

ITEM_STATUSES = ("on-hand", "listed", "sold", "removed")
LISTING_STATUSES = ("active", "ended", "all")

_FASHION = {"BA", "BB", "BC", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BK", "BL"}
_ELECTRONICS = {"AA", "AB", "AC", "AD", "AE"}
_MOTO = {"GB", "GC"}
_ART = {"RA", "RB"}
_AUTO = {"CA", "CV", "JA"}


def _prefix2(sku: str) -> str:
    return (sku or "").upper().replace("-", "")[:2]


def stream_from_sku(sku: str) -> str:
    raw = (sku or "").upper().strip()
    if raw.startswith("WS"):
        return "workshop"
    prefix = _prefix2(raw)
    if prefix in _FASHION:
        return "fashion"
    if prefix in _ELECTRONICS:
        return "electronics"
    if prefix in _MOTO:
        return "moto"
    if prefix in _ART:
        return "art"
    if prefix in _AUTO:
        return "auto"
    return "other"
