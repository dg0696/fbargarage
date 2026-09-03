# Roadmap

**Audience:** Program manager (primary); Manager, Developer (secondary)  
**Audiences:** program-manager, manager, developer  
**Status:** Active  
**Doc-reviewed:** 2026-09-03  
**Summary:** Financial pipeline is here. LAN UI can add listing drafts with photos, suggest from eBay/AI, list, end, revise, or relist, and refresh only changed eBay rows. Keep `Z:\gitrepos\ebay-store` as backup.

---

| Phase | Done when |
|-------|-----------|
| **Merge** | ebay-store scripts, SQLite schema, financials, reports, and local `.env` work from `Z:\gitrepos\fbargarage` |
| **Verify** | Done enough to keep working here. ebay-store folder stays as backup. |
| **Retire ebay-store** | Later, when you say so |
| **LAN UI** | FastAPI + Docker on `:5057`; MySQL `ebay_store`; Apache card `/fbargarage/` |
| **Cogs handshake** | `GET /health`, `/api/listings`, `/api/orders` as in cogs `docs/technical/ebay-store.md` |
| **Mutate eBay** | End, revise price/qty, relist, and create a listing from a new inventory item (photos + fields + eBay/AI suggest) |

## Related

- [Root README](../../README.md)
- [Reporting](../REPORTING.md)
