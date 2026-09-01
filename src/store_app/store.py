"""MySQL reads and writes for store inventory and listings."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator, Optional
from urllib.parse import quote_plus

from store_app.streams import CATEGORIES, ITEM_STATUSES, stream_from_sku

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from credentials import db_name  # noqa: E402
from init_mysql import connect  # noqa: E402

PAGE_SIZE = 50
SKU_MAX = 64
TITLE_MAX = 512
LOCATION_MAX = 128


def pager_pages(page: int, pages: int, radius: int = 2) -> list[Optional[int]]:
    """Page numbers to render, with None standing in for an ellipsis gap."""
    pages = max(1, pages)
    page = min(max(1, page), pages)
    if pages <= 9:
        return list(range(1, pages + 1))
    start = max(1, page - radius)
    end = min(pages, page + radius)
    if start == 1:
        end = min(pages, max(end, 1 + radius * 2))
    if end == pages:
        start = max(1, min(start, pages - radius * 2))
    out: list[Optional[int]] = []
    if start > 1:
        out.append(1)
        if start > 2:
            out.append(None)
    out.extend(range(start, end + 1))
    if end < pages:
        if end < pages - 1:
            out.append(None)
        out.append(pages)
    return out


def _money(value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"{Decimal(str(value)):.2f}"


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Not a valid number")


def _qty(value: Any) -> Decimal:
    parsed = _dec(value)
    if parsed is None:
        return Decimal("1")
    if parsed < 0:
        raise ValueError("Quantity cannot be negative")
    return parsed


@contextmanager
def _conn() -> Iterator[Any]:
    conn = connect(database=db_name())
    try:
        yield conn
    finally:
        conn.close()


def ensure_columns() -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM listings LIKE 'image_url'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE listings ADD COLUMN image_url VARCHAR(1024) NULL")
            conn.commit()
        cur.close()


def ping() -> dict[str, str]:
    ensure_columns()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT VERSION()")
        version = cur.fetchone()[0]
        cur.close()
    return {"ok": "true", "version": str(version)}


def counts() -> dict[str, Any]:
    with _conn() as conn:
        cur = conn.cursor()
        out: dict[str, Any] = {}
        cur.execute("SELECT COUNT(*) FROM items WHERE status <> 'removed'")
        out["items"] = int(cur.fetchone()[0])
        cur.execute("SELECT status, COUNT(*) FROM items GROUP BY status")
        out["items_by_status"] = {row[0]: int(row[1]) for row in cur.fetchall()}
        cur.execute("SELECT category, COUNT(*) FROM items WHERE status <> 'removed' GROUP BY category")
        out["items_by_category"] = {row[0]: int(row[1]) for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM listings WHERE status = 'active'")
        out["listings_active"] = int(cur.fetchone()[0])
        cur.execute(
            "SELECT stream, COUNT(*) FROM listings WHERE status = 'active' GROUP BY stream"
        )
        out["listings_by_stream"] = {row[0]: int(row[1]) for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM orders")
        out["orders"] = int(cur.fetchone()[0])
        cur.close()
    return out


def _item_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        sku,
        title,
        category,
        qty,
        cost,
        ask_price,
        location,
        status,
        notes,
        cogs_item_id,
        cogs_build_id,
    ) = row
    return {
        "sku": sku,
        "title": title,
        "category": category,
        "qty": str(qty).rstrip("0").rstrip(".") if qty is not None else "0",
        "cost": _money(cost),
        "ask_price": _money(ask_price),
        "location": location or "",
        "status": status,
        "notes": notes or "",
        "cogs_item_id": cogs_item_id or "",
        "cogs_build_id": cogs_build_id or "",
    }


def search_items(
    *,
    q: str = "",
    category: str = "",
    status: str = "",
    page: int = 1,
) -> dict[str, Any]:
    page = max(1, page)
    clauses = ["1=1"]
    args: list[Any] = []
    if q:
        clauses.append("(sku LIKE %s OR title LIKE %s OR location LIKE %s)")
        like = f"%{q}%"
        args.extend([like, like, like])
    if category:
        clauses.append("category = %s")
        args.append(category)
    if status:
        clauses.append("status = %s")
        args.append(status)
    else:
        clauses.append("status <> 'removed'")
    where = " AND ".join(clauses)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM items WHERE {where}", args)
        total = int(cur.fetchone()[0])
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        offset = (page - 1) * PAGE_SIZE
        cur.execute(
            f"""
            SELECT sku, title, category, qty, cost, ask_price, location, status,
                   notes, cogs_item_id, cogs_build_id
            FROM items
            WHERE {where}
            ORDER BY updated_at DESC, sku
            LIMIT %s OFFSET %s
            """,
            [*args, PAGE_SIZE, offset],
        )
        items = [_item_row(row) for row in cur.fetchall()]
        cur.close()
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "pager": pager_pages(page, pages),
    }


def get_item(sku: str) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT sku, title, category, qty, cost, ask_price, location, status,
                   notes, cogs_item_id, cogs_build_id
            FROM items WHERE sku = %s
            """,
            (sku,),
        )
        row = cur.fetchone()
        listings: list[dict[str, Any]] = []
        if row:
            cur.execute(
                """
                SELECT ebay_item_id, title, price, qty, stream, status, url, image_url
                FROM listings WHERE sku = %s ORDER BY status, ebay_item_id
                """,
                (sku,),
            )
            listings = [
                {
                    "ebay_item_id": r[0],
                    "title": r[1],
                    "price": _money(r[2]),
                    "qty": r[3],
                    "stream": r[4],
                    "status": r[5],
                    "url": r[6] or f"https://www.ebay.com/itm/{r[0]}",
                    "image_url": r[7] or "",
                }
                for r in cur.fetchall()
            ]
        cur.close()
    if row is None:
        return None
    item = _item_row(row)
    item["listings"] = listings
    return item


def upsert_item(
    *,
    sku: str,
    title: str,
    category: str = "other",
    qty: Any = 1,
    cost: Any = None,
    ask_price: Any = None,
    location: str = "",
    status: str = "on-hand",
    notes: str = "",
    cogs_item_id: str = "",
    cogs_build_id: str = "",
) -> None:
    sku = sku.strip()
    title = title.strip()
    if not sku:
        raise ValueError("SKU is required")
    if len(sku) > SKU_MAX:
        raise ValueError("SKU is too long")
    if not title:
        raise ValueError("Title is required")
    if category not in CATEGORIES:
        raise ValueError("Unknown category")
    if status not in ITEM_STATUSES:
        raise ValueError("Unknown status")
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO items (
                sku, title, category, qty, cost, ask_price, location, status,
                notes, cogs_item_id, cogs_build_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                category = VALUES(category),
                qty = VALUES(qty),
                cost = VALUES(cost),
                ask_price = VALUES(ask_price),
                location = VALUES(location),
                status = VALUES(status),
                notes = VALUES(notes),
                cogs_item_id = VALUES(cogs_item_id),
                cogs_build_id = VALUES(cogs_build_id)
            """,
            (
                sku,
                title[:TITLE_MAX],
                category,
                _qty(qty),
                _dec(cost),
                _dec(ask_price),
                (location or "")[:LOCATION_MAX] or None,
                status,
                notes or None,
                cogs_item_id or None,
                cogs_build_id or None,
            ),
        )
        conn.commit()
        cur.close()


def delete_item(sku: str) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE sku = %s", (sku,))
        conn.commit()
        cur.close()


def search_listings(
    *,
    q: str = "",
    stream: str = "",
    status: str = "active",
    page: int = 1,
) -> dict[str, Any]:
    page = max(1, page)
    clauses = ["1=1"]
    args: list[Any] = []
    if q:
        clauses.append("(sku LIKE %s OR title LIKE %s OR ebay_item_id LIKE %s)")
        like = f"%{q}%"
        args.extend([like, like, like])
    if stream:
        clauses.append("stream = %s")
        args.append(stream)
    if status and status != "all":
        clauses.append("status = %s")
        args.append(status)
    where = " AND ".join(clauses)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM listings WHERE {where}", args)
        total = int(cur.fetchone()[0])
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        offset = (page - 1) * PAGE_SIZE
        cur.execute(
            f"""
            SELECT ebay_item_id, sku, title, price, qty, stream, status, url,
                   ebay_category, watchers, image_url
            FROM listings
            WHERE {where}
            ORDER BY stream, sku, ebay_item_id
            LIMIT %s OFFSET %s
            """,
            [*args, PAGE_SIZE, offset],
        )
        listings = [
            {
                "ebay_item_id": row[0],
                "sku": row[1] or "",
                "title": row[2],
                "price": _money(row[3]),
                "qty": row[4],
                "stream": row[5],
                "status": row[6],
                "url": row[7] or f"https://www.ebay.com/itm/{row[0]}",
                "ebay_category": row[8] or "",
                "watchers": row[9] if row[9] is not None else "",
                "image_url": row[10] or "",
            }
            for row in cur.fetchall()
        ]
        cur.close()
    return {
        "listings": listings,
        "total": total,
        "page": page,
        "pages": pages,
        "pager": pager_pages(page, pages),
    }


def upsert_listing(
    *,
    ebay_item_id: str,
    title: str,
    sku: str = "",
    price: Any = None,
    qty: Any = 0,
    status: str = "active",
    ebay_category: str = "",
    watchers: Any = None,
    start_date: Any = None,
    end_date: Any = None,
    image_url: str = "",
    cogs_item_id: str = "",
    cogs_build_id: str = "",
) -> None:
    sku = (sku or "").strip()
    stream = stream_from_sku(sku)
    url = f"https://www.ebay.com/itm/{ebay_item_id}"
    qty_int = int(Decimal(str(qty or 0)))
    watchers_int = None if watchers in (None, "") else int(watchers)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO listings (
                ebay_item_id, sku, title, price, qty, stream, status, url,
                image_url, ebay_category, watchers, start_date, end_date,
                cogs_item_id, cogs_build_id, synced_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                sku = VALUES(sku),
                title = VALUES(title),
                price = VALUES(price),
                qty = VALUES(qty),
                stream = VALUES(stream),
                status = VALUES(status),
                url = VALUES(url),
                image_url = VALUES(image_url),
                ebay_category = VALUES(ebay_category),
                watchers = VALUES(watchers),
                start_date = VALUES(start_date),
                end_date = VALUES(end_date),
                synced_at = NOW()
            """,
            (
                str(ebay_item_id),
                sku or None,
                title[:TITLE_MAX],
                _dec(price),
                qty_int,
                stream,
                status,
                url,
                (image_url or "").strip() or None,
                ebay_category or None,
                watchers_int,
                start_date,
                end_date,
                cogs_item_id or None,
                cogs_build_id or None,
            ),
        )
        conn.commit()
        cur.close()
    if sku:
        existing = get_item(sku)
        if existing is None:
            upsert_item(
                sku=sku,
                title=title,
                category=stream,
                qty=qty_int,
                ask_price=price,
                status="listed" if status == "active" else "on-hand",
            )


def api_listings(*, stream: str = "", status: str = "active") -> list[dict[str, Any]]:
    clauses = ["1=1"]
    args: list[Any] = []
    if stream:
        clauses.append("l.stream = %s")
        args.append(stream)
    if status and status != "all":
        clauses.append("l.status = %s")
        args.append(status)
    where = " AND ".join(clauses)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT l.sku, l.ebay_item_id, l.title, l.price, l.qty, l.stream,
                   l.status, l.url, i.cogs_item_id, i.cogs_build_id, l.image_url
            FROM listings l
            LEFT JOIN items i ON i.sku = l.sku
            WHERE {where}
            ORDER BY l.stream, l.sku, l.ebay_item_id
            """,
            args,
        )
        rows = [
            {
                "sku": row[0] or "",
                "ebay_item_id": row[1],
                "title": row[2],
                "price": _money(row[3]) or "0.00",
                "qty": row[4],
                "stream": row[5],
                "status": row[6],
                "url": row[7] or f"https://www.ebay.com/itm/{row[1]}",
                "cogs_item_id": row[8],
                "cogs_build_id": row[9],
                "image_url": row[10] or "",
            }
            for row in cur.fetchall()
        ]
        cur.close()
    return rows


def get_listing_by_sku(sku: str) -> Optional[dict[str, Any]]:
    rows = [row for row in api_listings(status="all") if row["sku"] == sku]
    return rows[0] if rows else None


def upsert_order(
    *,
    order_id: str,
    sku: str = "",
    ebay_item_id: str = "",
    sold_on: Any = None,
    qty: Any = 1,
    sold_for: Any = None,
    cogs_item_id: str = "",
    cogs_build_id: str = "",
) -> None:
    order_id = (order_id or "").strip()
    if not order_id:
        raise ValueError("order_id is required")
    sku = (sku or "").strip()
    ebay_item_id = (ebay_item_id or "").strip()
    qty_int = int(Decimal(str(qty or 1)))
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO orders (
                order_id, sku, ebay_item_id, sold_on, qty, sold_for,
                cogs_item_id, cogs_build_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                sku = VALUES(sku),
                ebay_item_id = VALUES(ebay_item_id),
                sold_on = VALUES(sold_on),
                qty = VALUES(qty),
                sold_for = VALUES(sold_for)
            """,
            (
                order_id,
                sku or None,
                ebay_item_id or None,
                sold_on,
                qty_int,
                _dec(sold_for),
                cogs_item_id or None,
                cogs_build_id or None,
            ),
        )
        if sku:
            cur.execute(
                """
                UPDATE items
                SET status = 'sold', qty = 0
                WHERE sku = %s AND status IN ('on-hand', 'listed')
                """,
                (sku,),
            )
        conn.commit()
        cur.close()


def api_orders(*, since: str = "") -> list[dict[str, Any]]:
    clauses = ["1=1"]
    args: list[Any] = []
    if since:
        clauses.append("sold_on >= %s")
        args.append(since)
    where = " AND ".join(clauses)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT order_id, sku, sold_on, qty, cogs_item_id, cogs_build_id
            FROM orders
            WHERE {where}
            ORDER BY sold_on DESC, order_id
            """,
            args,
        )
        rows = [
            {
                "order_id": row[0],
                "sku": row[1] or "",
                "sold_on": row[2].isoformat() if row[2] else "",
                "qty": row[3],
                "cogs_item_id": row[4],
                "cogs_build_id": row[5],
            }
            for row in cur.fetchall()
        ]
        cur.close()
    return rows


def query_string(**kwargs: str) -> str:
    return "&".join(f"{key}={quote_plus(value)}" for key, value in kwargs.items() if value)
