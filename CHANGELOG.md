# Changelog

**Audience:** Developer (primary); Manager (secondary)  
**Audiences:** developer, manager  
**Status:** Active  
**Doc-reviewed:** 2026-08-31  
**Summary:** Version history for the f-bargarage store repo, from financial reports through the LAN inventory UI.

---

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.3] - 2026-08-31

### Added
- Inventory and Listings table pager: First, Previous, page numbers, Next, Last
- LAN inventory/listings UI on `:5057` (MySQL `ebay_store`, cogs `/health` and `/api/listings`)
- Refresh from eBay on Home and Listings (`POST /ebay/refresh`)
- Primary listing image on Listings and Item pages
- Marketplace account deletion Worker under `workers/ebay-account-deletion/`
- Local CTP pre-submit (`scripts/presubmit.ps1`) and doc-meta validator

### Changed
- Moved primary home to `Z:\gitrepos\fbargarage` (this repo). ebay-store is kept as backup.
- Seller CSVs and generated reports stay local; the GitHub repo is public.

## [0.2.0] - 2026-06-07

### Added
- SQLite data pipeline: schema, CSV import, and local database tooling (`db/`, `scripts/db/`)
- eBay REST API client, user OAuth script, and seller data sync (`scripts/lib/`, `scripts/db/sync_ebay.py`)
- DB-backed monthly report generators and `scripts/run_monthly_reports.py` orchestrator
- `scripts/analyze_all_orders.py` for store and SKU all-orders reports
- `scripts/reports/compare_reports.py` to validate CSV vs DB report parity
- `.env.example`, `requirements.txt`, and OAuth helper scripts
- `docs/REPORTING.md` with monthly workflow, validation, and printing instructions

### Changed
- Moved f-bargarage financial exports to `financials/f-bargarage/`
- Aligned SKU report formatting between legacy CSV scripts and DB-backed output
- Updated README and DATA_STRUCTURE for database workflow and report validation

## [0.1.1] - 2026-01-09

### Added
- Documentation for purchase and sales data locations in README.md and DATA_STRUCTURE.md
- Note about purchase data in `financials/ebay-reports/` subfolders
- Note about additional purchase and sales data in `financials/f-bargarage/` folder

## [0.1.0] - 2026-01-09

### Added
- Initial project setup and structure
- Git repository initialization with remote origin
- Comprehensive .gitignore file
- VS Code workspace configuration
- Archive functionality script (`scripts/archive_files.py`)
- Project documentation:
  - README.md with project overview
  - CHANGELOG.md for change tracking
  - docs/ARCHIVING.md for archive procedures
  - docs/GIT_WORKFLOW.md for git workflow guidelines
  - docs/DATA_STRUCTURE.md for data file documentation
- Folder structure:
  - scripts/ for data processing scripts
  - reports/ and reports/archive/ for generated reports
  - docs/ and docs/archive/ for documentation
  - archive/ for general file archives
  - releases/ for release notes
  - logs/ for application logs

### Changed
- Updated workspace configuration with Python settings, file exclusions, and extension recommendations

[Unreleased]: https://github.com/dg0696/fbargarage/compare/v0.3.3...HEAD
[0.3.3]: https://github.com/dg0696/fbargarage/releases/tag/v0.3.3
[0.2.0]: https://github.com/dg0696/ebay-store/compare/v0.1.2...v0.2.0
[0.1.1]: https://github.com/dg0696/ebay-store/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/dg0696/ebay-store/releases/tag/v0.1.0
