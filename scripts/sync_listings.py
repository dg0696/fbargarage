"""Pull live eBay listings into MySQL (Trading GetMyeBaySelling).

Traditional Seller Hub listings are not in the Inventory API.
Uses the Production user token from Windows Credential Manager.

Usage:
    python scripts/sync_listings.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from ebay_client import EbayClient  # noqa: E402
from store_app.store import _conn, counts, ensure_columns, upsert_listing  # noqa: E402

NS = {"e": "urn:ebay:apis:eBLBaseComponents"}
COMPAT = "1423"


def _text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path, NS)
    return (found.text or "").strip() if found is not None else ""


def fetch_active_pages(client: EbayClient) -> list[ET.Element]:
    token = client.get_user_access_token()
    items: list[ET.Element] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyeBaySellingRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <ErrorLanguage>en_US</ErrorLanguage>
  <ActiveList>
    <Include>true</Include>
    <Pagination>
      <EntriesPerPage>200</EntriesPerPage>
      <PageNumber>{page}</PageNumber>
    </Pagination>
  </ActiveList>
  <DetailLevel>ReturnAll</DetailLevel>
</GetMyeBaySellingRequest>
"""
        response = requests.post(
            f"{client.api_base}/ws/api.dll",
            data=xml.encode("utf-8"),
            headers={
                "X-EBAY-API-SITEID": "0",
                "X-EBAY-API-COMPATIBILITY-LEVEL": COMPAT,
                "X-EBAY-API-CALL-NAME": "GetMyeBaySelling",
                "X-EBAY-API-IAF-TOKEN": token,
                "Content-Type": "text/xml",
            },
            timeout=90,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ack = _text(root, "e:Ack")
        if ack in {"Failure", "PartialFailure"}:
            message = _text(root, "e:Errors/e:LongMessage") or _text(root, "e:Errors/e:ShortMessage")
            raise RuntimeError(f"GetMyeBaySelling {ack}: {message}")
        pagination = root.find("e:ActiveList/e:PaginationResult", NS)
        total_pages = int(_text(pagination, "e:TotalNumberOfPages") or "1")
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


def sync() -> dict[str, int]:
    client = EbayClient()
    if client.environment != "production":
        raise SystemExit("EBAY_API_ENV must be production for live listings")
    ensure_columns()
    rows = fetch_active_pages(client)
    seen: set[str] = set()
    imported = 0
    for item in rows:
        item_id = _text(item, "e:ItemID")
        title = _text(item, "e:Title")
        if not item_id or not title:
            continue
        seen.add(item_id)
        selling = item.find("e:SellingStatus", NS)
        qty = _text(item, "e:QuantityAvailable") or _text(item, "e:Quantity") or "0"
        price = _text(selling, "e:CurrentPrice") or _text(item, "e:StartPrice")
        upsert_listing(
            ebay_item_id=item_id,
            title=title,
            sku=_text(item, "e:SKU"),
            price=_money(price),
            qty=qty,
            status="active",
            ebay_category=_text(item, "e:PrimaryCategory/e:CategoryName"),
            watchers=_text(item, "e:WatchCount") or None,
            start_date=(_text(item, "e:ListingDetails/e:StartTime") or "")[:10] or None,
            end_date=(_text(item, "e:ListingDetails/e:EndTime") or "")[:10] or None,
            image_url=_text(item, "e:PictureDetails/e:GalleryURL")
            or _text(item, "e:PictureDetails/e:PictureURL"),
        )
        imported += 1

    ended = 0
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ebay_item_id FROM listings WHERE status = %s", ("active",))
        stale = [row[0] for row in cur.fetchall() if str(row[0]) not in seen]
        if stale:
            cur.executemany(
                "UPDATE listings SET status = %s WHERE ebay_item_id = %s",
                [("ended", item_id) for item_id in stale],
            )
            ended = len(stale)
            conn.commit()
        cur.close()
    return {"imported": imported, "ended": ended, **counts()}


def main() -> None:
    result = sync()
    print(
        f"Live listings: {result['imported']} active, "
        f"{result['ended']} marked ended, "
        f"{result['listings_active']} on home."
    )


if __name__ == "__main__":
    main()
