"""Pull live eBay orders into MySQL. No buyer fields.

Uses Production user token (sell.fulfillment.readonly).
Fulfillment getOrders only allows a 90-day creation window per call.

Usage:
    python scripts/sync_orders.py
    python scripts/sync_orders.py --since 2026-01-01
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from ebay_client import EbayClient  # noqa: E402
from store_app.store import counts, upsert_order  # noqa: E402

WINDOW_DAYS = 89


def _windows(since: date) -> list[tuple[str, str]]:
    start = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    out: list[tuple[str, str]] = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(days=WINDOW_DAYS), end)
        out.append(
            (
                cursor.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                nxt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            )
        )
        cursor = nxt
    return out


def _sold_on(value: str) -> str | None:
    if not value:
        return None
    return value[:10]


def fetch_orders(client: EbayClient, since: date) -> list[dict]:
    orders: list[dict] = []
    for start, end in _windows(since):
        offset = 0
        while True:
            payload = client.api_get(
                "/sell/fulfillment/v1/order",
                {
                    "limit": 200,
                    "offset": offset,
                    "filter": f"creationdate:[{start}..{end}]",
                },
            )
            page = payload.get("orders") or []
            orders.extend(page)
            offset += len(page)
            total = int(payload.get("total") or 0)
            if offset >= total or not page:
                break
    return orders


def sync(since: date) -> dict[str, int]:
    client = EbayClient()
    if client.environment != "production":
        raise SystemExit("EBAY_API_ENV must be production for live orders")
    imported = 0
    for order in fetch_orders(client, since):
        order_id = str(order.get("legacyOrderId") or order.get("orderId") or "").strip()
        sold_on = _sold_on(str(order.get("creationDate") or ""))
        if not order_id:
            continue
        for line in order.get("lineItems") or []:
            cost = line.get("lineItemCost") or {}
            upsert_order(
                order_id=order_id,
                sku=str(line.get("sku") or "").strip(),
                ebay_item_id=str(line.get("legacyItemId") or "").strip(),
                sold_on=sold_on,
                qty=line.get("quantity") or 1,
                sold_for=cost.get("value"),
            )
            imported += 1
    home = counts()
    return {"imported": imported, "orders": home["orders"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull live eBay orders into MySQL.")
    parser.add_argument("--since", default="2026-01-01")
    args = parser.parse_args()
    since = date.fromisoformat(args.since)
    result = sync(since)
    print(f"Live orders: {result['imported']} line(s) upserted, {result['orders']} in MySQL.")


if __name__ == "__main__":
    main()
