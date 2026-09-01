"""Paste eBay credentials into the terminal; store them in Windows Credential Manager.

Usage:
    python scripts/store_ebay_secrets.py
    python scripts/store_ebay_secrets.py --status
    python scripts/store_ebay_secrets.py --export-docker
    python scripts/store_ebay_secrets.py --set EBAY_REDIRECT_URI
    python scripts/store_ebay_secrets.py --get EBAY_CLIENT_ID
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from credentials import (  # noqa: E402
    REPO_ROOT,
    SECRET_NAMES,
    _stored,
    env,
    secret,
    secret_status,
    set_secret,
)

TOKEN_FILE = Path.home() / "fbargarage-ebay-compliance" / ".ebay-verification-token.txt"

PROMPT_FIELDS = (
    ("EBAY_CLIENT_ID_PRODUCTION", "Production App ID (Client ID)"),
    ("EBAY_DEV_ID_PRODUCTION", "Production Dev ID"),
    ("EBAY_CLIENT_SECRET_PRODUCTION", "Production Cert ID (Client Secret)"),
    ("EBAY_REDIRECT_URI_PRODUCTION", "Production RuName (optional, Enter to skip)"),
)

DOCKER_ENV = REPO_ROOT / "docker.env"
DOCKER_KEYS = (
    "EBAY_USER_ACCESS_TOKEN",
    "EBAY_USER_REFRESH_TOKEN",
    "EBAY_USER_TOKEN_EXPIRY",
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "EBAY_DEV_ID",
    "EBAY_REDIRECT_URI",
)


def _read_dotenv_secrets(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    if not path.is_file():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in SECRET_NAMES and value:
            found[key] = value
    return found


def _clear_dotenv_secrets(path: Path) -> None:
    if not path.is_file():
        return
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in SECRET_NAMES:
                lines.append(f"{key}=")
                continue
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prompt_value(label: str) -> str:
    print(f"\n{label}")
    print("Paste, then press Enter. Input is hidden. Leave blank to skip.")
    return getpass.getpass("").strip()


def _store_named(name: str, value: str) -> None:
    set_secret(name, value)
    print(f"stored {name} ({len(value)} chars)")


def _keep_sandbox_copy() -> None:
    for generic, labeled in (
        ("EBAY_CLIENT_ID", "EBAY_CLIENT_ID_SANDBOX"),
        ("EBAY_CLIENT_SECRET", "EBAY_CLIENT_SECRET_SANDBOX"),
    ):
        current = _stored(generic)
        if current and not _stored(labeled):
            set_secret(labeled, current)


def export_docker_env() -> None:
    """Copy WCM eBay tokens into gitignored docker.env for the TrueNAS container."""
    existing: dict[str, str] = {}
    order: list[tuple[str, str]] = []
    if DOCKER_ENV.is_file():
        for line in DOCKER_ENV.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                order.append(("raw", line))
                continue
            key, value = line.split("=", 1)
            existing[key.strip()] = value
            order.append(("key", key.strip()))
    written: list[str] = []
    for name in DOCKER_KEYS:
        value = secret(name)
        if not value:
            continue
        existing[name] = value
        written.append(name)
    api_env = env("EBAY_API_ENV")
    if api_env:
        existing["EBAY_API_ENV"] = api_env
        if "EBAY_API_ENV" not in written:
            written.append("EBAY_API_ENV")
    lines: list[str] = []
    seen: set[str] = set()
    for kind, payload in order:
        if kind == "raw":
            lines.append(payload)
            continue
        if payload in seen:
            continue
        seen.add(payload)
        lines.append(f"{payload}={existing.get(payload, '')}")
    for name, value in existing.items():
        if name not in seen:
            lines.append(f"{name}={value}")
            seen.add(name)
    DOCKER_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("updated docker.env: " + ", ".join(written))


def prompt_production() -> None:
    _keep_sandbox_copy()
    print("Windows Credential Manager  service=fbargarage")
    print("Paste Production keys from developer.ebay.com → Application Keys.")
    print("Nothing is written to .env.")
    stored = 0
    for name, label in PROMPT_FIELDS:
        value = _prompt_value(label)
        if not value:
            print(f"skipped {name}")
            continue
        _store_named(name, value)
        stored += 1
    extra_name = input("\nOptional extra key name (or Enter to finish): ").strip()
    if extra_name:
        extra_value = _prompt_value(extra_name)
        if extra_value:
            _store_named(extra_name, extra_value)
            stored += 1
    print()
    if stored:
        print(f"Saved {stored} value(s). Set EBAY_API_ENV=production in .env when you switch.")
    else:
        print("Nothing stored.")
    print()
    for name, state in secret_status().items():
        if name.endswith("_PRODUCTION") or name in ("EBAY_DEV_ID", "EBAY_REDIRECT_URI"):
            print(f"{name}={state}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paste eBay secrets into Windows Credential Manager.")
    parser.add_argument("--prompt", action="store_true", help="Interactive paste (default if no other flags).")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--from-env", action="store_true", help="Copy non-empty .env secrets into keyring.")
    parser.add_argument("--from-token-file", action="store_true", help="Import Cloudflare verification token file.")
    parser.add_argument("--clear-env", action="store_true", help="Blank secret values in .env after storing.")
    parser.add_argument("--export-docker", action="store_true", help="Copy WCM eBay tokens into docker.env.")
    parser.add_argument("--get", metavar="NAME", help="Print one secret (for scripts).")
    parser.add_argument("--set", metavar="NAME", dest="set_name", help="Read secret value from stdin.")
    args = parser.parse_args()

    if args.get:
        sys.stdout.write(secret(args.get))
        return

    if args.set_name:
        if sys.stdin.isatty():
            value = _prompt_value(args.set_name)
        else:
            value = sys.stdin.read().strip()
        if not value:
            raise SystemExit("No value on stdin")
        _store_named(args.set_name, value)
        return

    flagged = args.status or args.from_env or args.from_token_file or args.clear_env or args.export_docker
    if args.export_docker:
        export_docker_env()
        if not (args.status or args.from_env or args.from_token_file or args.clear_env):
            return
    if args.prompt or not flagged:
        prompt_production()
        return

    stored: list[str] = []
    if args.from_env:
        for name, value in _read_dotenv_secrets(REPO_ROOT / ".env").items():
            set_secret(name, value)
            stored.append(name)
    if args.from_token_file and TOKEN_FILE.is_file():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            set_secret("EBAY_VERIFICATION_TOKEN", token)
            stored.append("EBAY_VERIFICATION_TOKEN")
            TOKEN_FILE.unlink()
    if args.clear_env:
        _clear_dotenv_secrets(REPO_ROOT / ".env")
        print("cleared secret values from .env")
    if stored:
        print("stored: " + ", ".join(stored))
    if args.status:
        for name, state in secret_status().items():
            print(f"{name}={state}")


if __name__ == "__main__":
    main()
