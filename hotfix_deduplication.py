#!/usr/bin/env python3
"""
Production hot-fix script for event deduplication issue.
This is a standalone script that can be run directly on the production server.

Run this on the production server:
    cd ~/projects/lms/backend
    python3 hotfix_deduplication.py
"""

import os
import sys
import shutil
from datetime import datetime

# Colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

def log(msg, color=BLUE):
    print(f"{color}{msg}{NC}")

def main():
    log("="*60)
    log("  Event Deduplication Hot-Fix")
    log("="*60)
    print()
    
    # Verify we're in the right directory
    if not os.path.exists('src/services/event_service.py'):
        log("ERROR: Not in backend directory!", RED)
        log("Please cd to ~/projects/lms/backend first", YELLOW)
        sys.exit(1)
    
    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backups/hotfix_{timestamp}"
    os.makedirs(backup_dir, exist_ok=True)
    
    log(f"Creating backup in {backup_dir}...", YELLOW)
    shutil.copy2('src/services/event_service.py', f'{backup_dir}/event_service.py')
    shutil.copy2('src/routes/events.py', f'{backup_dir}/events.py')
    log("✓ Backup created", GREEN)
    print()
    
    # Fix 1: event_service.py
    log("Patching src/services/event_service.py...", YELLOW)
    
    with open('src/services/event_service.py', 'r') as f:
        content = f.read()
    
    # Add parent_group_ids extraction
    content = content.replace(
        '            original_start_day = parent.start_datetime.day\n            \n            # Simple iteration',
        '            original_start_day = parent.start_datetime.day\n            \n            # Pre-extract group IDs from parent (relationships won\'t work on transient objects)\n            parent_group_ids = [eg.group_id for eg in parent.event_groups] if parent.event_groups else []\n            \n            # Simple iteration'
    )
    
    # Add _group_ids to virtual events
    content = content.replace(
        '                    )\n                    # Attach relationship data manually',
        '                    )\n                    # Store group_ids directly for deduplication (relationships don\'t copy to transient objects)\n                    virtual_event._group_ids = parent_group_ids\n                    # Attach relationship data manually'
    )
    
    with open('src/services/event_service.py', 'w') as f:
        f.write(content)
    
    log("✓ event_service.py patched", GREEN)
    print()
    
    # Fix 2: events.py
    log("Patching src/routes/events.py...", YELLOW)
    
    with open('src/routes/events.py', 'r') as f:
        content = f.read()
    
    # Fix deduplication in /my endpoint
    content = content.replace(
        '        for e in events:\n            # Group IDs directly linked\n            e_group_ids = [eg.group_id for eg in e.event_groups] if hasattr(e, \'event_groups\') else []',
        '        for e in events:\n            # Group IDs directly linked OR from _group_ids for virtual events\n            virtual_gids = getattr(e, \'_group_ids\', None)\n            e_group_ids = virtual_gids or ([eg.group_id for eg in e.event_groups] if hasattr(e, \'event_groups\') else [])'
    )
    
    # Fix deduplication in /calendar endpoint
    content = content.replace(
        '        for e in all_events:\n            # Group IDs directly linked\n            e_group_ids = [eg.group_id for eg in e.event_groups] if hasattr(e, \'event_groups\') else []',
        '        for e in all_events:\n            # Group IDs directly linked OR from _group_ids for virtual events\n            e_group_ids = getattr(e, \'_group_ids\', None) or [eg.group_id for eg in e.event_groups] if hasattr(e, \'event_groups\') else []'
    )
    
    # Fix relevant_groups
    content = content.replace(
        '        relevant_groups = [group_id] if group_id else [eg.group_id for eg in e.event_groups]',
        '        # Use _group_ids for virtual events\n        virtual_group_ids = getattr(e, \'_group_ids\', None)\n        if virtual_group_ids:\n            relevant_groups = [group_id] if group_id else virtual_group_ids\n        else:\n            relevant_groups = [group_id] if group_id else [eg.group_id for eg in e.event_groups]'
    )
    
    # Fix group_names extraction
    content = content.replace(
        '        # Add group names\n        group_names = [eg.group.name for eg in event.event_groups if eg.group]\n        event_data.groups = group_names\n        \n        # Add group IDs - CRITICAL for frontend filtering\n        event_data.group_ids = [eg.group_id for eg in event.event_groups]',
        '        # Add group names - use _group_ids for virtual events\n        virtual_group_ids = getattr(event, \'_group_ids\', None)\n        if virtual_group_ids:\n            # For virtual events, fetch group names\n            groups = db.query(Group).filter(Group.id.in_(virtual_group_ids)).all()\n            group_names = [g.name for g in groups]\n            event_data.group_ids = virtual_group_ids\n        else:\n            group_names = [eg.group.name for eg in event.event_groups if eg.group]\n            event_data.group_ids = [eg.group_id for eg in event.event_groups]\n        event_data.groups = group_names'
    )
    
    with open('src/routes/events.py', 'w') as f:
        f.write(content)
    
    log("✓ events.py patched", GREEN)
    print()
    
    log("="*60, GREEN)
    log("  Hot-fix applied successfully!", GREEN)
    log("="*60, GREEN)
    print()
    
    log("Next steps:", YELLOW)
    log("  1. Restart backend: docker-compose restart web")
    log("  2. Check logs: docker-compose logs -f web")
    log("  3. Test calendar in browser")
    print()
    
    log(f"Rollback if needed:", YELLOW)
    log(f"  cp {backup_dir}/event_service.py src/services/")
    log(f"  cp {backup_dir}/events.py src/routes/")
    log("  docker-compose restart web")
    print()

if __name__ == '__main__':
    main()
