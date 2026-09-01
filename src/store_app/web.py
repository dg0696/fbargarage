"""FastAPI UI. Bind 127.0.0.1 locally or 0.0.0.0 on TrueNAS."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER, HTTP_404_NOT_FOUND

from store_app import __version__
from store_app.store import (
    api_listings,
    api_orders,
    counts,
    delete_item,
    get_item,
    ping,
    query_string,
    search_items,
    search_listings,
    upsert_item,
)
from store_app.streams import CATEGORIES, ITEM_STATUSES

PACKAGE_DIR = Path(__file__).resolve().parent
_SCRIPTS = PACKAGE_DIR.parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_SCRIPTS / "lib") not in sys.path:
    sys.path.insert(0, str(_SCRIPTS / "lib"))
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
STATIC_DIR = PACKAGE_DIR / "static"


def _item_or_404(sku: str) -> dict:
    item = get_item(sku)
    if item is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail=f"Unknown SKU {sku}")
    return item


def create_app() -> FastAPI:
    app = FastAPI(title="f-bargarage", version=__version__, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
        status: str = "",
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
                "statuses": ITEM_STATUSES,
                "ok": ok,
                "err": err,
                "query": query,
                **result,
            },
        )

    @app.post("/inventory")
    def inventory_add(
        sku: str = Form(...),
        title: str = Form(...),
        category: str = Form("other"),
        qty: str = Form("1"),
        cost: str = Form(""),
        ask_price: str = Form(""),
        location: str = Form(""),
        notes: str = Form(""),
    ) -> RedirectResponse:
        try:
            upsert_item(
                sku=sku,
                title=title,
                category=category,
                qty=qty,
                cost=cost,
                ask_price=ask_price,
                location=location,
                notes=notes,
            )
        except ValueError as exc:
            return RedirectResponse(
                f"/inventory?err={quote_plus(str(exc))}",
                status_code=HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            f"/inventory?ok={quote_plus('Added ' + sku.strip())}",
            status_code=HTTP_303_SEE_OTHER,
        )

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
                "ok": ok,
                "err": err,
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
    ) -> RedirectResponse:
        _item_or_404(sku)
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
            )
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
                **result,
            },
        )

    @app.post("/ebay/refresh")
    def ebay_refresh(next_path: str = Form("/listings", alias="next")) -> RedirectResponse:
        dest = next_path if next_path in {"/", "/listings"} else "/listings"
        try:
            from sync_listings import sync as sync_listings
            from sync_orders import sync as sync_orders

            listings = sync_listings()
            orders = sync_orders(date(2026, 1, 1))
            message = (
                f"eBay refresh: {listings['imported']} listings, "
                f"{listings['ended']} ended, {orders['imported']} order lines"
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

    return app


app = create_app()
