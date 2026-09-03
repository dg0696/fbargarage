"""Local item photos on disk. Served at /item-photos/{sku}/{filename}."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_BYTES = 8 * 1024 * 1024
MAX_PHOTOS = 12
SKU_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def photo_root() -> Path:
    configured = os.getenv("PHOTO_ROOT", "").strip()
    root = Path(configured) if configured else (REPO_ROOT / "data" / "item_photos")
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_sku(sku: str) -> str:
    cleaned = SKU_SAFE.sub("-", (sku or "").strip())
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("SKU is not a valid photo folder")
    return cleaned


def photo_url(sku: str, filename: str) -> str:
    return f"/item-photos/{safe_sku(sku)}/{filename}"


def photo_path(sku: str, filename: str) -> Path:
    name = Path(filename).name
    if name != filename or ".." in name:
        raise ValueError("Invalid photo name")
    return photo_root() / safe_sku(sku) / name


def extension_for(upload: UploadFile) -> str:
    name = (upload.filename or "").lower()
    suffix = Path(name).suffix
    if suffix in ALLOWED_EXT:
        return ".jpg" if suffix == ".jpeg" else suffix
    content = (upload.content_type or "").lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content in mapping:
        return mapping[content]
    raise ValueError("Photos must be JPEG, PNG, WebP, or GIF")


def suffix_for_bytes(data: bytes, content_type: str = "") -> str:
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif"
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    suffix = mapping.get((content_type or "").split(";")[0].strip().lower())
    if suffix:
        return suffix
    return ".jpg"


def save_bytes(sku: str, data: bytes, *, existing_count: int, content_type: str = "") -> str:
    if existing_count >= MAX_PHOTOS:
        raise ValueError(f"At most {MAX_PHOTOS} photos per item")
    if not data:
        raise ValueError("Empty photo")
    if len(data) > MAX_BYTES:
        raise ValueError("Each photo must be 8 MB or smaller")
    folder = photo_root() / safe_sku(sku)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix_for_bytes(data, content_type)}"
    (folder / filename).write_bytes(data)
    return filename


def save_from_url(sku: str, url: str, *, existing_count: int) -> str:
    import requests

    response = requests.get(
        url,
        timeout=45,
        headers={"User-Agent": "fbargarage-inventory/1.0", "Accept": "image/*"},
    )
    response.raise_for_status()
    return save_bytes(
        sku,
        response.content,
        existing_count=existing_count,
        content_type=response.headers.get("Content-Type", ""),
    )


def save_upload(sku: str, upload: UploadFile, *, existing_count: int) -> str:
    if existing_count >= MAX_PHOTOS:
        raise ValueError(f"At most {MAX_PHOTOS} photos per item")
    suffix = extension_for(upload)
    data = upload.file.read()
    if not data:
        raise ValueError("Empty photo")
    if len(data) > MAX_BYTES:
        raise ValueError("Each photo must be 8 MB or smaller")
    folder = photo_root() / safe_sku(sku)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    (folder / filename).write_bytes(data)
    return filename


def delete_file(sku: str, filename: str) -> None:
    path = photo_path(sku, filename)
    if path.is_file():
        path.unlink()


def delete_sku_files(sku: str) -> None:
    folder = photo_root() / safe_sku(sku)
    if not folder.is_dir():
        return
    for child in folder.iterdir():
        if child.is_file():
            child.unlink()
    try:
        folder.rmdir()
    except OSError:
        pass


def read_bytes(sku: str, filename: str) -> bytes:
    path = photo_path(sku, filename)
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path.read_bytes()
