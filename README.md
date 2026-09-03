# F-Bar Garage eBay store

**Audience:** Developer (primary); Operations, Manager (secondary)  
**Audiences:** developer, operations, manager  
**Status:** Active  
**Doc-reviewed:** 2026-09-03  
**Summary:** This repo is the primary f-bargarage store project. Financial reports run from SQLite and show on the LAN UI. Shelf inventory and listings live in MySQL on `:5057`, including photos, AI/eBay drafts, list, end, revise, relist, and incremental refresh.

---

Seller account **f-bargarage**. Watches, electronics, motorcycle and car parts, and other store SKUs. Workshop parts and builds stay in sibling **cogs** (`Z:\gitrepos\cogs`, `:5056`). This repo owns listings, store inventory, sales, and tax reports.

## What is here now

Brought over from `Z:\gitrepos\ebay-store` (v0.2.0):

| Capability | How |
|------------|-----|
| SQLite store | `db/schema.sql` → `db/ebay_store.db` (gitignored) |
| CSV import | `python scripts/db/import_csv.py --all` from `financials/f-bargarage/` |
| eBay OAuth + API sync | `.env` + `.\scripts\ebay_user_oauth.ps1` + `python scripts/db/sync_ebay.py --month YYYY-MM` |
| Monthly reports | `python scripts/run_monthly_reports.py --year 2026 --month 6 --from-db` |
| SKU / store analysis | `scripts/analyze_sku_financials.py`, `scripts/analyze_all_orders.py` |

Local `.env` and the existing SQLite file were copied so OAuth and reports keep working here. Do not commit them. Seller CSVs, eBay account HTML, and generated reports stay in local `financials/` and `reports/` (gitignored). This GitHub repo is public.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/db/init_db.py
python scripts/db/import_csv.py --all
python scripts/init_mysql.py
python scripts/import_listings_csv.py
python scripts/serve.py
```

LAN UI: http://127.0.0.1:5057/ · TrueNAS: http://truenas.local:5057/ after `python scripts/deploy_ui.py`. Apache card: `python scripts/deploy_apache_card.py` → http://truenas.local:8080/fbargarage/

If `.env` is missing, copy `.env.example` and fill Production keys from [developer.ebay.com](https://developer.ebay.com/my/keys). Then:

```powershell
.\scripts\ebay_user_oauth.ps1
python scripts/db/sync_ebay.py --month 2026-08
```

See [docs/REPORTING.md](docs/REPORTING.md) for the monthly workflow and [docs/DATA_STRUCTURE.md](docs/DATA_STRUCTURE.md) for CSV layouts. On the LAN UI, [Reports](http://truenas.local:5057/reports) shows the same generated files.

## LAN inventory

FastAPI + Docker on **`:5057`**, MySQL `ebay_store`. Apache `:8080` is a static card only. Cogs reads `GET /health`, `/api/listings`, `/api/orders`.

**Add to inventory** is its own tab. Add a shelf item with photos, description, condition, brand, and eBay category. **Suggest from photos and eBay** fills those fields from matching listings (and from OpenAI or Gemini if you set a key). After save you land on the item page; type LIST to create the eBay listing, or check **Also list on eBay after save** on the add form.

**Refresh from eBay** only pulls listings that changed and orders from the last few days. New SKUs get extra photos and item specifics in the background. Inventory shows the primary picture (local file, or the eBay image until the download finishes). Use **List** on a row that is not posted.

Select rows on Inventory or Listings and use **Apply to selected**: status/category/location/delete on the shelf, or end/relist on eBay.

End a live listing from Listings or Item (type END). Relist an ended listing from Listings (ended filter) or Item (type RELIST). Change price and qty on the Item page with **Update on eBay**.

See [docs/technical/app.md](docs/technical/app.md).

## Workspace

Open `fbargarage.code-workspace`. `Z:\gitrepos\ebay-store` is kept as backup.

## Docs

| Path | Job |
|------|-----|
| [docs/README.md](docs/README.md) | Index |
| [docs/REPORTING.md](docs/REPORTING.md) | Monthly reports |
| [docs/DATA_STRUCTURE.md](docs/DATA_STRUCTURE.md) | CSV and SQLite tables |
| [docs/ARCHIVING.md](docs/ARCHIVING.md) | Archive old files |
| [docs/technical/app.md](docs/technical/app.md) | LAN UI |
