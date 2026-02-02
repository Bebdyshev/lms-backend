#!/usr/bin/env python3
"""
Production deployment script for event deduplication fix.
This script can be run directly on the production server.

Usage:
    python3 deploy_deduplication_fix.py [--dry-run] [--backup-only]
"""

import os
import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# ANSI colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

def log_info(msg):
    print(f"{BLUE}ℹ {msg}{NC}")

def log_success(msg):
    print(f"{GREEN}✓ {msg}{NC}")

def log_warning(msg):
    print(f"{YELLOW}⚠ {msg}{NC}")

def log_error(msg):
    print(f"{RED}✗ {msg}{NC}")

def create_backup(files, backup_dir):
    """Create backup of specified files"""
    log_info(f"Creating backup in {backup_dir}")
    os.makedirs(backup_dir, exist_ok=True)
    
    for file_path in files:
        if os.path.exists(file_path):
            backup_path = os.path.join(backup_dir, os.path.basename(file_path))
            shutil.copy2(file_path, backup_path)
            log_success(f"Backed up {file_path}")
        else:
            log_warning(f"File not found: {file_path}")
    
    return True

def apply_event_service_fix(file_path, dry_run=False):
    """Apply fix to event_service.py"""
    log_info(f"Applying fix to {file_path}")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Fix 1: Add parent_group_ids extraction
    old_text1 = """            original_start_day = parent.start_datetime.day
            
            # Simple iteration (TODO: Optimize fast-forward if needed)
            while current_start <= end_date:"""
    
    new_text1 = """            original_start_day = parent.start_datetime.day
            
            # Pre-extract group IDs from parent (relationships won't work on transient objects)
            parent_group_ids = [eg.group_id for eg in parent.event_groups] if parent.event_groups else []
            
            # Simple iteration (TODO: Optimize fast-forward if needed)
            while current_start <= end_date:"""
    
    if old_text1 not in content:
        log_warning("Fix 1 pattern not found - may already be applied")
    else:
        content = content.replace(old_text1, new_text1)
        log_success("Fix 1: Added parent_group_ids extraction")
    
    # Fix 2: Add _group_ids assignment to virtual events
    old_text2 = """                    virtual_event = Event(
                        id=pseudo_id,
                        title=parent.title,
                        description=parent.description,
                        event_type=parent.event_type,
                        start_datetime=current_start,
                        end_datetime=current_start + duration,
                        location=parent.location,
                        is_online=parent.is_online,
                        meeting_url=parent.meeting_url,
                        created_by=parent.created_by,
                        is_recurring=True,
                        recurrence_pattern=parent.recurrence_pattern,
                        max_participants=parent.max_participants,
                        creator=parent.creator,
                        event_groups=parent.event_groups,
                        created_at=parent.created_at,
                        updated_at=parent.updated_at,
                        is_active=True
                    )
                    # Attach relationship data manually if needed by schema
                    # (SQLAlchemy might not attach relations to transient objects automatically in standard way, 
                    # but since we copied them from parent loaded from DB, they are available objects)
                    
                    generated_events.append(virtual_event)"""
    
    new_text2 = """                    virtual_event = Event(
                        id=pseudo_id,
                        title=parent.title,
                        description=parent.description,
                        event_type=parent.event_type,
                        start_datetime=current_start,
                        end_datetime=current_start + duration,
                        location=parent.location,
                        is_online=parent.is_online,
                        meeting_url=parent.meeting_url,
                        created_by=parent.created_by,
                        is_recurring=True,
                        recurrence_pattern=parent.recurrence_pattern,
                        max_participants=parent.max_participants,
                        creator=parent.creator,
                        event_groups=parent.event_groups,  # Keep for first instance
                        created_at=parent.created_at,
                        updated_at=parent.updated_at,
                        is_active=True
                    )
                    # Store group_ids directly for deduplication (relationships don't copy to transient objects)
                    virtual_event._group_ids = parent_group_ids
                    
                    generated_events.append(virtual_event)"""
    
    if old_text2 not in content:
        log_warning("Fix 2 pattern not found - may already be applied")
    else:
        content = content.replace(old_text2, new_text2)
        log_success("Fix 2: Added _group_ids assignment")
    
    if content == original_content:
        log_warning("No changes made to event_service.py")
        return False
    
    if not dry_run:
        with open(file_path, 'w') as f:
            f.write(content)
        log_success(f"Updated {file_path}")
    else:
        log_info("DRY RUN - changes not written")
    
    return True

def apply_events_fix(file_path, dry_run=False):
    """Apply fix to events.py"""
    log_info(f"Applying fix to {file_path}")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    original_content = content
    changes_count = 0
    
    # Fix 1: Update relevant_groups in /my endpoint
    old1 = """        # For events with multiple groups, we check if WE (the user) are interested in this one
        # If group_id filter was used, check only that
        relevant_groups = [group_id] if group_id else [eg.group_id for eg in e.event_groups]"""
    
    new1 = """        # For events with multiple groups, we check if WE (the user) are interested in this one
        # If group_id filter was used, check only that
        # Use _group_ids for virtual events
        virtual_group_ids = getattr(e, '_group_ids', None)
        if virtual_group_ids:
            relevant_groups = [group_id] if group_id else virtual_group_ids
        else:
            relevant_groups = [group_id] if group_id else [eg.group_id for eg in e.event_groups]"""
    
    if old1 in content:
        content = content.replace(old1, new1)
        changes_count += 1
        log_success("Fix 1: Updated relevant_groups logic in /my")
    
    # Fix 2: Update existing_event_map in /my endpoint
    old2 = """        # Deduplication map
        existing_event_map = set()
        for e in events:
            # Group IDs directly linked
            e_group_ids = [eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else []"""
    
    new2 = """        # Deduplication map
        existing_event_map = set()
        for e in events:
            # Group IDs directly linked OR from _group_ids for virtual events
            virtual_gids = getattr(e, '_group_ids', None)
            e_group_ids = virtual_gids or ([eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else [])"""
    
    if old2 in content:
        content = content.replace(old2, new2)
        changes_count += 1
        log_success("Fix 2: Updated existing_event_map in /my")
    
    # Fix 3: Update existing_event_map in /calendar endpoint
    old3 = """        existing_event_map = set()
        for e in all_events:
            # Group IDs directly linked
            e_group_ids = [eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else []"""
    
    new3 = """        existing_event_map = set()
        for e in all_events:
            # Group IDs directly linked OR from _group_ids for virtual events
            e_group_ids = getattr(e, '_group_ids', None) or [eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else []"""
    
    if old3 in content:
        content = content.replace(old3, new3)
        changes_count += 1
        log_success("Fix 3: Updated existing_event_map in /calendar")
    
    # Fix 4: Update event enrichment in /calendar
    old4 = """        # Add group names
        group_names = [eg.group.name for eg in event.event_groups if eg.group]
        event_data.groups = group_names
        
        # Add group IDs - CRITICAL for frontend filtering
        event_data.group_ids = [eg.group_id for eg in event.event_groups]"""
    
    new4 = """        # Add group names - use _group_ids for virtual events
        virtual_group_ids = getattr(event, '_group_ids', None)
        if virtual_group_ids:
            # For virtual events, fetch group names
            groups = db.query(Group).filter(Group.id.in_(virtual_group_ids)).all()
            group_names = [g.name for g in groups]
            event_data.group_ids = virtual_group_ids
        else:
            group_names = [eg.group.name for eg in event.event_groups if eg.group]
            event_data.group_ids = [eg.group_id for eg in event.event_groups]
        event_data.groups = group_names"""
    
    if old4 in content:
        content = content.replace(old4, new4)
        changes_count += 1
        log_success("Fix 4: Updated event enrichment in /calendar")
    
    if content == original_content:
        log_warning("No changes made to events.py")
        return False
    
    if not dry_run:
        with open(file_path, 'w') as f:
            f.write(content)
        log_success(f"Updated {file_path} ({changes_count} changes)")
    else:
        log_info(f"DRY RUN - {changes_count} changes not written")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Deploy event deduplication fix')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without applying')
    parser.add_argument('--backup-only', action='store_true', help='Only create backup without applying fixes')
    parser.add_argument('--backup-dir', default=None, help='Custom backup directory')
    
    args = parser.parse_args()
    
    print(f"\n{BLUE}{'='*60}{NC}")
    print(f"{BLUE}  Event Deduplication Fix Deployment{NC}")
    print(f"{BLUE}{'='*60}{NC}\n")
    
    if args.dry_run:
        log_warning("DRY RUN MODE - No changes will be applied")
    
    # Determine paths
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent
    
    event_service_path = backend_dir / "src" / "services" / "event_service.py"
    events_path = backend_dir / "src" / "routes" / "events.py"
    
    # Verify files exist
    if not event_service_path.exists():
        log_error(f"File not found: {event_service_path}")
        sys.exit(1)
    
    if not events_path.exists():
        log_error(f"File not found: {events_path}")
        sys.exit(1)
    
    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = args.backup_dir or str(backend_dir / "backups" / f"deduplication_fix_{timestamp}")
    
    files_to_backup = [str(event_service_path), str(events_path)]
    
    if not create_backup(files_to_backup, backup_dir):
        log_error("Backup failed")
        sys.exit(1)
    
    if args.backup_only:
        log_info("Backup-only mode - exiting")
        sys.exit(0)
    
    # Apply fixes
    print()
    success = True
    
    if not apply_event_service_fix(str(event_service_path), args.dry_run):
        success = False
    
    print()
    
    if not apply_events_fix(str(events_path), args.dry_run):
        success = False
    
    print()
    
    if success:
        log_success("All fixes applied successfully!")
        print()
        log_info("Next steps:")
        print("  1. Restart the backend service:")
        print("     - Docker: docker-compose restart web")
        print("     - SystemD: sudo systemctl restart lms-backend")
        print()
        log_info(f"Backup location: {backup_dir}")
        print()
        log_info("To rollback if needed:")
        print(f"  cp {backup_dir}/event_service.py {event_service_path}")
        print(f"  cp {backup_dir}/events.py {events_path}")
        print("  docker-compose restart web")
    else:
        log_warning("Some fixes were not applied - check logs above")
        if not args.dry_run:
            log_warning("Consider rolling back from backup if needed")
    
    print()

if __name__ == "__main__":
    main()
