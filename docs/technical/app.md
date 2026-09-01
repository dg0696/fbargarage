# LAN store app

**Audience:** Developer (primary); Operations (secondary)  
**Audiences:** developer, operations  
**Status:** Active  
**Doc-reviewed:** 2026-09-01  
**Summary:** FastAPI UI on `:5057` reads and writes MySQL `ebay_store`, and can end, revise, and relist Seller Hub listings.

---

## Where it lives

| Piece | Target |
|-------|--------|
| Code | `Z:\gitrepos\fbargarage` |
| MySQL | `ebay_store` on `truenas.local:3306` (`dota`) |
| SQLite financials | `db/ebay_store.db` (gitignored) |
| Live URL | http://truenas.local:5057/ |
| Apache card | http://truenas.local:8080/fbargarage/ |
| Local | `python scripts/serve.py` → http://127.0.0.1:5057/ |

Copy **cogs**, not Resume-Builder. Apache is static httpd with no PHP.

## Pages

| Page | Job |
|------|-----|
| Home | Counts by status and stream |
| Inventory | Search, add, edit, delete shelf rows; First / Previous / page numbers / Next / Last |
| Item | Qty, cost, location, cogs IDs, linked listings; **Update on eBay** price/qty; **End listing**; **Relist** |
| Listings | Active eBay rows with the same table pager; **End**; ended rows **Relist**; **Refresh from eBay** pulls listings and 2026 orders |

## LAN API (cogs)

- `GET /health` → `{ ok, version, store: "f-bargarage" }`
- `GET /api/listings?stream=&status=active`
- `GET /api/listings/{sku}`
- `GET /api/orders?since=YYYY-MM-DD` (no buyer fields)

## Commands

```powershell
python scripts/ebay_user_oauth.py
python scripts/store_ebay_secrets.py --export-docker
python scripts/sync_listings.py
python scripts/sync_orders.py
python scripts/serve.py
python scripts/deploy_ui.py
python scripts/deploy_apache_card.py
```

Re-copy the Apache card after a Resume-Builder `deploy_web.py` (it wipes htdocs).

## Secrets

eBay Client ID/Secret, RuName, OAuth tokens, and the deletion-endpoint verification token live in **Windows Credential Manager** (service `fbargarage`), not in `.env` on the NAS share.

```powershell
python scripts/store_ebay_secrets.py
python scripts/store_ebay_secrets.py --status
python scripts/ebay_user_oauth.py
python scripts/store_ebay_secrets.py --export-docker
```

The first command prompts you to paste Production App ID, Dev ID, and Cert ID. Sandbox keys already in WCM are kept as `*_SANDBOX`. User OAuth must include **sell.inventory** (write) for End / revise — enable that scope on the eBay app if consent fails.

`.env` may keep `EBAY_API_ENV` and MySQL host names. Docker on TrueNAS uses `docker.env` for `DB_PASSWORD` and eBay tokens.

## eBay Production unlock

eBay requires a public HTTPS **Marketplace account deletion** URL before Production keys work. That lives in `workers/ebay-account-deletion/` on Cloudflare (`workers.dev` first). Google Workspace mail on `f-bargarage.com` stays on Google — do not change MX or nameservers for this step.

## Related

- [Roadmap](../project/roadmap.md)
- Cogs contract: `Z:\gitrepos\cogs\docs\technical\ebay-store.md`
