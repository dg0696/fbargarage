# Motorcycle parts payouts

**Audience:** Operations (primary); Manager (secondary)  
**Audiences:** operations, manager  
**Status:** Active  
**Doc-reviewed:** 2026-09-02  
**Summary:** Sold motorcycle parts (SKU prefixes GB and GC) are paid up as of 2026-09-02. Net to pay is 70% of the amount after eBay fees.

---

## Status

| Item | Value |
|------|--------|
| Status | Current — no outstanding payout on sold motorcycle parts |
| As of | 2026-09-02 |
| Scope | Sold orders only (not unsold shelf stock) |
| SKUs | `GB*`, `GC*` (store stream `moto` in `src/store_app/streams.py`) |

## What Net means

1. Start from the eBay order **net amount** (after marketplace fees).
2. **Net** to pay the parts owner is **70%** of that figure.

Monthly printed reports that use SKU prefix `G` are broader than motorcycle-only. Use GB and GC, not every `G*` SKU.

Dollar amounts stay in the local SQLite ledger (`db/ebay_store.db`) and generated `reports/` files, not in this public repo.

## Related

- [Reporting](../REPORTING.md)
- [Documentation hub](../README.md)
