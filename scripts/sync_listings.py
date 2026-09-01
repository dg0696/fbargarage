"""Pull live eBay listings into MySQL (Trading GetMyeBaySelling).

Traditional Seller Hub listings are not in the Inventory API.
Uses the Production user token from Windows Credential Manager.

Usage:
    python scripts/sync_listings.py
"""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from ebay_client import EbayClient  # noqa: E402
from store_app.store import _conn, counts, ensure_columns, upsert_listing  # noqa: E402
from trading import NS, trading_call, xml_text  # noqa: E402


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


def sync() -> dict[str, int]:
    client = EbayClient()
    if client.environment != "production":
        raise SystemExit("EBAY_API_ENV must be production for live listings")
    ensure_columns()
    rows = fetch_active_pages(client)
    seen: set[str] = set()
    imported = 0
    for item in rows:
        item_id = xml_text(item, "e:ItemID")
        title = xml_text(item, "e:Title")
        if not item_id or not title:
            continue
        seen.add(item_id)
        selling = item.find("e:SellingStatus", NS)
        qty = xml_text(item, "e:QuantityAvailable") or xml_text(item, "e:Quantity") or "0"
        price = xml_text(selling, "e:CurrentPrice") or xml_text(item, "e:StartPrice")
        upsert_listing(
            ebay_item_id=item_id,
            title=title,
            sku=xml_text(item, "e:SKU"),
            price=_money(price),
            qty=qty,
            status="active",
            ebay_category=xml_text(item, "e:PrimaryCategory/e:CategoryName"),
            watchers=xml_text(item, "e:WatchCount") or None,
            start_date=(xml_text(item, "e:ListingDetails/e:StartTime") or "")[:10] or None,
            end_date=(xml_text(item, "e:ListingDetails/e:EndTime") or "")[:10] or None,
            image_url=xml_text(item, "e:PictureDetails/e:GalleryURL")
            or xml_text(item, "e:PictureDetails/e:PictureURL"),
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
