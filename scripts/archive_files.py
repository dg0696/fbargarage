#!/usr/bin/env python3
"""
Archive Files Script

Moves old files to archive folders based on date/age criteria.
Organizes archived files by year/month and preserves file structure.
Generates archive manifest and logs operations.
"""

import argparse
import json
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


class FileArchiver:
    """Handles archiving of files based on age and type."""
    
    def __init__(self, dry_run: bool = False):
        """Initialize the archiver.
        
        Args:
            dry_run: If True, preview operations without moving files
        """
        self.dry_run = dry_run
        self.manifest: List[Dict] = []
        self.setup_logging()
        
    def setup_logging(self):
        """Set up logging configuration."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "archive.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def get_file_age_days(self, file_path: Path) -> int:
        """Get the age of a file in days.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Age in days
        """
        if not file_path.exists():
            return 0
        
        # Use modification time
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        age = datetime.now() - mtime
        return age.days
    
    def get_archive_path(self, source_path: Path, archive_base: Path, file_type: str) -> Path:
        """Determine the archive path for a file.
        
        Args:
            source_path: Original file path
            archive_base: Base archive directory
            file_type: Type of file (reports, docs, scripts, financials)
            
        Returns:
            Archive path
        """
        # Get file modification date
        mtime = datetime.fromtimestamp(source_path.stat().st_mtime)
        year = mtime.strftime("%Y")
        month = mtime.strftime("%m")
        
        # Determine archive structure based on type
        if file_type == "reports":
            archive_dir = archive_base / "reports" / "archive" / year / month
        elif file_type == "docs":
            archive_dir = archive_base / "docs" / "archive" / year
        elif file_type == "scripts":
            archive_dir = archive_base / "archive" / "scripts" / year
        elif file_type == "financials":
            archive_dir = archive_base / "financials" / "archive" / year
        else:
            archive_dir = archive_base / "archive" / year
        
        # Preserve relative path structure
        # If file is in a subdirectory, maintain that structure
        relative_path = source_path.relative_to(Path.cwd())
        if len(relative_path.parts) > 1:
            # Keep subdirectory structure
            subdir = Path(*relative_path.parts[:-1])
            archive_dir = archive_dir / subdir
        
        archive_dir.mkdir(parents=True, exist_ok=True)
        return archive_dir / source_path.name
    
    def archive_file(self, source_path: Path, archive_base: Path, file_type: str) -> bool:
        """Archive a single file.
        
        Args:
            source_path: Path to file to archive
            archive_base: Base directory for archives
            file_type: Type of file
            
        Returns:
            True if archived successfully, False otherwise
        """
        try:
            archive_path = self.get_archive_path(source_path, archive_base, file_type)
            
            # Check if file already exists in archive
            if archive_path.exists():
                self.logger.warning(f"File already exists in archive: {archive_path}")
                # Add suffix to avoid overwriting
                stem = archive_path.stem
                suffix = archive_path.suffix
                counter = 1
                while archive_path.exists():
                    archive_path = archive_path.parent / f"{stem}_{counter}{suffix}"
                    counter += 1
            
            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would archive: {source_path} -> {archive_path}")
            else:
                shutil.move(str(source_path), str(archive_path))
                self.logger.info(f"Archived: {source_path} -> {archive_path}")
            
            # Add to manifest
            file_size = source_path.stat().st_size if source_path.exists() else 0
            self.manifest.append({
                "original_path": str(source_path),
                "archived_path": str(archive_path),
                "archive_date": datetime.now().isoformat(),
                "file_size": file_size,
                "file_type": file_type
            })
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error archiving {source_path}: {e}")
            return False
    
    def archive_directory(self, source_dir: Path, archive_base: Path, 
                         file_type: str, age_days: int, extensions: Optional[List[str]] = None) -> int:
        """Archive files in a directory based on age.
        
        Args:
            source_dir: Directory to archive from
            archive_base: Base archive directory
            file_type: Type of files
            age_days: Minimum age in days
            extensions: Optional list of file extensions to include (e.g., ['.csv', '.pdf'])
            
        Returns:
            Number of files archived
        """
        if not source_dir.exists():
            self.logger.warning(f"Source directory does not exist: {source_dir}")
            return 0
        
        archived_count = 0
        
        # Walk through directory
        for root, dirs, files in os.walk(source_dir):
            # Skip archive directories
            if "archive" in root:
                continue
                
            for file in files:
                file_path = Path(root) / file
                
                # Check extension filter
                if extensions and file_path.suffix.lower() not in extensions:
                    continue
                
                # Check age
                age = self.get_file_age_days(file_path)
                if age >= age_days:
                    if self.archive_file(file_path, archive_base, file_type):
                        archived_count += 1
        
        return archived_count
    
    def save_manifest(self, manifest_path: Path):
        """Save archive manifest to JSON file.
        
        Args:
            manifest_path: Path to save manifest
        """
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        manifest_data = {
            "archive_date": datetime.now().isoformat(),
            "total_files": len(self.manifest),
            "files": self.manifest
        }
        
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2)
        
        self.logger.info(f"Manifest saved to: {manifest_path}")


def main():
    """Main entry point for the archive script."""
    parser = argparse.ArgumentParser(
        description="Archive old files based on age and type",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview archiving reports older than 90 days
  python scripts/archive_files.py --type reports --age-days 90 --dry-run
  
  # Archive old documentation files
  python scripts/archive_files.py --type docs --age-days 180
  
  # Archive scripts older than 365 days
  python scripts/archive_files.py --type scripts --age-days 365
        """
    )
    
    parser.add_argument(
        "--source-dir",
        type=str,
        help="Directory to archive from (default: current directory)"
    )
    
    parser.add_argument(
        "--age-days",
        type=int,
        default=90,
        help="Minimum age in days to archive (default: 90)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be archived without moving files"
    )
    
    parser.add_argument(
        "--type",
        choices=["reports", "docs", "scripts", "financials", "all"],
        default="all",
        help="Type of files to archive (default: all)"
    )
    
    parser.add_argument(
        "--extensions",
        type=str,
        help="Comma-separated list of file extensions to include (e.g., .csv,.pdf)"
    )
    
    args = parser.parse_args()
    
    # Set up archiver
    archiver = FileArchiver(dry_run=args.dry_run)
    
    # Determine source directory
    source_dir = Path(args.source_dir) if args.source_dir else Path.cwd()
    archive_base = Path.cwd()
    
    # Parse extensions
    extensions = None
    if args.extensions:
        extensions = [ext.strip() for ext in args.extensions.split(",")]
    
    # Archive based on type
    archived_count = 0
    
    if args.type == "reports" or args.type == "all":
        reports_dir = source_dir / "reports"
        if reports_dir.exists():
            count = archiver.archive_directory(
                reports_dir, archive_base, "reports", args.age_days, extensions
            )
            archived_count += count
            archiver.logger.info(f"Archived {count} report files")
    
    if args.type == "docs" or args.type == "all":
        docs_dir = source_dir / "docs"
        if docs_dir.exists():
            count = archiver.archive_directory(
                docs_dir, archive_base, "docs", args.age_days, extensions
            )
            archived_count += count
            archiver.logger.info(f"Archived {count} documentation files")
    
    if args.type == "scripts" or args.type == "all":
        scripts_dir = source_dir / "scripts"
        if scripts_dir.exists():
            count = archiver.archive_directory(
                scripts_dir, archive_base, "scripts", args.age_days, extensions
            )
            archived_count += count
            archiver.logger.info(f"Archived {count} script files")
    
    if args.type == "financials" or args.type == "all":
        financials_dir = source_dir / "financials"
        if financials_dir.exists():
            count = archiver.archive_directory(
                financials_dir, archive_base, "financials", args.age_days, extensions
            )
            archived_count += count
            archiver.logger.info(f"Archived {count} financial files")
    
    # Save manifest
    if archiver.manifest:
        manifest_path = archive_base / "archive" / "manifests" / f"manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        archiver.save_manifest(manifest_path)
    
    archiver.logger.info(f"Total files archived: {archived_count}")
    
    if args.dry_run:
        archiver.logger.info("This was a dry run. No files were actually moved.")


if __name__ == "__main__":
    main()
