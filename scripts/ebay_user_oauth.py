"""Production/sandbox user OAuth. Paste the localhost redirect URL; code is not echoed.

Usage:
    python scripts/ebay_user_oauth.py
"""

from __future__ import annotations

import getpass
import sys
import webbrowser
from urllib.parse import parse_qs, unquote, urlparse

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "lib"))

from ebay_client import EbayClient  # noqa: E402


def extract_code(raw: str) -> str:
    text = raw.strip().strip('"').strip("'")
    if "code=" in text:
        parsed = urlparse(text)
        values = parse_qs(parsed.query).get("code") or parse_qs(parsed.fragment).get("code")
        if values:
            return unquote(values[0])
    return unquote(text)


def main() -> None:
    client = EbayClient()
    url = client.build_authorize_url()
    print(f"Environment: {client.environment}")
    print("Opening eBay sign-in. Log in as f-bargarage, then Agree.")
    print("The localhost page will fail. Copy the full address bar.")
    print()
    webbrowser.open(url)
    raw = getpass.getpass("Paste the full redirect URL (hidden): ")
    code = extract_code(raw)
    if not code:
        raise SystemExit("No code found. Paste the full https://localhost/ebay-oauth?code=... URL.")
    print(f"Exchanging code ({len(code)} chars)…")
    try:
        client.exchange_authorization_code(code)
    except Exception as exc:
        body = getattr(getattr(exc, "response", None), "text", "")
        raise SystemExit(f"Token exchange failed: {exc}\n{body[:300]}") from exc
    print("User tokens saved to Windows Credential Manager.")
    print("Next: live listings pull.")


if __name__ == "__main__":
    main()
