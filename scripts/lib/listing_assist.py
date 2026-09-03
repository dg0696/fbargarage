"""Draft listing fields from eBay comps and optional vision AI."""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from credentials import secret  # noqa: E402
from ebay_client import EbayClient  # noqa: E402
from trading import suggest_categories  # noqa: E402

MARKETPLACE = "EBAY_US"


def _ai_keys() -> dict[str, str]:
    return {
        "openai": os.getenv("OPENAI_API_KEY") or secret("OPENAI_API_KEY"),
        "gemini": os.getenv("GEMINI_API_KEY") or secret("GEMINI_API_KEY"),
    }


def search_ebay_comps(client: EbayClient, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    text = (query or "").strip()
    if not text:
        return []
    payload = client.api_get(
        "/buy/browse/v1/item_summary/search",
        params={"q": text[:100], "limit": str(limit)},
        use_user_token=False,
    )
    # Browse prefers marketplace header; retry via direct request if empty.
    items = payload.get("itemSummaries") or []
    if not items:
        token = client.get_application_token()
        response = requests.get(
            f"{client.api_base}/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE,
            },
            params={"q": text[:100], "limit": str(limit)},
            timeout=60,
        )
        response.raise_for_status()
        items = response.json().get("itemSummaries") or []
    comps = []
    for row in items[:limit]:
        price = (row.get("price") or {}).get("value") or ""
        image = ((row.get("image") or {}).get("imageUrl")) or ""
        categories = row.get("leafCategoryIds") or []
        comps.append(
            {
                "title": row.get("title") or "",
                "price": str(price),
                "url": row.get("itemWebUrl") or "",
                "image_url": image,
                "condition": row.get("condition") or "",
                "category_id": str(categories[0]) if categories else "",
                "item_id": row.get("itemId") or "",
            }
        )
    return comps


def _median_price(comps: list[dict[str, Any]]) -> str:
    amounts = []
    for row in comps:
        try:
            amounts.append(float(row["price"]))
        except (TypeError, ValueError, KeyError):
            continue
    if not amounts:
        return ""
    return f"{statistics.median(amounts):.2f}"


def _comps_description(title: str, notes: str, comps: list[dict[str, Any]]) -> str:
    lines = [title.strip()] if title.strip() else []
    if notes.strip():
        lines.extend(["", notes.strip()])
    if comps:
        lines.extend(["", "Similar sold/listed items on eBay:"])
        for row in comps[:5]:
            price = f" — ${row['price']}" if row.get("price") else ""
            condition = f" ({row['condition']})" if row.get("condition") else ""
            lines.append(f"- {row['title']}{condition}{price}")
    return "\n".join(lines).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI did not return JSON")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("AI JSON was not an object")
    return data


def _openai_draft(prompt: str, images: list[bytes], key: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for blob in images[:4]:
        import base64

        encoded = base64.b64encode(blob).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
            }
        )
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
        },
        timeout=90,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    return _parse_json_object(text)


def _gemini_draft(prompt: str, images: list[bytes], key: str) -> dict[str, Any]:
    import base64

    parts: list[dict[str, Any]] = [{"text": prompt}]
    for blob in images[:4]:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(blob).decode("ascii")}})
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": key},
        json={"contents": [{"parts": parts}]},
        timeout=90,
    )
    response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json_object(text)


def draft_listing(
    *,
    title: str,
    notes: str = "",
    description: str = "",
    images: list[bytes] | None = None,
    client: EbayClient | None = None,
) -> dict[str, Any]:
    """Return suggested title, description, price, brand, condition, category, and comps."""
    client = client or EbayClient()
    query = " ".join(part for part in (title, notes) if part.strip()).strip() or title
    comps: list[dict[str, Any]] = []
    categories: list[dict[str, str]] = []
    errors: list[str] = []
    try:
        comps = search_ebay_comps(client, query)
    except Exception as exc:
        errors.append(f"eBay search: {exc}")
    try:
        categories = suggest_categories(client, query)
    except Exception as exc:
        errors.append(f"eBay categories: {exc}")

    suggested = {
        "title": (title or "").strip()[:80],
        "description": description.strip() or _comps_description(title, notes, comps),
        "ask_price": _median_price(comps),
        "brand": "",
        "condition_id": "3000",
        "ebay_category_id": (categories[0]["id"] if categories else "")
        or next((row["category_id"] for row in comps if row.get("category_id")), ""),
        "ebay_category_name": categories[0]["name"] if categories else "",
        "source": "ebay-comps",
    }
    first_condition = next((row["condition"] for row in comps if row.get("condition")), "")
    lowered = first_condition.lower()
    if "new" in lowered and "other" in lowered:
        suggested["condition_id"] = "1500"
    elif lowered == "new" or lowered.startswith("new "):
        suggested["condition_id"] = "1000"
    elif "part" in lowered:
        suggested["condition_id"] = "7000"

    keys = _ai_keys()
    prompt = (
        "You help an eBay seller draft a US listing. Return JSON only with keys: "
        "title (max 80 chars), description (plain text, 2-6 short paragraphs), "
        "ask_price (number string), brand, condition_id "
        "(1000 new, 1500 new other, 3000 used, 7000 for parts), "
        "ebay_category_hint (short). Use the photos and these comparable listings:\n"
        f"{json.dumps(comps[:6], ensure_ascii=True)}\n"
        f"Seller title: {title}\nSeller notes: {notes}\n"
        "Do not invent certifications or fitment you cannot see."
    )
    images = images or []
    ai_data = None
    try:
        if keys["openai"]:
            ai_data = _openai_draft(prompt, images, keys["openai"])
            suggested["source"] = "openai+ebay"
        elif keys["gemini"]:
            ai_data = _gemini_draft(prompt, images, keys["gemini"])
            suggested["source"] = "gemini+ebay"
        elif images:
            errors.append("No OPENAI_API_KEY or GEMINI_API_KEY — used eBay matches only")
    except Exception as exc:
        errors.append(f"AI: {exc}")
        ai_data = None

    if isinstance(ai_data, dict):
        if ai_data.get("title"):
            suggested["title"] = str(ai_data["title"]).strip()[:80]
        if ai_data.get("description"):
            suggested["description"] = str(ai_data["description"]).strip()
        if ai_data.get("ask_price"):
            suggested["ask_price"] = str(ai_data["ask_price"]).strip()
        if ai_data.get("brand"):
            suggested["brand"] = str(ai_data["brand"]).strip()[:128]
        if str(ai_data.get("condition_id") or "") in {"1000", "1500", "3000", "7000"}:
            suggested["condition_id"] = str(ai_data["condition_id"])

    return {
        "suggested": suggested,
        "comps": comps,
        "categories": categories,
        "errors": errors,
        "ai_ready": bool(keys["openai"] or keys["gemini"]),
    }


def html_description(text: str) -> str:
    body = xml_escape((text or "").strip()).replace("\n", "<br>\n")
    return f"<div>{body}</div>" if body else ""
