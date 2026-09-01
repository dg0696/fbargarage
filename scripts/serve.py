"""Run the f-bargarage LAN UI.

Usage:
    python scripts/serve.py
    python scripts/serve.py --host 0.0.0.0 --port 5057
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from credentials import app_host, app_port, db_summary  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the f-bargarage store UI.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    host = args.host or app_host()
    port = args.port or app_port()
    db = db_summary()
    print(f"f-bargarage UI  http://{host}:{port}/")
    print(f"Database {db['user']}@{db['host']}:{db['port']}/{db['name']} ({db['password_source']})")

    import uvicorn

    uvicorn.run("store_app.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
