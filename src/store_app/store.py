"""MySQL reads and writes for store inventory and listings."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator, Optional
from urllib.parse import quote_plus

from store_app.listing_fields import (
    DEFAULT_CONDITION,
    brand_from_specifics,
    decode_specifics,
    encode_specifics,
    html_to_text,
    sort_specifics,
)
from store_app.photos import delete_file, delete_sku_files, photo_url, save_from_url
from store_app.streams import AVAILABLE_STATUSES, CATEGORIES, ITEM_STATUSES, stream_from_sku

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from credentials import db_name  # noqa: E402
from init_mysql import connect  # noqa: E402

PAGE_SIZE = 50
SKU_MAX = 64
TITLE_MAX = 512
LOCATION_MAX = 128
BRAND_MAX = 128
DESCRIPTION_MAX = 40000
ITEM_SELECT = (
    "sku, title, category, qty, cost, ask_price, location, status, notes, "
    "cogs_item_id, cogs_build_id, description, condition_id, "
    "ebay_category_id, ebay_category_name, brand, item_specifics"
)
_schema_ready = False


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
    ensure_columns()
    conn = connect(database=db_name())
    try:
        yield conn
    finally:
        conn.close()


def _add_column(cur: Any, table: str, name: str, ddl: str) -> None:
    cur.execute(f"SHOW COLUMNS FROM {table} LIKE %s", (name,))
    if cur.fetchone() is None:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def ensure_columns() -> None:
    global _schema_ready
    if _schema_ready:
        return
    conn = connect(database=db_name())
    try:
        cur = conn.cursor()
        _add_column(cur, "listings", "image_url", "image_url VARCHAR(1024) NULL")
        _add_column(cur, "items", "description", "description TEXT NULL")
        _add_column(cur, "items", "condition_id", "condition_id VARCHAR(16) NULL")
        _add_column(cur, "items", "ebay_category_id", "ebay_category_id VARCHAR(32) NULL")
        _add_column(cur, "items", "ebay_category_name", "ebay_category_name VARCHAR(128) NULL")
        _add_column(cur, "items", "brand", "brand VARCHAR(128) NULL")
        _add_column(cur, "items", "item_specifics", "item_specifics TEXT NULL")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS item_photos (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                sku VARCHAR(64) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                source_url VARCHAR(1024) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_item_photos_sku (sku)
            )
            """
        )
        _add_column(cur, "item_photos", "source_url", "source_url VARCHAR(1024) NULL")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                name VARCHAR(64) NOT NULL PRIMARY KEY,
                value VARCHAR(255) NOT NULL
            )
            """
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
    _schema_ready = True


def get_meta(name: str) -> str:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM app_meta WHERE name = %s", (name,))
        row = cur.fetchone()
        cur.close()
    return str(row[0]) if row and row[0] is not None else ""


def set_meta(name: str, value: str) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO app_meta (name, value) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE value = VALUES(value)
            """,
            (name, value),
        )
        conn.commit()
        cur.close()


def listing_snapshots() -> dict[str, dict[str, Any]]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ebay_item_id, sku, title, price, qty, status, watchers,
                   image_url, ebay_category
            FROM listings
            """
        )
        rows = {
            str(row[0]): {
                "ebay_item_id": str(row[0]),
                "sku": row[1] or "",
                "title": row[2] or "",
                "price": _money(row[3]),
                "qty": int(row[4] or 0),
                "status": row[5] or "",
                "watchers": "" if row[6] is None else str(row[6]),
                "image_url": row[7] or "",
                "ebay_category": row[8] or "",
            }
            for row in cur.fetchall()
        }
        cur.close()
    return rows


def latest_order_sold_on() -> Optional[Any]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(sold_on) FROM orders")
        row = cur.fetchone()
        cur.close()
    return row[0] if row else None


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
        description,
        condition_id,
        ebay_category_id,
        ebay_category_name,
        brand,
        item_specifics,
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
        "description": description or "",
        "condition_id": condition_id or DEFAULT_CONDITION,
        "ebay_category_id": ebay_category_id or "",
        "ebay_category_name": ebay_category_name or "",
        "brand": brand or "",
        "item_specifics": sort_specifics(item_specifics),
        "photos": [],
    }


def search_items(
    *,
    q: str = "",
    category: str = "",
    status: str = "available",
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
    if status in ("", "available"):
        placeholders = ", ".join(["%s"] * len(AVAILABLE_STATUSES))
        clauses.append(f"status IN ({placeholders})")
        args.extend(AVAILABLE_STATUSES)
    elif status != "all":
        clauses.append("status = %s")
        args.append(status)
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
            SELECT {ITEM_SELECT}
            FROM items
            WHERE {where}
            ORDER BY updated_at DESC, sku
            LIMIT %s OFFSET %s
            """,
            [*args, PAGE_SIZE, offset],
        )
        items = [_item_row(row) for row in cur.fetchall()]
        _attach_primary_images(cur, items)
        _attach_listing_state(cur, items)
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
            f"""
            SELECT {ITEM_SELECT}
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
        photos = list_item_photos(sku, cur=cur) if row else []
        cur.close()
    if row is None:
        return None
    item = _item_row(row)
    item["listings"] = listings
    item["photos"] = photos
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
    description: str = "",
    condition_id: str = "",
    ebay_category_id: str = "",
    ebay_category_name: str = "",
    brand: str = "",
    item_specifics: Any = None,
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
    description = (description or "")[:DESCRIPTION_MAX]
    condition = (condition_id or DEFAULT_CONDITION).strip() or DEFAULT_CONDITION
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO items (
                sku, title, category, qty, cost, ask_price, location, status,
                notes, cogs_item_id, cogs_build_id, description, condition_id,
                ebay_category_id, ebay_category_name, brand, item_specifics
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                cogs_build_id = VALUES(cogs_build_id),
                description = VALUES(description),
                condition_id = VALUES(condition_id),
                ebay_category_id = VALUES(ebay_category_id),
                ebay_category_name = VALUES(ebay_category_name),
                brand = VALUES(brand),
                item_specifics = COALESCE(VALUES(item_specifics), item_specifics)
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
                description or None,
                condition,
                (ebay_category_id or "").strip() or None,
                (ebay_category_name or "").strip() or None,
                (brand or "").strip()[:BRAND_MAX] or None,
                encode_specifics(item_specifics) if item_specifics is not None else None,
            ),
        )
        conn.commit()
        cur.close()


def list_item_photos(sku: str, *, cur: Any = None) -> list[dict[str, Any]]:
    def _rows(cursor: Any) -> list[dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, filename, sort_order
            FROM item_photos WHERE sku = %s
            ORDER BY sort_order, id
            """,
            (sku,),
        )
        return [
            {
                "id": row[0],
                "filename": row[1],
                "sort_order": row[2],
                "url": photo_url(sku, row[1]),
            }
            for row in cursor.fetchall()
        ]

    if cur is not None:
        return _rows(cur)
    with _conn() as conn:
        cursor = conn.cursor()
        photos = _rows(cursor)
        cursor.close()
    return photos


def _attach_first_photos(cur: Any, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    skus = [item["sku"] for item in items]
    placeholders = ", ".join(["%s"] * len(skus))
    cur.execute(
        f"""
        SELECT sku, id, filename, sort_order
        FROM item_photos
        WHERE sku IN ({placeholders})
        ORDER BY sku, sort_order, id
        """,
        skus,
    )
    first: dict[str, dict[str, Any]] = {}
    for sku, photo_id, filename, sort_order in cur.fetchall():
        if sku in first:
            continue
        first[sku] = {
            "id": photo_id,
            "filename": filename,
            "sort_order": sort_order,
            "url": photo_url(sku, filename),
        }
    for item in items:
        photo = first.get(item["sku"])
        item["photos"] = [photo] if photo else []


def _attach_listing_state(cur: Any, items: list[dict[str, Any]]) -> None:
    for item in items:
        item["has_active_listing"] = False
        item["listing_url"] = ""
        item["post_state"] = "not posted"
    if not items:
        return
    skus = [item["sku"] for item in items]
    placeholders = ", ".join(["%s"] * len(skus))
    cur.execute(
        f"""
        SELECT sku, status, ebay_item_id, url
        FROM listings
        WHERE sku IN ({placeholders})
        ORDER BY status = 'active' DESC, ebay_item_id
        """,
        skus,
    )
    first: dict[str, dict[str, Any]] = {}
    for sku, status, ebay_item_id, url in cur.fetchall():
        info = first.setdefault(
            sku,
            {
                "has_active_listing": False,
                "listing_url": url or f"https://www.ebay.com/itm/{ebay_item_id}",
            },
        )
        if status == "active":
            info["has_active_listing"] = True
            info["listing_url"] = url or f"https://www.ebay.com/itm/{ebay_item_id}"
    for item in items:
        info = first.get(item["sku"])
        if item.get("status") == "sold":
            item["post_state"] = "sold"
        elif info and info.get("has_active_listing"):
            item["has_active_listing"] = True
            item["listing_url"] = info.get("listing_url") or ""
            item["post_state"] = "active"
        else:
            item["post_state"] = "not posted"


def _attach_primary_images(cur: Any, items: list[dict[str, Any]]) -> None:
    _attach_first_photos(cur, items)
    missing = [item["sku"] for item in items if not item.get("photos")]
    if not missing:
        return
    placeholders = ", ".join(["%s"] * len(missing))
    cur.execute(
        f"""
        SELECT sku, image_url
        FROM listings
        WHERE sku IN ({placeholders}) AND image_url IS NOT NULL AND image_url <> ''
        ORDER BY status = 'active' DESC, ebay_item_id
        """,
        missing,
    )
    first: dict[str, str] = {}
    for sku, url in cur.fetchall():
        if sku not in first:
            first[sku] = url
    for item in items:
        if item.get("photos"):
            continue
        url = first.get(item["sku"])
        if url:
            item["photos"] = [{"id": 0, "filename": "", "sort_order": 0, "url": url}]


def add_item_photo(sku: str, filename: str, source_url: str = "") -> int:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM item_photos WHERE sku = %s",
            (sku,),
        )
        order = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO item_photos (sku, filename, sort_order, source_url)
            VALUES (%s, %s, %s, %s)
            """,
            (sku, filename, order, (source_url or "").strip() or None),
        )
        photo_id = int(cur.lastrowid)
        conn.commit()
        cur.close()
    return photo_id


def photo_source_urls(sku: str) -> set[str]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT source_url FROM item_photos WHERE sku = %s AND source_url IS NOT NULL",
            (sku,),
        )
        urls = {str(row[0]) for row in cur.fetchall() if row[0]}
        cur.close()
    return urls


def import_remote_photos(sku: str, urls: list[str]) -> int:
    saved = 0
    known = photo_source_urls(sku)
    existing = len(list_item_photos(sku))
    for url in urls:
        url = (url or "").strip()
        if not url or url in known:
            continue
        if existing + saved >= 12:
            break
        try:
            filename = save_from_url(sku, url, existing_count=existing + saved)
        except Exception:
            continue
        add_item_photo(sku, filename, source_url=url)
        known.add(url)
        saved += 1
    return saved


def apply_listing_to_item(
    sku: str,
    *,
    title: str,
    price: Any = None,
    qty: Any = None,
    listing_status: str = "active",
    ebay_category_id: str = "",
    ebay_category_name: str = "",
    condition_id: str = "",
    description: str = "",
    brand: str = "",
    picture_urls: list[str] | None = None,
    item_specifics: Any = None,
) -> None:
    sku = (sku or "").strip()
    if not sku:
        return
    existing = get_item(sku)
    plain = html_to_text(description) if description else ""
    status = "listed" if listing_status == "active" else (existing["status"] if existing else "on-hand")
    specifics = decode_specifics(item_specifics) if item_specifics is not None else None
    if specifics == []:
        specifics = None
    resolved_brand = brand or brand_from_specifics(specifics or (existing or {}).get("item_specifics"))
    if existing is None:
        upsert_item(
            sku=sku,
            title=title or sku,
            category=stream_from_sku(sku),
            qty=qty if qty not in (None, "") else 1,
            ask_price=price,
            status=status,
            description=plain,
            condition_id=condition_id,
            ebay_category_id=ebay_category_id,
            ebay_category_name=ebay_category_name,
            brand=resolved_brand,
            item_specifics=specifics,
        )
    else:
        upsert_item(
            sku=sku,
            title=title or existing["title"],
            category=existing["category"],
            qty=qty if qty not in (None, "") else existing["qty"],
            cost=existing.get("cost") or "",
            ask_price=price if price not in (None, "") else existing.get("ask_price") or "",
            location=existing.get("location") or "",
            status=status,
            notes=existing.get("notes") or "",
            cogs_item_id=existing.get("cogs_item_id") or "",
            cogs_build_id=existing.get("cogs_build_id") or "",
            description=plain or existing.get("description") or "",
            condition_id=condition_id or existing.get("condition_id") or "",
            ebay_category_id=ebay_category_id or existing.get("ebay_category_id") or "",
            ebay_category_name=ebay_category_name or existing.get("ebay_category_name") or "",
            brand=resolved_brand or existing.get("brand") or "",
            item_specifics=specifics,
        )
    import_remote_photos(sku, picture_urls or [])


def items_needing_ebay_details() -> list[dict[str, str]]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT l.sku, l.ebay_item_id
            FROM listings l
            JOIN items i ON i.sku = l.sku
            WHERE l.status = 'active'
              AND l.sku IS NOT NULL
              AND l.sku <> ''
              AND (
                i.item_specifics IS NULL
                OR i.item_specifics = ''
                OR i.item_specifics = '[]'
                OR i.description IS NULL
                OR i.description = ''
              )
            ORDER BY l.sku, l.ebay_item_id
            """
        )
        seen: set[str] = set()
        rows: list[dict[str, str]] = []
        for sku, ebay_item_id in cur.fetchall():
            if sku in seen:
                continue
            seen.add(sku)
            rows.append({"sku": sku, "ebay_item_id": ebay_item_id})
        cur.close()
    return rows


def get_item_photo(sku: str, photo_id: int) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, filename, sort_order FROM item_photos WHERE sku = %s AND id = %s",
            (sku, photo_id),
        )
        row = cur.fetchone()
        cur.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "filename": row[1],
        "sort_order": row[2],
        "url": photo_url(sku, row[1]),
    }


def delete_item_photo(sku: str, photo_id: int) -> None:
    photo = get_item_photo(sku, photo_id)
    if photo is None:
        return
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM item_photos WHERE sku = %s AND id = %s", (sku, photo_id))
        conn.commit()
        cur.close()
    delete_file(sku, photo["filename"])


def delete_item(sku: str) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM item_photos WHERE sku = %s", (sku,))
        cur.execute("DELETE FROM items WHERE sku = %s", (sku,))
        conn.commit()
        cur.close()
    delete_sku_files(sku)


def batch_update_items(
    skus: list[str],
    *,
    status: str = "",
    category: str = "",
    location: str | None = None,
) -> int:
    cleaned = [sku.strip() for sku in skus if sku and sku.strip()]
    if not cleaned:
        return 0
    if status and status not in ITEM_STATUSES:
        raise ValueError("Unknown status")
    if category and category not in CATEGORIES:
        raise ValueError("Unknown category")
    fields: list[str] = []
    args: list[Any] = []
    if status:
        fields.append("status = %s")
        args.append(status)
    if category:
        fields.append("category = %s")
        args.append(category)
    if location is not None:
        fields.append("location = %s")
        args.append((location or "")[:LOCATION_MAX] or None)
    if not fields:
        raise ValueError("Pick a batch change")
    placeholders = ", ".join(["%s"] * len(cleaned))
    args.extend(cleaned)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE items SET {', '.join(fields)} WHERE sku IN ({placeholders})",
            args,
        )
        updated = cur.rowcount
        conn.commit()
        cur.close()
    return int(updated)


def batch_delete_items(skus: list[str]) -> int:
    cleaned = [sku.strip() for sku in skus if sku and sku.strip()]
    for sku in cleaned:
        delete_item(sku)
    return len(cleaned)


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


def first_active_listing_id() -> Optional[str]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ebay_item_id FROM listings
            WHERE status = 'active'
            ORDER BY synced_at DESC, ebay_item_id
            LIMIT 1
            """
        )
        row = cur.fetchone()
        cur.close()
    return str(row[0]) if row else None


def get_listing(ebay_item_id: str) -> Optional[dict[str, Any]]:
    item_id = str(ebay_item_id).strip()
    if not item_id:
        return None
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ebay_item_id, sku, title, price, qty, stream, status, url,
                   image_url, ebay_category
            FROM listings WHERE ebay_item_id = %s
            """,
            (item_id,),
        )
        row = cur.fetchone()
        cur.close()
    if row is None:
        return None
    return {
        "ebay_item_id": row[0],
        "sku": row[1] or "",
        "title": row[2],
        "price": _money(row[3]),
        "qty": row[4],
        "stream": row[5],
        "status": row[6],
        "url": row[7] or f"https://www.ebay.com/itm/{row[0]}",
        "image_url": row[8] or "",
        "ebay_category": row[9] or "",
    }


def mark_listing_ended(ebay_item_id: str) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE listings
            SET status = 'ended', synced_at = NOW()
            WHERE ebay_item_id = %s
            """,
            (str(ebay_item_id).strip(),),
        )
        conn.commit()
        cur.close()


def update_listing_offer(ebay_item_id: str, *, price: Any = None, qty: Any = None) -> None:
    fields: list[str] = ["synced_at = NOW()"]
    args: list[Any] = []
    if price not in (None, ""):
        fields.append("price = %s")
        args.append(_dec(price))
    if qty not in (None, ""):
        fields.append("qty = %s")
        args.append(int(Decimal(str(qty))))
    if len(args) == 0:
        return
    args.append(str(ebay_item_id).strip())
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE listings SET {', '.join(fields)} WHERE ebay_item_id = %s",
            args,
        )
        conn.commit()
        cur.close()


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
