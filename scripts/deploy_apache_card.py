"""Copy the static /fbargarage/ link card into Apache htdocs.

  python scripts/deploy_apache_card.py
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SSH_HOST = os.getenv("SSH_HOST", "truenas.local")
SSH_USER = os.getenv("SSH_USER", "dotanuki")
WEB_ROOT = os.getenv("WEB_ROOT", "/mnt/foobar/Apache/website")
REMOTE_SRC = os.getenv(
    "UI_DEPLOY_PATH",
    "/mnt/foobar/workspace/gitrepos/fbargarage",
)
CARD_URL = f"http://{SSH_HOST}:8080/fbargarage/"


def _ssh(remote: str, *, capture: bool = False) -> subprocess.CompletedProcess:
    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        f"{SSH_USER}@{SSH_HOST}",
        remote,
    ]
    return subprocess.run(args, capture_output=capture, text=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Apache /fbargarage/ link card")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dest = f"{WEB_ROOT}/fbargarage"
    src = f"{REMOTE_SRC}/web/fbargarage"
    remote_cmd = (
        f"sudo mkdir -p '{dest}' && "
        f"sudo cp -a '{src}/.' '{dest}/' && "
        f"sudo chmod -R a+rX '{dest}'"
    )
    if args.dry_run:
        print(f"[dry-run] ssh {SSH_USER}@{SSH_HOST} {remote_cmd}")
        return 0

    print(f"Copying {src} -> {dest} ...")
    copied = _ssh(remote_cmd)
    if copied.returncode != 0:
        print("[FAIL] copy into Apache web root failed.", file=sys.stderr)
        return 1

    try:
        with urllib.request.urlopen(CARD_URL, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(f"[FAIL] {CARD_URL} not reachable: {exc}", file=sys.stderr)
        return 1
    if "Open F-Bar Garage" not in body:
        print(f"[FAIL] unexpected card body at {CARD_URL}", file=sys.stderr)
        return 1
    print(f"[OK] {CARD_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
