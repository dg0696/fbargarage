"""eBay REST API client with OAuth token management."""

import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from credentials import secret, set_secret  # noqa: E402

READ_SCOPES = " ".join(
    [
        "https://api.ebay.com/oauth/api_scope/sell.finances",
        "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
        "https://api.ebay.com/oauth/api_scope/sell.inventory.readonly",
        "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
        "https://api.ebay.com/oauth/api_scope/sell.marketing.readonly",
    ]
)
USER_SCOPES = " ".join(
    [
        "https://api.ebay.com/oauth/api_scope",
        "https://api.ebay.com/oauth/api_scope/sell.inventory",
        READ_SCOPES,
    ]
)


def read_dotenv(path=ENV_PATH):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_secret(key, value):
    set_secret(key, value)


def load_ebay_config(path=ENV_PATH):
    config = read_dotenv(path)
    for name in (
        "EBAY_CLIENT_ID",
        "EBAY_CLIENT_SECRET",
        "EBAY_DEV_ID",
        "EBAY_REDIRECT_URI",
        "EBAY_CLIENT_TOKEN",
        "EBAY_USER_ACCESS_TOKEN",
        "EBAY_USER_REFRESH_TOKEN",
        "EBAY_USER_TOKEN_EXPIRY",
    ):
        value = secret(name)
        if value:
            config[name] = value
    return config


class EbayClient:
    def __init__(self, env_path=ENV_PATH):
        self.env_path = Path(env_path)
        self.config = load_ebay_config(self.env_path)
        self.environment = self.config.get("EBAY_API_ENV") or os.getenv("EBAY_API_ENV") or "production"
        self.api_base = (
            "https://api.sandbox.ebay.com"
            if self.environment == "sandbox"
            else "https://api.ebay.com"
        )
        self.auth_base = (
            "https://auth.sandbox.ebay.com"
            if self.environment == "sandbox"
            else "https://auth.ebay.com"
        )
        self.token_url = f"{self.api_base}/identity/v1/oauth2/token"

    def _basic_auth_header(self):
        client_id = self.config["EBAY_CLIENT_ID"]
        client_secret = self.config["EBAY_CLIENT_SECRET"]
        encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        return f"Basic {encoded}"

    def get_application_token(self):
        scope = "https://api.ebay.com/oauth/api_scope"
        response = requests.post(
            self.token_url,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": scope,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def refresh_user_token(self):
        refresh_token = self.config.get("EBAY_USER_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError("EBAY_USER_REFRESH_TOKEN is not set. Run python scripts/ebay_user_oauth.py first.")

        last_error = None
        payload = None
        for scopes in (USER_SCOPES, READ_SCOPES):
            response = requests.post(
                self.token_url,
                headers={
                    "Authorization": self._basic_auth_header(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": scopes,
                },
                timeout=60,
            )
            if response.ok:
                payload = response.json()
                break
            last_error = response
        if payload is None:
            last_error.raise_for_status()
            raise RuntimeError("eBay token refresh failed")
        access_token = payload["access_token"]
        write_secret("EBAY_USER_ACCESS_TOKEN", access_token)
        if "refresh_token" in payload:
            write_secret("EBAY_USER_REFRESH_TOKEN", payload["refresh_token"])
        expires_in = payload.get("expires_in", 7200)
        write_secret("EBAY_USER_TOKEN_EXPIRY", str(int(time.time()) + int(expires_in)))
        self.config = load_ebay_config(self.env_path)
        return access_token

    def get_user_access_token(self, force_refresh=False):
        access_token = self.config.get("EBAY_USER_ACCESS_TOKEN")
        expiry = int(self.config.get("EBAY_USER_TOKEN_EXPIRY") or "0")
        if force_refresh or not access_token or time.time() >= expiry - 300:
            return self.refresh_user_token()
        return access_token

    def build_authorize_url(self, state="ebay-store"):
        client_id = self.config.get("EBAY_CLIENT_ID")
        redirect_uri = self.config.get("EBAY_REDIRECT_URI")
        if not client_id or not redirect_uri:
            raise RuntimeError(
                "Set EBAY_CLIENT_ID and EBAY_REDIRECT_URI (python scripts/store_ebay_secrets.py --set …)."
            )

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": USER_SCOPES,
            "state": state,
        }
        return f"{self.auth_base}/oauth2/authorize?{urlencode(params)}"

    def exchange_authorization_code(self, code):
        redirect_uri = self.config.get("EBAY_REDIRECT_URI")
        response = requests.post(
            self.token_url,
            headers={
                "Authorization": self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        write_secret("EBAY_USER_ACCESS_TOKEN", payload["access_token"])
        write_secret("EBAY_USER_REFRESH_TOKEN", payload["refresh_token"])
        write_secret(
            "EBAY_USER_TOKEN_EXPIRY",
            str(int(time.time()) + int(payload.get("expires_in", 7200))),
        )
        self.config = load_ebay_config(self.env_path)
        return payload

    def api_get(self, path, params=None, use_user_token=True):
        token = self.get_user_access_token() if use_user_token else self.get_application_token()
        url = f"{self.api_base}{path}"
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            params=params or {},
            timeout=60,
        )
        if response.status_code == 401 and use_user_token:
            token = self.get_user_access_token(force_refresh=True)
            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                params=params or {},
                timeout=60,
            )
        response.raise_for_status()
        if not response.text:
            return {}
        return response.json()

    def paginate_get(self, path, params=None, results_key="transactions", use_user_token=True):
        params = dict(params or {})
        offset = int(params.pop("offset", 0))
        limit = int(params.pop("limit", 100))
        all_items = []

        while True:
            page_params = {**params, "offset": offset, "limit": limit}
            payload = self.api_get(path, page_params, use_user_token=use_user_token)
            items = payload.get(results_key, [])
            all_items.extend(items)
            total = payload.get("total", len(all_items))
            offset += len(items)
            if offset >= total or not items:
                break
        return all_items
