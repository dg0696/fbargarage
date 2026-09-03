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


def fetch_seller_events(client: EbayClient, mod_from) -> list[ET.Element]:
    """Listings created, revised, or ended since mod_from (UTC datetime)."""
    stamp = escape(mod_from.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    root = trading_call(
        client,
        "GetSellerEvents",
        (
            f"<ModTimeFrom>{stamp}</ModTimeFrom>"
            "<IncludeWatchCount>true</IncludeWatchCount>"
            "<DetailLevel>ReturnAll</DetailLevel>"
        ),
        fail_partial=False,
    )
    return root.findall("e:ItemArray/e:Item", NS)


def listing_picture_urls(item: ET.Element | None) -> list[str]:
    if item is None:
        return []
    urls: list[str] = []
    details = item.find("e:PictureDetails", NS)
    if details is not None:
        for node in details.findall("e:PictureURL", NS):
            url = (node.text or "").strip()
            if url and url not in urls:
                urls.append(url)
    gallery = xml_text(item, "e:PictureDetails/e:GalleryURL")
    if gallery and gallery not in urls:
        urls.insert(0, gallery)
    return urls


def item_specific(item: ET.Element | None, name: str) -> str:
    if item is None:
        return ""
    wanted = name.strip().lower()
    for row in listing_item_specifics(item):
        if str(row["name"]).lower() == wanted:
            values = row.get("values") or []
            return str(values[0]) if values else ""
    return ""


def listing_item_specifics(item: ET.Element | None) -> list[dict[str, object]]:
    if item is None:
        return []
    out: list[dict[str, object]] = []
    for node in item.findall("e:ItemSpecifics/e:NameValueList", NS):
        name = xml_text(node, "e:Name").strip()
        values: list[str] = []
        for value_node in node.findall("e:Value", NS):
            text = (value_node.text or "").strip()
            if text and text not in values:
                values.append(text)
        if name and values:
            out.append({"name": name, "values": values})
    return out


def get_listing_details(client: EbayClient, ebay_item_id: str) -> dict[str, object]:
    item_id = escape(str(ebay_item_id).strip())
    if not item_id:
        raise ValueError("eBay item ID is required")
    root = trading_call(
        client,
        "GetItem",
        (
            f"<ItemID>{item_id}</ItemID>"
            "<IncludeItemSpecifics>true</IncludeItemSpecifics>"
            "<DetailLevel>ReturnAll</DetailLevel>"
        ),
        fail_partial=False,
    )
    item = root.find("e:Item", NS)
    specifics = listing_item_specifics(item)
    return {
        "title": xml_text(item, "e:Title"),
        "description": xml_text(item, "e:Description"),
        "condition_id": xml_text(item, "e:ConditionID"),
        "ebay_category_id": xml_text(item, "e:PrimaryCategory/e:CategoryID"),
        "ebay_category_name": xml_text(item, "e:PrimaryCategory/e:CategoryName"),
        "brand": item_specific(item, "Brand") or item_specific(item, "Manufacturer"),
        "item_specifics": specifics,
        "picture_urls": listing_picture_urls(item),
        "sku": xml_text(item, "e:SKU"),
    }


def suggest_categories(client: EbayClient, query: str, *, limit: int = 6) -> list[dict[str, str]]:
    text = escape((query or "").strip())
    if not text:
        return []
    root = trading_call(client, "GetSuggestedCategories", f"<Query>{text}</Query>", fail_partial=False)
    out: list[dict[str, str]] = []
    for node in root.findall("e:SuggestedCategoryArray/e:SuggestedCategory", NS):
        category_id = xml_text(node, "e:Category/e:CategoryID")
        name = xml_text(node, "e:Category/e:CategoryName")
        parent = xml_text(node, "e:Category/e:CategoryParentName")
        if not category_id:
            continue
        label = f"{parent} > {name}" if parent and parent != name else name
        out.append({"id": category_id, "name": label or name})
        if len(out) >= limit:
            break
    return out


def seller_profiles_from_item(client: EbayClient, ebay_item_id: str) -> dict[str, str]:
    item_id = escape(str(ebay_item_id).strip())
    if not item_id:
        raise ValueError("eBay item ID is required")
    root = trading_call(
        client,
        "GetItem",
        f"<ItemID>{item_id}</ItemID><DetailLevel>ReturnAll</DetailLevel>",
        fail_partial=False,
    )
    item = root.find("e:Item", NS)
    return {
        "shipping_profile_id": xml_text(item, "e:SellerProfiles/e:SellerShippingProfile/e:ShippingProfileID"),
        "return_profile_id": xml_text(item, "e:SellerProfiles/e:SellerReturnProfile/e:ReturnProfileID"),
        "payment_profile_id": xml_text(item, "e:SellerProfiles/e:SellerPaymentProfile/e:PaymentProfileID"),
        "postal_code": xml_text(item, "e:PostalCode"),
        "location": xml_text(item, "e:Location") or xml_text(item, "e:Country"),
        "country": xml_text(item, "e:Country") or "US",
        "dispatch_time": xml_text(item, "e:DispatchTimeMax") or "3",
    }


def upload_picture(client: EbayClient, image_bytes: bytes, *, name: str = "photo") -> str:
    if not image_bytes:
        raise ValueError("Photo is empty")
    import base64

    encoded = base64.b64encode(image_bytes).decode("ascii")
    label = escape((name or "photo")[:40])
    root = trading_call(
        client,
        "UploadSiteHostedPictures",
        f"<PictureName>{label}</PictureName><PictureData>{encoded}</PictureData>",
        fail_partial=False,
    )
    url = xml_text(root, "e:SiteHostedPictureDetails/e:FullURL") or xml_text(
        root, "e:SiteHostedPictureDetails/e:FullURL"
    )
    if not url:
        raise RuntimeError("eBay did not return a hosted picture URL")
    return url


def _specifics_xml(brand: str, item_specifics: object = None) -> str:
    rows = item_specifics if isinstance(item_specifics, list) else []
    seen: set[str] = set()
    parts: list[str] = []
    brand_value = (brand or "").strip()
    if brand_value:
        parts.append(
            f"<NameValueList><Name>Brand</Name><Value>{escape(brand_value)}</Value></NameValueList>"
        )
        seen.add("brand")
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        values = [str(value).strip() for value in (row.get("values") or []) if str(value).strip()]
        key = name.lower()
        if not name or not values or key in seen:
            continue
        seen.add(key)
        value_xml = "".join(f"<Value>{escape(value)}</Value>" for value in values[:10])
        parts.append(f"<NameValueList><Name>{escape(name)}</Name>{value_xml}</NameValueList>")
    if "brand" not in seen:
        parts.insert(
            0,
            "<NameValueList><Name>Brand</Name><Value>Unbranded</Value></NameValueList>",
        )
    return f"<ItemSpecifics>{''.join(parts)}</ItemSpecifics>"


def add_fixed_price_item(
    client: EbayClient,
    *,
    title: str,
    description: str,
    price: str | Decimal,
    qty: str | int = 1,
    sku: str = "",
    category_id: str,
    condition_id: str = "3000",
    picture_urls: list[str],
    brand: str = "",
    item_specifics: object = None,
    profiles: dict[str, str],
) -> str:
    title_text = escape((title or "").strip()[:80])
    if not title_text:
        raise ValueError("Title is required")
    if not category_id:
        raise ValueError("eBay category is required")
    try:
        amount = Decimal(str(price))
    except InvalidOperation as exc:
        raise ValueError("Price must be a number") from exc
    if amount <= 0:
        raise ValueError("Price must be greater than zero")
    try:
        quantity = int(Decimal(str(qty)))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Qty must be a whole number") from exc
    if quantity < 1:
        quantity = 1
    urls = [escape(url.strip()) for url in picture_urls if url and url.strip()]
    if not urls:
        raise ValueError("At least one photo is required to list")
    pictures = "".join(f"<PictureURL>{url}</PictureURL>" for url in urls[:12])
    safe_desc = (description or "").replace("]]>", "")
    country = escape(profiles.get("country") or "US")
    location = escape(profiles.get("location") or "USA")
    postal = escape(profiles.get("postal_code") or "")
    dispatch = escape(profiles.get("dispatch_time") or "3")
    shipping = escape(profiles.get("shipping_profile_id") or "")
    returns = escape(profiles.get("return_profile_id") or "")
    payment = escape(profiles.get("payment_profile_id") or "")
    if not (shipping and returns and payment):
        raise ValueError(
            "Missing eBay business policies. List one item in Seller Hub first, "
            "or set EBAY_SHIPPING_PROFILE_ID, EBAY_RETURN_PROFILE_ID, and EBAY_PAYMENT_PROFILE_ID."
        )
    sku_xml = f"<SKU>{escape(sku.strip())}</SKU>" if sku.strip() else ""
    postal_xml = f"<PostalCode>{postal}</PostalCode>" if postal else ""
    inner = (
        "<Item>"
        f"<Title>{title_text}</Title>"
        f"<Description><![CDATA[{safe_desc}]]></Description>"
        f"<PrimaryCategory><CategoryID>{escape(category_id)}</CategoryID></PrimaryCategory>"
        f'<StartPrice currencyID="USD">{amount:.2f}</StartPrice>'
        f"<ConditionID>{escape(condition_id or '3000')}</ConditionID>"
        f"<Country>{country}</Country>"
        "<Currency>USD</Currency>"
        f"<DispatchTimeMax>{dispatch}</DispatchTimeMax>"
        "<ListingDuration>GTC</ListingDuration>"
        "<ListingType>FixedPriceItem</ListingType>"
        f"<Location>{location}</Location>"
        f"{postal_xml}"
        f"<Quantity>{quantity}</Quantity>"
        f"{sku_xml}"
        f"<PictureDetails>{pictures}</PictureDetails>"
        "<SellerProfiles>"
        f"<SellerShippingProfile><ShippingProfileID>{shipping}</ShippingProfileID></SellerShippingProfile>"
        f"<SellerReturnProfile><ReturnProfileID>{returns}</ReturnProfileID></SellerReturnProfile>"
        f"<SellerPaymentProfile><PaymentProfileID>{payment}</PaymentProfileID></SellerPaymentProfile>"
        "</SellerProfiles>"
        f"{_specifics_xml(brand, item_specifics)}"
        "</Item>"
    )
    try:
        root = trading_call(client, "AddFixedPriceItem", inner, fail_partial=False)
    except RuntimeError as exc:
        text = str(exc).lower()
        if "fixed price" not in text and "addfixedpriceitem" not in text:
            raise
        root = trading_call(client, "AddItem", inner, fail_partial=False)
    new_id = xml_text(root, "e:ItemID")
    if not new_id:
        message = xml_text(root, "e:Errors/e:LongMessage") or xml_text(
            root, "e:Errors/e:ShortMessage"
        )
        raise RuntimeError(message or "Add listing did not return an ItemID")
    return new_id
