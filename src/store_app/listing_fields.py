"""Listing draft fields shared by the add-item form and eBay create."""

from __future__ import annotations

import html
import json
import re

CONDITIONS = (
    ("1000", "New"),
    ("1500", "New other"),
    ("3000", "Used"),
    ("7000", "For parts"),
)

CONDITION_LABELS = {code: label for code, label in CONDITIONS}
DEFAULT_CONDITION = "3000"
TITLE_EBAY_MAX = 80


PREFERRED_SPECIFICS = (
    "Brand",
    "Manufacturer",
    "Model",
    "Department",
    "Watch Movement",
    "Case Size",
    "Case Diameter",
    "Band Width",
    "Band Material",
    "Maximum Wrist Size",
    "Wrist Size",
    "Dial Color",
    "Dial",
    "Case Color",
    "Band Color",
    "Color",
    "Case Material",
)


def decode_specifics(raw: object) -> list[dict[str, object]]:
    if not raw:
        return []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, str):
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        return []
    out: list[dict[str, object]] = []
    if not isinstance(rows, list):
        return []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        values = [str(value).strip() for value in (row.get("values") or []) if str(value).strip()]
        if name and values:
            out.append({"name": name, "values": values})
    return out


def encode_specifics(rows: object) -> str:
    return json.dumps(decode_specifics(rows), ensure_ascii=False)


def sort_specifics(rows: object) -> list[dict[str, object]]:
    decoded = decode_specifics(rows)
    rank = {name.lower(): index for index, name in enumerate(PREFERRED_SPECIFICS)}
    decoded.sort(key=lambda row: (rank.get(str(row["name"]).lower(), 1000), str(row["name"]).lower()))
    return decoded


def brand_from_specifics(rows: object) -> str:
    decoded = decode_specifics(rows)
    by_name = {str(row["name"]).lower(): row.get("values") or [] for row in decoded}
    for key in ("brand", "manufacturer"):
        values = by_name.get(key) or []
        if values:
            return str(values[0])
    return ""


def html_to_text(value: str) -> str:
    text = value or ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
