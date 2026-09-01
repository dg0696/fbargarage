"""Deploy the store UI to TrueNAS Docker (cogs / spamalot pattern).

  python scripts/deploy_ui.py
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SSH_HOST = os.getenv("SSH_HOST", "truenas.local")
SSH_USER = os.getenv("SSH_USER", "dotanuki")
DOCKER_CMD = os.getenv("DOCKER_CMD", "sudo docker")
REMOTE_DIR = os.getenv(
    "UI_DEPLOY_PATH",
    "/mnt/foobar/workspace/gitrepos/fbargarage",
)
CONTAINER_NAME = "fbargarage-ui"
UI_PORT = os.getenv("APP_PORT", "5057")
VERIFY_WAIT_SEC = 8


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


def _print_logs() -> None:
    result = _ssh(f"{DOCKER_CMD} logs {CONTAINER_NAME} --tail 40", capture=True)
    text = (result.stderr or "") + (result.stdout or "")
    if text.strip():
        print(text.strip(), file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy f-bargarage UI to TrueNAS")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    remote_cmd = f"cd {REMOTE_DIR} && {DOCKER_CMD} compose up -d --build"
    if args.dry_run:
        print(f"[dry-run] ssh {SSH_USER}@{SSH_HOST} {remote_cmd}")
        return 0

    print(f"Building UI on {SSH_HOST}:{REMOTE_DIR} ...")
    started = _ssh(remote_cmd)
    if started.returncode != 0:
        print("[FAIL] docker compose failed. Is Docker available as sudo docker?", file=sys.stderr)
        return 1

    if args.skip_verify:
        print(f"[OK] UI should be at http://{SSH_HOST}:{UI_PORT}/")
        return 0

    print(f"Waiting {VERIFY_WAIT_SEC}s for the container...")
    time.sleep(VERIFY_WAIT_SEC)
    status = _ssh(
        f"{DOCKER_CMD} ps --filter name={CONTAINER_NAME} --format '{{{{.Status}}}}'",
        capture=True,
    )
    state = (status.stdout or "").strip()
    if "Restarting" in state or not state:
        print(f"[FAIL] container status: {state or 'missing'}", file=sys.stderr)
        _print_logs()
        return 1
    print(f"[OK] Container is running ({state})")

    url = f"http://{SSH_HOST}:{UI_PORT}/health"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(f"[FAIL] {url} not reachable: {exc}", file=sys.stderr)
        _print_logs()
        return 1
    if '"ok": true' not in body and '"ok":true' not in body:
        print(f"[FAIL] unexpected health body: {body}", file=sys.stderr)
        return 1
    print(f"[OK] {url}")
    print(f"[OK] Open http://{SSH_HOST}:{UI_PORT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
