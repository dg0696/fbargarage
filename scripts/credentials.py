"""Resolve TrueNAS MySQL credentials without putting secrets in git.

Same host and user as Resume-Builder / spamalot-builder / cogs: dota @ truenas.local:3306.
Order: this repo .env, Windows Credential Manager, then sibling repos.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

KEYRING_SERVICE = "fbargarage"
RESUME_KEYRING_SERVICE = "ResumeBuilder-Database"
SIBLING_ENV = Path(r"Z:\gitrepos\Resume-Builder\.env")
SIBLING_SPAMALOT_ENV = Path(r"Z:\gitrepos\spamalot-builder\.env")
SIBLING_COGS_ENV = Path(r"Z:\gitrepos\cogs\.env")
SIBLING_INIT = Path(r"Z:\gitrepos\Resume-Builder\scripts\init_db_with_root.py")
SIBLING_DB_DOC = Path(r"Z:\gitrepos\Resume-Builder\docs\DATABASE_SETUP.md")


SECRET_NAMES = (
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "EBAY_DEV_ID",
    "EBAY_REDIRECT_URI",
    "EBAY_CLIENT_TOKEN",
    "EBAY_USER_ACCESS_TOKEN",
    "EBAY_USER_REFRESH_TOKEN",
    "EBAY_USER_TOKEN_EXPIRY",
    "EBAY_VERIFICATION_TOKEN",
    "EBAY_CLIENT_ID_SANDBOX",
    "EBAY_CLIENT_SECRET_SANDBOX",
    "EBAY_DEV_ID_SANDBOX",
    "EBAY_CLIENT_ID_PRODUCTION",
    "EBAY_CLIENT_SECRET_PRODUCTION",
    "EBAY_DEV_ID_PRODUCTION",
    "EBAY_REDIRECT_URI_PRODUCTION",
)

_SECRET_ALIASES = {
    "EBAY_CLIENT_ID": {
        "production": ("EBAY_CLIENT_ID_PRODUCTION",),
        "sandbox": ("EBAY_CLIENT_ID_SANDBOX",),
    },
    "EBAY_CLIENT_SECRET": {
        "production": ("EBAY_CLIENT_SECRET_PRODUCTION", "EBAY_CERT_ID"),
        "sandbox": ("EBAY_CLIENT_SECRET_SANDBOX",),
    },
    "EBAY_DEV_ID": {
        "production": ("EBAY_DEV_ID_PRODUCTION",),
        "sandbox": ("EBAY_DEV_ID_SANDBOX",),
    },
    "EBAY_REDIRECT_URI": {
        "production": ("EBAY_REDIRECT_URI_PRODUCTION",),
        "sandbox": ("EBAY_REDIRECT_URI_SANDBOX",),
    },
}

# Windows Credential Manager rejects blobs over ~2.5 KB (eBay app tokens).
_KEYRING_MAX = 2000
LOCAL_SECRETS = Path.home() / ".fbargarage" / "secrets.json"


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _local_secrets() -> dict[str, str]:
    if not LOCAL_SECRETS.is_file():
        return {}
    try:
        data = json.loads(LOCAL_SECRETS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_local_secrets(data: dict[str, str]) -> None:
    LOCAL_SECRETS.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_SECRETS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if os.name == "nt":
        subprocess.run(
            ["icacls", str(LOCAL_SECRETS), "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME', '')}:F"],
            check=False,
            capture_output=True,
        )


def _stored(name: str) -> str:
    try:
        import keyring
    except ImportError:
        keyring = None  # type: ignore
    if keyring is not None:
        try:
            stored = keyring.get_password(KEYRING_SERVICE, name)
        except Exception:
            stored = None
        if stored:
            return stored
    return _local_secrets().get(name, "")


def secret(name: str, default: str = "") -> str:
    """Env-specific WCM keys first, then process env, then generic stored value."""
    api_env = env("EBAY_API_ENV", "production")
    for alias in _SECRET_ALIASES.get(name, {}).get(api_env, ()):
        stored = _stored(alias)
        if stored:
            return stored
    value = env(name)
    if value:
        return value
    return _stored(name) or default


def set_secret(name: str, value: str) -> None:
    local = _local_secrets()
    if not value:
        local.pop(name, None)
        _write_local_secrets(local)
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, name)
        except Exception:
            pass
        return
    if len(value) <= _KEYRING_MAX:
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, name, value)
            local.pop(name, None)
            _write_local_secrets(local)
            return
        except Exception:
            pass
    local[name] = value
    _write_local_secrets(local)


def secret_status() -> dict[str, str]:
    return {name: "set" if secret(name) else "missing" for name in SECRET_NAMES}


def db_host() -> str:
    return env("DB_HOST", "truenas.local")


def db_port() -> int:
    return int(env("DB_PORT", "3306"))


def db_name() -> str:
    return env("DB_NAME", "ebay_store")


def db_user() -> str:
    return env("DB_USER", "dota")


def app_host() -> str:
    return env("APP_HOST", "127.0.0.1")


def app_port() -> int:
    return int(env("APP_PORT", "5057"))


def _keyring_password() -> str:
    try:
        import keyring
    except ImportError:
        return ""
    for service, username in (
        (KEYRING_SERVICE, db_user()),
        ("cogs", db_user()),
        ("spamalot-builder", db_user()),
        (RESUME_KEYRING_SERVICE, "password"),
        (RESUME_KEYRING_SERVICE, db_user()),
    ):
        try:
            value = keyring.get_password(service, username)
        except Exception:
            value = None
        if value:
            return value
    return ""


def _parse_dotenv_password(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("DB_PASSWORD="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _parse_sibling_init_password() -> str:
    if not SIBLING_INIT.is_file():
        return ""
    try:
        text = SIBLING_INIT.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r'^DOTA_PASSWORD\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else ""


def db_password() -> str:
    return (
        env("DB_PASSWORD")
        or _keyring_password()
        or _parse_dotenv_password(REPO_ROOT / ".env")
        or _parse_dotenv_password(SIBLING_COGS_ENV)
        or _parse_dotenv_password(SIBLING_SPAMALOT_ENV)
        or _parse_dotenv_password(SIBLING_ENV)
        or _parse_sibling_init_password()
    )


def password_source() -> str:
    if env("DB_PASSWORD"):
        return ".env"
    if _keyring_password():
        return "keyring"
    if _parse_dotenv_password(SIBLING_COGS_ENV):
        return "cogs .env"
    if _parse_dotenv_password(SIBLING_SPAMALOT_ENV):
        return "spamalot-builder .env"
    if _parse_dotenv_password(SIBLING_ENV):
        return "Resume-Builder .env"
    if _parse_sibling_init_password():
        return "Resume-Builder init script"
    return "missing"


def sibling_root_password() -> str:
    if not SIBLING_DB_DOC.is_file():
        return ""
    try:
        text = SIBLING_DB_DOC.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r'DB_ROOT_PASSWORD\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else ""


def db_summary() -> dict[str, str | int]:
    return {
        "host": db_host(),
        "port": db_port(),
        "name": db_name(),
        "user": db_user(),
        "password_configured": "yes" if db_password() else "no",
        "password_source": password_source(),
    }
