# Archiving Guide

**Audience:** Operations (primary); Developer (secondary)  
**Audiences:** operations, developer  
**Status:** Active  
**Doc-reviewed:** 2026-08-31  
**Summary:** How to archive old reports, docs, scripts, and financial files with `scripts/archive_files.py`.

---

This document explains the archiving process and policies for the eBay Store Financial Analysis project.

## Overview

The archive functionality helps manage old files, documents, and scripts by moving them to organized archive folders based on age and file type. This keeps the main project directories clean while preserving historical data.

## Archive Script

The archive script (`scripts/archive_files.py`) provides automated archiving with the following features:

- Moves files based on age (modification date)
- Organizes archived files by year/month
- Preserves file structure in archives
- Generates archive manifests (JSON)
- Logs all operations to `logs/archive.log`
- Supports dry-run mode for preview

## Archive Locations

Files are archived to different locations based on their type:

| File Type | Archive Location | Organization |
|-----------|-----------------|--------------|
| Reports | `reports/archive/YYYY/MM/` | By year and month |
| Documentation | `docs/archive/YYYY/` | By year |
| Scripts | `archive/scripts/YYYY/` | By year |
| Financial Data | `financials/archive/YYYY/` | By year |

## Usage

### Basic Usage

Archive reports older than 90 days:
```bash
python scripts/archive_files.py --type reports --age-days 90
```

Archive documentation older than 180 days:
```bash
python scripts/archive_files.py --type docs --age-days 180
```

Archive all file types older than 365 days:
```bash
python scripts/archive_files.py --type all --age-days 365
```

### Dry Run

Preview what would be archived without actually moving files:
```bash
python scripts/archive_files.py --type reports --age-days 90 --dry-run
```

### Filter by Extension

Archive only specific file types:
```bash
python scripts/archive_files.py --type reports --age-days 90 --extensions .csv,.pdf
```

### Custom Source Directory

Archive from a specific directory:
```bash
python scripts/archive_files.py --source-dir ./custom/path --type reports --age-days 90
```

## Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--source-dir` | Directory to archive from | Current directory |
| `--age-days` | Minimum age in days to archive | 90 |
| `--dry-run` | Preview without moving files | False |
| `--type` | Type of files (reports, docs, scripts, financials, all) | all |
| `--extensions` | Comma-separated file extensions | All files |

## Archive Manifests

Each archive operation generates a manifest file in `archive/manifests/` with the following information:

- Archive date
- Total number of files archived
- For each file:
  - Original path
  - Archived path
  - Archive date
  - File size
  - File type

Manifest files are named: `manifest_YYYYMMDD_HHMMSS.json`

## Archive Policies

### Recommended Archive Intervals

- **Reports**: Archive quarterly (90 days) or annually
- **Documentation**: Archive annually (365 days)
- **Scripts**: Archive when deprecated or replaced (manual or 365+ days)
- **Financial Data**: Keep source data, archive only processed/duplicate files

### Best Practices

1. **Always use dry-run first**: Preview what will be archived before running
2. **Review manifests**: Check manifest files to track what was archived
3. **Backup important data**: Ensure important files are backed up before archiving
4. **Regular archiving**: Schedule regular archiving to keep directories clean
5. **Document archive decisions**: Note why files were archived in commit messages

## Archive Structure Preservation

The archive script preserves the relative directory structure of files. For example:

- `reports/2025/q1_report.csv` → `reports/archive/2025/01/2025/q1_report.csv`
- `docs/guide.md` → `docs/archive/2025/guide.md`

## Logging

All archive operations are logged to `logs/archive.log` with:
- Timestamp
- Log level (INFO, WARNING, ERROR)
- Operation details
- File paths
- Errors (if any)

## Restoring Archived Files

To restore archived files:

1. Locate the file in the archive directory
2. Check the manifest to find the original location
3. Copy or move the file back to its original location

Example:
```bash
# Find file in manifest
cat archive/manifests/manifest_20260101_120000.json | grep "filename"

# Restore file
cp reports/archive/2025/01/filename.csv reports/
```

## Troubleshooting

### Files Not Being Archived

- Check file modification dates (files must be older than `--age-days`)
- Verify file extensions match `--extensions` filter
- Ensure files are not already in archive directories
- Check logs for error messages

### Duplicate Files in Archive

If a file with the same name already exists in the archive, the script will:
- Add a numeric suffix (e.g., `file_1.csv`, `file_2.csv`)
- Log a warning message

### Archive Directories Not Created

The script automatically creates archive directories as needed. If creation fails:
- Check file permissions
- Verify disk space
- Review error logs

## Automation

You can automate archiving using:

- **Cron jobs** (Linux/Mac):
  ```bash
  0 0 1 * * cd /path/to/fbargarage && python scripts/archive_files.py --type reports --age-days 90
  ```

- **Task Scheduler** (Windows):
  - Create a scheduled task to run the archive script monthly

- **Git hooks**: Add archive operations to pre-commit hooks (not recommended for large operations)

## Questions or Issues

For questions about archiving or to report issues, please:
1. Check the logs in `logs/archive.log`
2. Review the manifest files
3. Open an issue on GitHub
