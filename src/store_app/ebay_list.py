"""Create an eBay listing from a shelf item and its local photos."""

from __future__ import annotations

import os
from store_app.photos import read_bytes
from store_app.store import first_active_listing_id, get_item, upsert_item, upsert_listing


def _profiles(client) -> dict[str, str]:
    from trading import seller_profiles_from_item

    env_profiles = {
        "shipping_profile_id": os.getenv("EBAY_SHIPPING_PROFILE_ID", "").strip(),
        "return_profile_id": os.getenv("EBAY_RETURN_PROFILE_ID", "").strip(),
        "payment_profile_id": os.getenv("EBAY_PAYMENT_PROFILE_ID", "").strip(),
        "postal_code": os.getenv("EBAY_POSTAL_CODE", "").strip(),
        "location": os.getenv("EBAY_LOCATION", "").strip() or "USA",
        "country": os.getenv("EBAY_COUNTRY", "US").strip() or "US",
        "dispatch_time": os.getenv("EBAY_DISPATCH_TIME", "3").strip() or "3",
    }
    listing_id = first_active_listing_id()
    if listing_id:
        copied = seller_profiles_from_item(client, listing_id)
        for key, value in copied.items():
            if value and not env_profiles.get(key):
                env_profiles[key] = value
    return env_profiles


def list_item_on_ebay(sku: str) -> str:
    from ebay_client import EbayClient
    from listing_assist import html_description, suggest_categories
    from trading import add_fixed_price_item, upload_picture

    item = get_item(sku)
    if item is None:
        raise ValueError(f"Unknown SKU {sku}")
    if any(row.get("status") == "active" for row in item.get("listings") or []):
        raise ValueError("This SKU already has an active eBay listing")
    if not item.get("ask_price"):
        raise ValueError("Ask price is required to list")
    photos = item.get("photos") or []
    if not photos:
        raise ValueError("Add at least one photo before listing")
    client = EbayClient()
    category_id = item.get("ebay_category_id") or ""
    category_name = item.get("ebay_category_name") or ""
    if not category_id:
        suggestions = suggest_categories(client, item["title"] or sku)
        if not suggestions:
            raise ValueError("Could not pick an eBay category. Fill category or run Suggest first.")
        category_id = suggestions[0]["id"]
        category_name = suggestions[0]["name"]
    picture_urls = []
    for photo in photos:
        picture_urls.append(
            upload_picture(client, read_bytes(sku, photo["filename"]), name=f"{sku}-{photo['id']}")
        )
    description = html_description(item.get("description") or item.get("notes") or item["title"])
    new_id = add_fixed_price_item(
        client,
        title=item["title"],
        description=description,
        price=item["ask_price"],
        qty=item.get("qty") or 1,
        sku=sku,
        category_id=category_id,
        condition_id=item.get("condition_id") or "3000",
        picture_urls=picture_urls,
        brand=item.get("brand") or "",
        item_specifics=item.get("item_specifics") or [],
        profiles=_profiles(client),
    )
    upsert_listing(
        ebay_item_id=new_id,
        title=item["title"],
        sku=sku,
        price=item["ask_price"],
        qty=item.get("qty") or 1,
        status="active",
        ebay_category=category_name,
        image_url=picture_urls[0],
    )
    upsert_item(
        sku=sku,
        title=item["title"],
        category=item["category"],
        qty=item.get("qty") or 1,
        cost=item.get("cost") or "",
        ask_price=item["ask_price"],
        location=item.get("location") or "",
        status="listed",
        notes=item.get("notes") or "",
        cogs_item_id=item.get("cogs_item_id") or "",
        cogs_build_id=item.get("cogs_build_id") or "",
        description=item.get("description") or "",
        condition_id=item.get("condition_id") or "",
        ebay_category_id=category_id,
        ebay_category_name=category_name,
        brand=item.get("brand") or "",
        item_specifics=item.get("item_specifics") or [],
    )
    return new_id
