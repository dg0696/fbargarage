"""FastAPI UI. Bind 127.0.0.1 locally or 0.0.0.0 on TrueNAS."""

from __future__ import annotations

import sys
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER, HTTP_404_NOT_FOUND

from store_app import __version__
from store_app.listing_fields import CONDITIONS
from store_app.photos import photo_root, save_upload
from store_app.store import (
    add_item_photo,
    api_listings,
    api_orders,
    counts,
    batch_delete_items,
    batch_update_items,
    delete_item,
    delete_item_photo,
    get_item,
    get_listing,
    list_item_photos,
    mark_listing_ended,
    ping,
    query_string,
    search_items,
    search_listings,
    update_listing_offer,
    upsert_item,
    upsert_listing,
)
from store_app.reporting import (
    generate_month,
    list_months,
    month_files,
    read_report,
    sqlite_ready,
)
from store_app.streams import CATEGORIES, INVENTORY_FILTERS, ITEM_STATUSES

PACKAGE_DIR = Path(__file__).resolve().parent
_ROOT = PACKAGE_DIR.parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_SCRIPTS / "lib") not in sys.path:
    sys.path.insert(0, str(_SCRIPTS / "lib"))
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
STATIC_DIR = PACKAGE_DIR / "static"
_ebay_pull_lock = threading.Lock()


def _run_in_background(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _enrich_skus_in_background(skus: list) -> None:
    if not skus:
        return
    if not _ebay_pull_lock.acquire(blocking=False):
        return
    try:
        from sync_listings import enrich_skus

        enrich_skus(skus)
    except Exception:
        pass
    finally:
        _ebay_pull_lock.release()


def _pull_skus_in_background(skus: list) -> None:
    from sync_listings import pull_item_from_ebay

    for code in skus:
        try:
            pull_item_from_ebay(code)
        except Exception:
            continue


def _item_or_404(sku: str) -> dict:
    item = get_item(sku)
    if item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Unknown SKU {sku}")
    return item


def _listing_or_404(ebay_item_id: str) -> dict:
    listing = get_listing(ebay_item_id)
    if listing is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Unknown listing {ebay_item_id}")
    return listing


def _safe_next(next_path: str, fallback: str) -> str:
    allowed = next_path in {"/", "/listings", "/inventory"} or next_path.startswith(
        ("/listings?", "/inventory?", "/items/")
    )
    if allowed:
        if "://" in next_path or "//" in next_path[1:]:
            return fallback
        return next_path
    return fallback


def _form_ids(values: Optional[List[str]]) -> List[str]:
    return [value.strip() for value in (values or []) if value and value.strip()]


def _photo_list(uploads: Optional[List[UploadFile]]) -> List[UploadFile]:
    return [upload for upload in (uploads or []) if upload and upload.filename]


def _save_photos(sku: str, uploads: Optional[List[UploadFile]]) -> int:
    saved = 0
    existing = len(list_item_photos(sku))
    for upload in _photo_list(uploads):
        filename = save_upload(sku, upload, existing_count=existing + saved)
        add_item_photo(sku, filename)
        saved += 1
    return saved


def _ebay_write_error(exc: Exception) -> str:
    text = str(exc)
    lower = text.lower()
    if any(word in lower for word in ("scope", "unauthorized", "insufficient", "access denied", "invalid iaf")):
        return (
            "eBay write access missing. Run python scripts/ebay_user_oauth.py "
            "then python scripts/store_ebay_secrets.py --export-docker"
        )
    return ("eBay update failed: " + text)[:180]


def create_app() -> FastAPI:
    app = FastAPI(title="f-bargarage", version=__version__, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.mount("/item-photos", StaticFiles(directory=str(photo_root())), name="item-photos")

    @app.get("/health")
    def health() -> dict[str, object]:
        try:
            db = ping()
            reachable = True
        except Exception as exc:
            db = {"error": str(exc)}
            reachable = False
        return {
            "ok": reachable,
            "version": __version__,
            "store": "f-bargarage",
            "db": db,
        }

    @app.get("/api/listings")
    def listings_api(stream: str = "", status: str = "active") -> dict[str, object]:
        return {"listings": api_listings(stream=stream, status=status)}

    @app.get("/api/listings/{sku}")
    def listing_api(sku: str) -> dict[str, object]:
        rows = [row for row in api_listings(status="all") if row.get("sku") == sku]
        if not rows:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Unknown SKU {sku}")
        return rows[0]

    @app.get("/api/orders")
    def orders_api(since: str = "") -> dict[str, object]:
        return {"orders": api_orders(since=since)}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, ok: Optional[str] = None, err: Optional[str] = None) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "home.html",
            {
                "title": "Home",
                "nav": "home",
                "version": __version__,
                "counts": counts(),
                "ok": ok,
                "err": err,
            },
        )

    @app.get("/inventory", response_class=HTMLResponse)
    def inventory(
        request: Request,
        q: str = "",
        category: str = "",
        status: str = "available",
        page: int = 1,
        ok: Optional[str] = None,
        err: Optional[str] = None,
    ) -> HTMLResponse:
        result = search_items(q=q.strip(), category=category, status=status, page=page)
        query = query_string(q=q, category=category, status=status)
        return TEMPLATES.TemplateResponse(
            request,
            "inventory.html",
            {
                "title": "Inventory",
                "nav": "inventory",
                "version": __version__,
                "q": q,
                "category": category,
                "status": status,
                "categories": CATEGORIES,
                "filters": INVENTORY_FILTERS,
                "statuses": ITEM_STATUSES,
                "ok": ok,
                "err": err,
                "query": query,
                **result,
            },
        )

    @app.post("/inventory/batch")
    def inventory_batch(
        action: str = Form(...),
        value: str = Form(""),
        sku: Optional[List[str]] = Form(None),
        next_path: str = Form("/inventory", alias="next"),
    ) -> RedirectResponse:
        dest = _safe_next(next_path, "/inventory")
        skus = _form_ids(sku)
        if not skus:
            return RedirectResponse(
                f"{dest}{'&' if '?' in dest else '?'}err={quote_plus('Select at least one item')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            if action == "status":
                count = batch_update_items(skus, status=value)
                message = f"Set status on {count} items"
            elif action == "category":
                count = batch_update_items(skus, category=value)
                message = f"Set category on {count} items"
            elif action == "location":
                count = batch_update_items(skus, location=value)
                message = f"Set location on {count} items"
            elif action == "remove":
                count = batch_delete_items(skus)
                message = f"Removed {count} items"
            elif action == "pull_ebay":
                _run_in_background(_pull_skus_in_background, list(skus))
                message = (
                    f"Pulling eBay fields for {len(skus)} items in the background. "
                    "Open an item in a minute to see manufacturer, model, and sizes."
                )
            else:
                raise ValueError("Unknown batch action")
        except ValueError as exc:
            return RedirectResponse(
                f"{dest}{'&' if '?' in dest else '?'}err={quote_plus(str(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        sep = "&" if "?" in dest else "?"
        return RedirectResponse(
            f"{dest}{sep}ok={quote_plus(message)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.get("/inventory/add", response_class=HTMLResponse)
    def inventory_add_page(
        request: Request,
        ok: Optional[str] = None,
        err: Optional[str] = None,
    ) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "inventory_add.html",
            {
                "title": "Add to inventory",
                "nav": "add",
                "version": __version__,
                "categories": CATEGORIES,
                "conditions": CONDITIONS,
                "ok": ok,
                "err": err,
            },
        )

    @app.post("/inventory/add")
    def inventory_add(
        sku: str = Form(...),
        title: str = Form(...),
        category: str = Form("other"),
        qty: str = Form("1"),
        cost: str = Form(""),
        ask_price: str = Form(""),
        location: str = Form(""),
        notes: str = Form(""),
        description: str = Form(""),
        condition_id: str = Form(""),
        ebay_category_id: str = Form(""),
        ebay_category_name: str = Form(""),
        brand: str = Form(""),
        list_now: str = Form(""),
        photos: Optional[List[UploadFile]] = File(None),
    ) -> RedirectResponse:
        sku_clean = sku.strip()
        try:
            upsert_item(
                sku=sku_clean,
                title=title,
                category=category,
                qty=qty,
                cost=cost,
                ask_price=ask_price,
                location=location,
                notes=notes,
                description=description,
                condition_id=condition_id,
                ebay_category_id=ebay_category_id,
                ebay_category_name=ebay_category_name,
                brand=brand,
            )
            _save_photos(sku_clean, photos)
        except ValueError as exc:
            return RedirectResponse(
                f"/inventory/add?err={quote_plus(str(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        dest = f"/items/{quote_plus(sku_clean)}"
        if list_now:
            try:
                from store_app.ebay_list import list_item_on_ebay

                new_id = list_item_on_ebay(sku_clean)
                return RedirectResponse(
                    f"{dest}?ok={quote_plus('Added and listed as ' + new_id)}",
                    status_code=HTTP_303_SEE_OTHER,
                )
            except Exception as exc:
                return RedirectResponse(
                    f"{dest}?err={quote_plus('Saved, but list failed: ' + _ebay_write_error(exc))}",
                    status_code=HTTP_303_SEE_OTHER,
                )
        return RedirectResponse(
            f"{dest}?ok={quote_plus('Added ' + sku_clean)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/inventory/suggest")
    async def inventory_suggest(
        title: str = Form(""),
        notes: str = Form(""),
        description: str = Form(""),
        photos: Optional[List[UploadFile]] = File(None),
    ) -> JSONResponse:
        images: list[bytes] = []
        for upload in _photo_list(photos):
            blob = await upload.read()
            if blob:
                images.append(blob)
        try:
            from listing_assist import draft_listing

            payload = draft_listing(title=title, notes=notes, description=description, images=images)
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)[:240]}, status_code=400)
        return JSONResponse({"ok": True, **payload})

    @app.get("/items/{sku}", response_class=HTMLResponse)
    def item_page(
        request: Request,
        sku: str,
        ok: Optional[str] = None,
        err: Optional[str] = None,
    ) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            request,
            "item.html",
            {
                "title": "Item",
                "nav": "inventory",
                "version": __version__,
                "item": _item_or_404(sku),
                "categories": CATEGORIES,
                "statuses": ITEM_STATUSES,
                "conditions": CONDITIONS,
                "ok": ok,
                "err": err,
                "end_reasons": ("NotAvailable", "Incorrect", "LostOrBroken", "OtherListingError"),
            },
        )

    @app.post("/items/{sku}")
    def item_save(
        sku: str,
        title: str = Form(...),
        category: str = Form("other"),
        qty: str = Form("1"),
        cost: str = Form(""),
        ask_price: str = Form(""),
        location: str = Form(""),
        status: str = Form("on-hand"),
        notes: str = Form(""),
        cogs_item_id: str = Form(""),
        cogs_build_id: str = Form(""),
        description: str = Form(""),
        condition_id: str = Form(""),
        ebay_category_id: str = Form(""),
        ebay_category_name: str = Form(""),
        brand: str = Form(""),
        photos: Optional[List[UploadFile]] = File(None),
    ) -> RedirectResponse:
        item = _item_or_404(sku)
        try:
            upsert_item(
                sku=sku,
                title=title,
                category=category,
                qty=qty,
                cost=cost,
                ask_price=ask_price,
                location=location,
                status=status,
                notes=notes,
                cogs_item_id=cogs_item_id,
                cogs_build_id=cogs_build_id,
                description=description,
                condition_id=condition_id,
                ebay_category_id=ebay_category_id,
                ebay_category_name=ebay_category_name,
                brand=brand,
                item_specifics=item.get("item_specifics") or None,
            )
            _save_photos(sku, photos)
        except ValueError as exc:
            return RedirectResponse(
                f"/items/{quote_plus(sku)}?err={quote_plus(str(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            f"/items/{quote_plus(sku)}?ok={quote_plus('Saved')}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/items/{sku}/remove")
    def item_remove(sku: str, confirm: str = Form("")) -> RedirectResponse:
        _item_or_404(sku)
        if confirm.strip().upper() != "REMOVE":
            return RedirectResponse(
                f"/items/{quote_plus(sku)}?err={quote_plus('Type REMOVE to delete')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        delete_item(sku)
        return RedirectResponse(
            f"/inventory?ok={quote_plus('Removed ' + sku)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/items/{sku}/photos/{photo_id}/delete")
    def item_photo_delete(sku: str, photo_id: int) -> RedirectResponse:
        _item_or_404(sku)
        delete_item_photo(sku, photo_id)
        return RedirectResponse(
            f"/items/{quote_plus(sku)}?ok={quote_plus('Removed photo')}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/items/{sku}/suggest")
    def item_suggest(sku: str) -> RedirectResponse:
        item = _item_or_404(sku)
        images = []
        for photo in item.get("photos") or []:
            from store_app.photos import read_bytes

            try:
                images.append(read_bytes(sku, photo["filename"]))
            except FileNotFoundError:
                continue
        try:
            from listing_assist import draft_listing

            payload = draft_listing(
                title=item["title"],
                notes=item.get("notes") or "",
                description=item.get("description") or "",
                images=images,
            )
            draft = payload["suggested"]
            upsert_item(
                sku=sku,
                title=draft.get("title") or item["title"],
                category=item["category"],
                qty=item.get("qty") or 1,
                cost=item.get("cost") or "",
                ask_price=draft.get("ask_price") or item.get("ask_price") or "",
                location=item.get("location") or "",
                status=item.get("status") or "on-hand",
                notes=item.get("notes") or "",
                cogs_item_id=item.get("cogs_item_id") or "",
                cogs_build_id=item.get("cogs_build_id") or "",
                description=draft.get("description") or item.get("description") or "",
                condition_id=draft.get("condition_id") or item.get("condition_id") or "",
                ebay_category_id=draft.get("ebay_category_id") or item.get("ebay_category_id") or "",
                ebay_category_name=draft.get("ebay_category_name") or item.get("ebay_category_name") or "",
                brand=draft.get("brand") or item.get("brand") or "",
                item_specifics=item.get("item_specifics") or None,
            )
        except Exception as exc:
            return RedirectResponse(
                f"/items/{quote_plus(sku)}?err={quote_plus(str(exc)[:180])}",
                status_code=HTTP_303_SEE_OTHER,
            )
        extra = payload.get("errors") or []
        message = "Filled from eBay matches" + (" + AI" if payload.get("suggested", {}).get("source", "").startswith(("openai", "gemini")) else "")
        if extra:
            message += " — " + "; ".join(extra)[:120]
        return RedirectResponse(
            f"/items/{quote_plus(sku)}?ok={quote_plus(message)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/items/{sku}/ebay-pull")
    def item_ebay_pull(sku: str) -> RedirectResponse:
        _item_or_404(sku)
        try:
            from sync_listings import pull_item_from_ebay

            extra = pull_item_from_ebay(sku)
        except Exception as exc:
            return RedirectResponse(
                f"/items/{quote_plus(sku)}?err={quote_plus(_ebay_write_error(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        names = [str(row.get("name") or "") for row in (extra.get("item_specifics") or [])]
        message = "Pulled from eBay"
        if names:
            message += ": " + ", ".join(names[:8])
            if len(names) > 8:
                message += f" (+{len(names) - 8} more)"
        elif extra.get("description"):
            message += " description and photos"
        else:
            message += " — no extra item specifics on that listing"
        return RedirectResponse(
            f"/items/{quote_plus(sku)}?ok={quote_plus(message)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/items/{sku}/list")
    def item_list(
        sku: str,
        confirm: str = Form(""),
        next_path: str = Form("", alias="next"),
    ) -> RedirectResponse:
        _item_or_404(sku)
        dest = _safe_next(next_path, f"/items/{quote_plus(sku)}")
        sep = "&" if "?" in dest else "?"
        if confirm.strip().upper() != "LIST":
            return RedirectResponse(
                f"{dest}{sep}err={quote_plus('Type LIST to create the eBay listing')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            from store_app.ebay_list import list_item_on_ebay

            new_id = list_item_on_ebay(sku)
        except Exception as exc:
            return RedirectResponse(
                f"{dest}{sep}err={quote_plus(_ebay_write_error(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            f"{dest}{sep}ok={quote_plus('Listed on eBay as ' + new_id)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.get("/listings", response_class=HTMLResponse)
    def listings_page(
        request: Request,
        q: str = "",
        stream: str = "",
        status: str = "active",
        page: int = 1,
        ok: Optional[str] = None,
        err: Optional[str] = None,
    ) -> HTMLResponse:
        result = search_listings(q=q.strip(), stream=stream, status=status, page=page)
        query = query_string(q=q, stream=stream, status=status)
        return TEMPLATES.TemplateResponse(
            request,
            "listings.html",
            {
                "title": "Listings",
                "nav": "listings",
                "version": __version__,
                "q": q,
                "stream": stream,
                "status": status,
                "streams": CATEGORIES,
                "query": query,
                "ok": ok,
                "err": err,
                "end_reasons": ("NotAvailable", "Incorrect", "LostOrBroken", "OtherListingError"),
                **result,
            },
        )

    @app.get("/reports", response_class=HTMLResponse)
    def reports_page(
        request: Request,
        year: int = 0,
        month: int = 0,
        file: str = "",
        ok: Optional[str] = None,
        err: Optional[str] = None,
    ) -> HTMLResponse:
        today = date.today()
        if year < 1 or month < 1:
            previous = date(today.year, today.month, 1) - timedelta(days=1)
            year, month = previous.year, previous.month
        body = ""
        current_label = ""
        if file:
            try:
                body = read_report(file)
                current_label = file
            except (ValueError, FileNotFoundError):
                err = err or "Unknown report file"
        return TEMPLATES.TemplateResponse(
            request,
            "reports.html",
            {
                "title": "Reports",
                "nav": "reports",
                "version": __version__,
                "year": year,
                "month": month,
                "years": list(range(2025, today.year + 1)),
                "months": list(range(1, 13)),
                "files": month_files(year, month),
                "available_months": list_months(),
                "sqlite_ready": sqlite_ready(),
                "body": body,
                "current_label": current_label,
                "ok": ok,
                "err": err,
            },
        )

    @app.post("/reports/generate")
    def reports_generate(year: int = Form(...), month: int = Form(...)) -> RedirectResponse:
        dest = f"/reports?year={year}&month={month}"
        try:
            missing = generate_month(year, month)
        except Exception as exc:
            return RedirectResponse(
                f"{dest}&err={quote_plus(str(exc)[:180])}",
                status_code=HTTP_303_SEE_OTHER,
            )
        message = f"Generated {year:04d}-{month:02d}"
        if missing:
            message += " — " + "; ".join(missing)
        return RedirectResponse(
            f"{dest}&ok={quote_plus(message)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/ebay/refresh")
    def ebay_refresh(next_path: str = Form("/listings", alias="next")) -> RedirectResponse:
        dest = next_path if next_path in {"/", "/listings"} else "/listings"
        try:
            from sync_listings import sync as sync_listings
            from sync_orders import sync as sync_orders

            listings = sync_listings(enrich_details=False, incremental=True)
            orders = sync_orders()
            new_skus = list(listings.get("new_skus") or [])
            if new_skus:
                _run_in_background(_enrich_skus_in_background, new_skus)
            mode = "changed listings" if listings.get("incremental") else "full list, unchanged skipped"
            message = (
                f"eBay refresh ({mode}): {listings['updated']} updated, "
                f"{listings['skipped']} unchanged, {listings['ended']} ended, "
                f"{orders['imported']} order lines"
            )
            return RedirectResponse(
                f"{dest}?ok={quote_plus(message)}",
                status_code=HTTP_303_SEE_OTHER,
            )
        except Exception as exc:
            return RedirectResponse(
                f"{dest}?err={quote_plus('eBay refresh failed: ' + str(exc)[:180])}",
                status_code=HTTP_303_SEE_OTHER,
            )

    @app.post("/listings/batch")
    def listings_batch(
        action: str = Form(...),
        reason: str = Form("NotAvailable"),
        ebay_item_id: Optional[List[str]] = Form(None),
        next_path: str = Form("/listings", alias="next"),
    ) -> RedirectResponse:
        dest = _safe_next(next_path, "/listings")
        ids = _form_ids(ebay_item_id)
        sep = "&" if "?" in dest else "?"
        if not ids:
            return RedirectResponse(
                f"{dest}{sep}err={quote_plus('Select at least one listing')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        ok_count = 0
        errors: list[str] = []
        try:
            from ebay_client import EbayClient
            from trading import end_listing, relist_listing

            client = EbayClient()
        except Exception as exc:
            return RedirectResponse(
                f"{dest}{sep}err={quote_plus(_ebay_write_error(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        for item_id in ids:
            listing = get_listing(item_id)
            if listing is None:
                errors.append(f"{item_id} missing")
                continue
            try:
                if action == "end":
                    if listing["status"] != "active":
                        errors.append(f"{item_id} not active")
                        continue
                    end_listing(client, item_id, reason=reason)
                    mark_listing_ended(item_id)
                    ok_count += 1
                elif action == "relist":
                    if listing["status"] == "active":
                        errors.append(f"{item_id} already active")
                        continue
                    new_id = relist_listing(
                        client,
                        item_id,
                        sku=listing["sku"],
                        price=listing["price"] or None,
                        qty=listing["qty"] or 1,
                    )
                    upsert_listing(
                        ebay_item_id=new_id,
                        title=listing["title"],
                        sku=listing["sku"],
                        price=listing["price"] or None,
                        qty=listing["qty"] or 1,
                        status="active",
                        ebay_category=listing.get("ebay_category") or "",
                        image_url=listing.get("image_url") or "",
                    )
                    ok_count += 1
                else:
                    raise ValueError("Unknown batch action")
            except Exception as exc:
                errors.append(f"{item_id}: {_ebay_write_error(exc)}")
        if action not in {"end", "relist"}:
            return RedirectResponse(
                f"{dest}{sep}err={quote_plus('Unknown batch action')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        verb = "Ended" if action == "end" else "Relisted"
        message = f"{verb} {ok_count}"
        if errors:
            message += " — " + "; ".join(errors)[:160]
        key = "ok" if ok_count and not errors else ("err" if not ok_count else "ok")
        return RedirectResponse(
            f"{dest}{sep}{key}={quote_plus(message)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/listings/{ebay_item_id}/end")
    def listing_end(
        ebay_item_id: str,
        confirm: str = Form(""),
        reason: str = Form("NotAvailable"),
        next_path: str = Form("/listings", alias="next"),
    ) -> RedirectResponse:
        listing = _listing_or_404(ebay_item_id)
        dest = _safe_next(next_path, "/listings")
        if listing["status"] != "active":
            return RedirectResponse(
                f"{dest}?err={quote_plus('Listing is not active')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        if confirm.strip().upper() != "END":
            return RedirectResponse(
                f"{dest}?err={quote_plus('Type END to end the eBay listing')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            from ebay_client import EbayClient
            from trading import end_listing

            end_listing(EbayClient(), ebay_item_id, reason=reason)
            mark_listing_ended(ebay_item_id)
        except Exception as exc:
            return RedirectResponse(
                f"{dest}?err={quote_plus(_ebay_write_error(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            f"{dest}?ok={quote_plus('Ended listing ' + ebay_item_id)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/listings/{ebay_item_id}/revise")
    def listing_revise(
        ebay_item_id: str,
        price: str = Form(""),
        qty: str = Form(""),
        next_path: str = Form("/listings", alias="next"),
    ) -> RedirectResponse:
        listing = _listing_or_404(ebay_item_id)
        dest = _safe_next(next_path, "/listings")
        if listing["status"] != "active":
            return RedirectResponse(
                f"{dest}?err={quote_plus('Listing is not active')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            from ebay_client import EbayClient
            from trading import revise_price_qty

            revise_price_qty(EbayClient(), ebay_item_id, price=price or None, qty=qty or None)
            update_listing_offer(ebay_item_id, price=price or None, qty=qty or None)
        except Exception as exc:
            return RedirectResponse(
                f"{dest}?err={quote_plus(_ebay_write_error(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            f"{dest}?ok={quote_plus('Updated listing ' + ebay_item_id + ' on eBay')}",
            status_code=HTTP_303_SEE_OTHER,
        )

    @app.post("/listings/{ebay_item_id}/relist")
    def listing_relist(
        ebay_item_id: str,
        confirm: str = Form(""),
        next_path: str = Form("/listings", alias="next"),
    ) -> RedirectResponse:
        listing = _listing_or_404(ebay_item_id)
        dest = _safe_next(next_path, "/listings")
        if listing["status"] == "active":
            return RedirectResponse(
                f"{dest}?err={quote_plus('Listing is already active')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        if confirm.strip().upper() != "RELIST":
            return RedirectResponse(
                f"{dest}?err={quote_plus('Type RELIST to list this item again')}",
                status_code=HTTP_303_SEE_OTHER,
            )
        try:
            from ebay_client import EbayClient
            from trading import relist_listing

            new_id = relist_listing(
                EbayClient(),
                ebay_item_id,
                sku=listing["sku"],
                price=listing["price"] or None,
                qty=listing["qty"] or 1,
            )
            upsert_listing(
                ebay_item_id=new_id,
                title=listing["title"],
                sku=listing["sku"],
                price=listing["price"] or None,
                qty=listing["qty"] or 1,
                status="active",
                ebay_category=listing.get("ebay_category") or "",
                image_url=listing.get("image_url") or "",
            )
        except Exception as exc:
            return RedirectResponse(
                f"{dest}?err={quote_plus(_ebay_write_error(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            f"{dest}?ok={quote_plus('Relisted as ' + new_id)}",
            status_code=HTTP_303_SEE_OTHER,
        )

    return app


app = create_app()
