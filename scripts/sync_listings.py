"""Pull live eBay listings into MySQL (Trading GetMyeBaySelling).

Traditional Seller Hub listings are not in the Inventory API.
Uses the Production user token from Windows Credential Manager.

Usage:
    python scripts/sync_listings.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from ebay_client import EbayClient  # noqa: E402
from store_app.store import (  # noqa: E402
    _conn,
    apply_listing_to_item,
    counts,
    ensure_columns,
    get_item,
    get_meta,
    items_needing_ebay_details,
    listing_snapshots,
    set_meta,
    upsert_listing,
)
from trading import (  # noqa: E402
    NS,
    fetch_seller_events,
    get_listing_details,
    item_specific,
    listing_item_specifics,
    listing_picture_urls,
    trading_call,
    xml_text,
)

INCREMENTAL_MAX = timedelta(hours=47)
OVERLAP = timedelta(minutes=2)
LISTINGS_META = "listings_synced_at"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_meta_time(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_active_pages(client: EbayClient):
    items = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        inner = f"""
  <ActiveList>
    <Include>true</Include>
    <Pagination>
      <EntriesPerPage>200</EntriesPerPage>
      <PageNumber>{page}</PageNumber>
    </Pagination>
  </ActiveList>
  <DetailLevel>ReturnAll</DetailLevel>
"""
        root = trading_call(client, "GetMyeBaySelling", inner)
        pagination = root.find("e:ActiveList/e:PaginationResult", NS)
        total_pages = int(xml_text(pagination, "e:TotalNumberOfPages") or "1")
        items.extend(root.findall("e:ActiveList/e:ItemArray/e:Item", NS))
        page += 1
    return items


def _money(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _qty_available(item) -> str:
    selling = item.find("e:SellingStatus", NS)
    available = xml_text(item, "e:QuantityAvailable")
    if available:
        return available
    listed = xml_text(item, "e:Quantity") or "0"
    sold = xml_text(selling, "e:QuantitySold") or "0"
    try:
        return str(max(int(Decimal(listed)) - int(Decimal(sold)), 0))
    except (InvalidOperation, ValueError):
        return listed or "0"


def _listing_status(item) -> str:
    selling = item.find("e:SellingStatus", NS)
    raw = (xml_text(selling, "e:ListingStatus") or xml_text(item, "e:ListingStatus") or "Active").lower()
    return "active" if raw == "active" else "ended"


def _same_listing(existing: dict, incoming: dict) -> bool:
    if (existing.get("title") or "") != (incoming.get("title") or ""):
        return False
    if (existing.get("sku") or "") != (incoming.get("sku") or ""):
        return False
    if (existing.get("status") or "") != (incoming.get("status") or ""):
        return False
    if int(existing.get("qty") or 0) != int(incoming.get("qty") or 0):
        return False
    old_price = existing.get("price") or ""
    new_price = incoming.get("price")
    new_text = f"{new_price:.2f}" if isinstance(new_price, Decimal) else str(new_price or "")
    return str(old_price) == new_text


def _row_from_xml(item) -> dict | None:
    item_id = xml_text(item, "e:ItemID")
    title = xml_text(item, "e:Title")
    if not item_id or not title:
        return None
    selling = item.find("e:SellingStatus", NS)
    picture_urls = listing_picture_urls(item)
    qty = _qty_available(item)
    return {
        "ebay_item_id": item_id,
        "title": title,
        "sku": xml_text(item, "e:SKU"),
        "price": _money(xml_text(selling, "e:CurrentPrice") or xml_text(item, "e:StartPrice")),
        "qty": qty,
        "status": _listing_status(item),
        "ebay_category": xml_text(item, "e:PrimaryCategory/e:CategoryName"),
        "watchers": xml_text(item, "e:WatchCount") or None,
        "start_date": (xml_text(item, "e:ListingDetails/e:StartTime") or "")[:10] or None,
        "end_date": (xml_text(item, "e:ListingDetails/e:EndTime") or "")[:10] or None,
        "image_url": picture_urls[0] if picture_urls else "",
        "picture_urls": picture_urls,
        "condition_id": xml_text(item, "e:ConditionID"),
        "ebay_category_id": xml_text(item, "e:PrimaryCategory/e:CategoryID"),
        "brand": item_specific(item, "Brand") or item_specific(item, "Manufacturer"),
        "item_specifics": listing_item_specifics(item),
        "xml": item,
    }


def _write_listing(client, row: dict, *, enrich_details: bool, existing: dict | None) -> None:
    image_url = row["image_url"] or (existing or {}).get("image_url") or ""
    category = row["ebay_category"] or (existing or {}).get("ebay_category") or ""
    upsert_listing(
        ebay_item_id=row["ebay_item_id"],
        title=row["title"],
        sku=row["sku"],
        price=row["price"],
        qty=row["qty"],
        status=row["status"],
        ebay_category=category,
        watchers=row["watchers"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        image_url=image_url,
    )
    sku = (row["sku"] or "").strip()
    if not sku or row["status"] != "active":
        return
    details = {
        "condition_id": row["condition_id"],
        "ebay_category_id": row["ebay_category_id"],
        "ebay_category_name": category,
        "brand": row["brand"],
        "description": "",
        "picture_urls": row["picture_urls"] if enrich_details else [],
        "item_specifics": row["item_specifics"] or None,
    }
    if enrich_details:
        try:
            extra = get_listing_details(client, row["ebay_item_id"])
        except Exception:
            extra = {}
        if extra.get("description"):
            details["description"] = str(extra["description"])
        if extra.get("condition_id"):
            details["condition_id"] = str(extra["condition_id"])
        if extra.get("ebay_category_id"):
            details["ebay_category_id"] = str(extra["ebay_category_id"])
        if extra.get("ebay_category_name"):
            details["ebay_category_name"] = str(extra["ebay_category_name"])
        if extra.get("brand"):
            details["brand"] = str(extra["brand"])
        if extra.get("item_specifics"):
            details["item_specifics"] = extra["item_specifics"]
        extra_pics = extra.get("picture_urls") or []
        if extra_pics:
            details["picture_urls"] = extra_pics
    apply_listing_to_item(
        sku,
        title=row["title"],
        price=row["price"],
        qty=row["qty"],
        listing_status=row["status"],
        **details,
    )


def _mark_ended(item_ids: list[str]) -> int:
    if not item_ids:
        return 0
    with _conn() as conn:
        cur = conn.cursor()
        cur.executemany(
            "UPDATE listings SET status = %s, synced_at = NOW() WHERE ebay_item_id = %s",
            [("ended", item_id) for item_id in item_ids],
        )
        ended = cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(item_ids)
        conn.commit()
        cur.close()
    return ended


def sync(*, enrich_details: bool = False, incremental: bool = False) -> dict[str, object]:
    """Mirror live listings. Incremental refresh only writes changed rows."""
    client = EbayClient()
    if client.environment != "production":
        raise RuntimeError("EBAY_API_ENV must be production for live listings")
    ensure_columns()
    known = listing_snapshots()
    used_events = False
    rows = []
    if incremental:
        last = _parse_meta_time(get_meta(LISTINGS_META))
        if last and _utc_now() - last <= INCREMENTAL_MAX:
            try:
                rows = [_row_from_xml(item) for item in fetch_seller_events(client, last - OVERLAP)]
                rows = [row for row in rows if row]
                used_events = True
            except Exception:
                used_events = False
                rows = []
    if not used_events:
        rows = [_row_from_xml(item) for item in fetch_active_pages(client)]
        rows = [row for row in rows if row]

    seen: set[str] = set()
    updated = 0
    skipped = 0
    ended = 0
    new_skus: list[str] = []
    for row in rows:
        item_id = row["ebay_item_id"]
        seen.add(item_id)
        existing = known.get(item_id)
        incoming = {
            "title": row["title"],
            "sku": (row["sku"] or "").strip(),
            "status": row["status"],
            "qty": int(Decimal(str(row["qty"] or 0))),
            "price": row["price"],
        }
        if existing and _same_listing(existing, incoming):
            skipped += 1
            continue
        _write_listing(client, row, enrich_details=enrich_details, existing=existing)
        updated += 1
        sku = incoming["sku"]
        if sku and not existing:
            new_skus.append(sku)
        if row["status"] == "ended" and (not existing or existing.get("status") != "ended"):
            ended += 1

    if not used_events:
        stale = [item_id for item_id in known if known[item_id]["status"] == "active" and item_id not in seen]
        if stale:
            ended += _mark_ended(stale)
            updated += len(stale)

    set_meta(LISTINGS_META, _utc_now().isoformat())
    home = counts()
    return {
        "imported": updated,
        "updated": updated,
        "skipped": skipped,
        "ended": ended,
        "checked": len(rows),
        "incremental": used_events,
        "new_skus": new_skus,
        **home,
    }


def _apply_details(sku: str, extra: dict, *, listing_status: str = "active") -> None:
    existing = get_item(sku)
    apply_listing_to_item(
        sku,
        title=str(extra.get("title") or (existing or {}).get("title") or sku),
        price=(existing or {}).get("ask_price"),
        qty=(existing or {}).get("qty"),
        listing_status=listing_status,
        description=str(extra.get("description") or ""),
        condition_id=str(extra.get("condition_id") or ""),
        ebay_category_id=str(extra.get("ebay_category_id") or ""),
        ebay_category_name=str(extra.get("ebay_category_name") or ""),
        brand=str(extra.get("brand") or ""),
        picture_urls=list(extra.get("picture_urls") or []),
        item_specifics=extra.get("item_specifics") or None,
    )


def pull_item_from_ebay(sku: str) -> dict[str, object]:
    """GetItem for one SKU: description, photos, and all item specifics."""
    item = get_item(sku)
    if item is None:
        raise ValueError(f"Unknown SKU {sku}")
    listing_id = ""
    listing_status = "active"
    for row in item.get("listings") or []:
        listing_id = row.get("ebay_item_id") or ""
        listing_status = row.get("status") or "active"
        if row.get("status") == "active":
            break
    if not listing_id:
        raise ValueError("No eBay listing is linked to this SKU")
    from ebay_client import EbayClient

    extra = get_listing_details(EbayClient(), listing_id)
    _apply_details(sku, extra, listing_status=listing_status)
    return extra


def enrich_skus(skus: list[str]) -> dict[str, int]:
    """GetItem only for the given SKUs (new listings from an incremental refresh)."""
    codes = [sku.strip() for sku in skus if sku and sku.strip()]
    pulled = 0
    failed = 0
    for sku in codes:
        try:
            pull_item_from_ebay(sku)
            pulled += 1
        except Exception:
            failed += 1
    return {"pulled": pulled, "failed": failed, "queued": len(codes)}


def enrich_missing_details(*, limit: int = 0) -> dict[str, int]:
    """Background GetItem for listed SKUs that still lack description or specifics."""
    from ebay_client import EbayClient

    client = EbayClient()
    if client.environment != "production":
        return {"pulled": 0, "failed": 0, "queued": 0}
    rows = items_needing_ebay_details()
    if limit:
        rows = rows[:limit]
    pulled = 0
    failed = 0
    for row in rows:
        try:
            extra = get_listing_details(client, row["ebay_item_id"])
            _apply_details(row["sku"], extra, listing_status="active")
            pulled += 1
        except Exception:
            failed += 1
    return {"pulled": pulled, "failed": failed, "queued": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync live eBay listings into MySQL")
    parser.add_argument(
        "--details",
        action="store_true",
        help="Also GetItem descriptions, item specifics, and all photos (slow)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only fetch listings changed since the last refresh",
    )
    args = parser.parse_args()
    result = sync(enrich_details=args.details, incremental=args.incremental)
    print(
        f"Live listings: {result['updated']} updated, "
        f"{result['skipped']} unchanged, "
        f"{result['ended']} ended, "
        f"{result['listings_active']} on home."
    )


if __name__ == "__main__":
    main()
