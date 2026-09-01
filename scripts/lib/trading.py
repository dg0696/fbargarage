"""Trading API XML calls (Seller Hub listings are not in the Inventory API)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape

import requests

from ebay_client import EbayClient

NS = {"e": "urn:ebay:apis:eBLBaseComponents"}
COMPAT = "1423"
END_REASONS = ("NotAvailable", "Incorrect", "LostOrBroken", "OtherListingError")


def xml_text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path, NS)
    return (found.text or "").strip() if found is not None else ""


def trading_call(
    client: EbayClient,
    call_name: str,
    inner_xml: str,
    *,
    fail_partial: bool = True,
) -> ET.Element:
    token = client.get_user_access_token()
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<{call_name}Request xmlns="urn:ebay:apis:eBLBaseComponents">'
        "<ErrorLanguage>en_US</ErrorLanguage>"
        f"{inner_xml}"
        f"</{call_name}Request>"
    )
    response = requests.post(
        f"{client.api_base}/ws/api.dll",
        data=xml.encode("utf-8"),
        headers={
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": COMPAT,
            "X-EBAY-API-CALL-NAME": call_name,
            "X-EBAY-API-IAF-TOKEN": token,
            "Content-Type": "text/xml",
        },
        timeout=90,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ack = xml_text(root, "e:Ack")
    if ack == "Failure" or (fail_partial and ack == "PartialFailure"):
        message = xml_text(root, "e:Errors/e:LongMessage") or xml_text(
            root, "e:Errors/e:ShortMessage"
        )
        raise RuntimeError(f"{call_name} {ack}: {message}")
    return root


def end_listing(client: EbayClient, ebay_item_id: str, reason: str = "NotAvailable") -> None:
    item_id = escape(str(ebay_item_id).strip())
    if not item_id:
        raise ValueError("eBay item ID is required")
    if reason not in END_REASONS:
        raise ValueError("Unknown ending reason")
    inner = f"<ItemID>{item_id}</ItemID><EndingReason>{reason}</EndingReason>"
    try:
        trading_call(client, "EndFixedPriceItem", inner)
    except RuntimeError as exc:
        text = str(exc).lower()
        if "fixed price" not in text and "endfixedpriceitem" not in text:
            raise
        trading_call(client, "EndItem", inner)


def revise_price_qty(
    client: EbayClient,
    ebay_item_id: str,
    *,
    price: str | Decimal | None = None,
    qty: str | int | None = None,
) -> None:
    item_id = escape(str(ebay_item_id).strip())
    if not item_id:
        raise ValueError("eBay item ID is required")
    parts = [f"<ItemID>{item_id}</ItemID>"]
    if price not in (None, ""):
        try:
            amount = Decimal(str(price))
        except InvalidOperation as exc:
            raise ValueError("Price must be a number") from exc
        if amount <= 0:
            raise ValueError("Price must be greater than zero")
        parts.append(f'<StartPrice currencyID="USD">{amount:.2f}</StartPrice>')
    if qty not in (None, ""):
        try:
            quantity = int(Decimal(str(qty)))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Qty must be a whole number") from exc
        if quantity < 1:
            raise ValueError("Qty must be at least 1. End the listing instead of setting zero.")
        parts.append(f"<Quantity>{quantity}</Quantity>")
    if len(parts) == 1:
        raise ValueError("Price or qty is required")
    trading_call(
        client,
        "ReviseInventoryStatus",
        "<InventoryStatus>" + "".join(parts) + "</InventoryStatus>",
    )


def relist_listing(
    client: EbayClient,
    ebay_item_id: str,
    *,
    sku: str = "",
    price: str | Decimal | None = None,
    qty: str | int | None = None,
) -> str:
    """Relist an ended Seller Hub listing. Returns the new eBay item ID."""
    item_id = escape(str(ebay_item_id).strip())
    if not item_id:
        raise ValueError("eBay item ID is required")
    fields = [f"<ItemID>{item_id}</ItemID>"]
    if sku.strip():
        fields.append(f"<SKU>{escape(sku.strip())}</SKU>")
    if qty not in (None, ""):
        try:
            quantity = int(Decimal(str(qty)))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Qty must be a whole number") from exc
        if quantity < 1:
            quantity = 1
        fields.append(f"<Quantity>{quantity}</Quantity>")
    if price not in (None, ""):
        try:
            amount = Decimal(str(price))
        except InvalidOperation as exc:
            raise ValueError("Price must be a number") from exc
        if amount > 0:
            fields.append(f'<StartPrice currencyID="USD">{amount:.2f}</StartPrice>')
    inner = "<Item>" + "".join(fields) + "</Item>"
    try:
        root = trading_call(client, "RelistFixedPriceItem", inner, fail_partial=False)
    except RuntimeError as exc:
        text = str(exc).lower()
        if "fixed price" not in text and "relistfixedpriceitem" not in text:
            raise
        root = trading_call(client, "RelistItem", inner, fail_partial=False)
    new_id = xml_text(root, "e:ItemID")
    if not new_id:
        message = xml_text(root, "e:Errors/e:LongMessage") or xml_text(
            root, "e:Errors/e:ShortMessage"
        )
        raise RuntimeError(message or "Relist did not return a new ItemID")
    return new_id
