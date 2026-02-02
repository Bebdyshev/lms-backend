#!/bin/bash
# Script to fix event deduplication on production server
# This fixes the root cause of duplicate calendar events

set -e  # Exit on error

echo "=== Event Deduplication Fix Deployment ==="
echo "This will fix duplicate events in calendar by:"
echo "1. Adding _group_ids to virtual events in EventService"
echo "2. Updating deduplication logic in events.py"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're on production server
if [ -f "/.dockerenv" ] || [ -f "/etc/docker" ]; then
    echo -e "${YELLOW}Running inside Docker container${NC}"
    IS_DOCKER=true
else
    echo -e "${YELLOW}Running on host machine${NC}"
    IS_DOCKER=false
fi

# Backup current files
BACKUP_DIR="backups/deduplication_fix_$(date +%Y%m%d_%H%M%S)"
echo -e "${YELLOW}Creating backup in $BACKUP_DIR${NC}"
mkdir -p "$BACKUP_DIR"

cp src/services/event_service.py "$BACKUP_DIR/"
cp src/routes/events.py "$BACKUP_DIR/"

echo -e "${GREEN}✓ Backup created${NC}"

# Apply fix to event_service.py
echo -e "${YELLOW}Applying fix to event_service.py${NC}"

# The fix adds _group_ids extraction before the loop
python3 << 'EOF'
import sys

file_path = "src/services/event_service.py"
with open(file_path, 'r') as f:
    content = f.read()

# Find and replace the virtual event creation section
old_text = """            original_start_day = parent.start_datetime.day
            
            # Simple iteration (TODO: Optimize fast-forward if needed)
            while current_start <= end_date:"""

new_text = """            original_start_day = parent.start_datetime.day
            
            # Pre-extract group IDs from parent (relationships won't work on transient objects)
            parent_group_ids = [eg.group_id for eg in parent.event_groups] if parent.event_groups else []
            
            # Simple iteration (TODO: Optimize fast-forward if needed)
            while current_start <= end_date:"""

if old_text in content:
    content = content.replace(old_text, new_text)
    
    # Now add _group_ids assignment after virtual_event creation
    old_creation = """                    virtual_event = Event(
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
    
    new_creation = """                    virtual_event = Event(
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
    
    if old_creation in content:
        content = content.replace(old_creation, new_creation)
        with open(file_path, 'w') as f:
            f.write(content)
        print("✓ event_service.py updated successfully")
        sys.exit(0)
    else:
        print("✗ Could not find virtual_event creation block")
        sys.exit(1)
else:
    print("✗ Could not find original_start_day section")
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ event_service.py fixed${NC}"
else
    echo -e "${RED}✗ Failed to fix event_service.py${NC}"
    exit 1
fi

# Apply fix to events.py
echo -e "${YELLOW}Applying fix to events.py${NC}"

python3 << 'EOF'
import sys
import re

file_path = "src/routes/events.py"
with open(file_path, 'r') as f:
    content = f.read()

changes_made = 0

# Fix 1: Update deduplication in /my endpoint (around line 180)
pattern1 = r"(\s+)# For events with multiple groups.*?\n\s+# If group_id filter was used.*?\n\s+relevant_groups = \[group_id\] if group_id else \[eg\.group_id for eg in e\.event_groups\]"
replacement1 = r"""\1# For events with multiple groups, we check if WE (the user) are interested in this one
\1# If group_id filter was used, check only that
\1# Use _group_ids for virtual events
\1virtual_group_ids = getattr(e, '_group_ids', None)
\1if virtual_group_ids:
\1    relevant_groups = [group_id] if group_id else virtual_group_ids
\1else:
\1    relevant_groups = [group_id] if group_id else [eg.group_id for eg in e.event_groups]"""

if re.search(pattern1, content):
    content = re.sub(pattern1, replacement1, content)
    changes_made += 1

# Fix 2: Update existing_event_map in /my endpoint
old_map_my = """        # Deduplication map
        existing_event_map = set()
        for e in events:
            # Group IDs directly linked
            e_group_ids = [eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else []"""

new_map_my = """        # Deduplication map
        existing_event_map = set()
        for e in events:
            # Group IDs directly linked OR from _group_ids for virtual events
            virtual_gids = getattr(e, '_group_ids', None)
            e_group_ids = virtual_gids or ([eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else [])"""

if old_map_my in content:
    content = content.replace(old_map_my, new_map_my)
    changes_made += 1

# Fix 3: Update existing_event_map in /calendar endpoint
old_map_cal = """        existing_event_map = set()
        for e in all_events:
            # Group IDs directly linked
            e_group_ids = [eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else []"""

new_map_cal = """        existing_event_map = set()
        for e in all_events:
            # Group IDs directly linked OR from _group_ids for virtual events
            e_group_ids = getattr(e, '_group_ids', None) or [eg.group_id for eg in e.event_groups] if hasattr(e, 'event_groups') else []"""

if old_map_cal in content:
    content = content.replace(old_map_cal, new_map_cal)
    changes_made += 1

# Fix 4: Update /calendar event enrichment
old_enrich = """    for event in all_events:
        # For virtual events, we might need to handle schema conversion manually 
        # because they are not attached to session
        
        event_data = EventSchema.from_orm(event)
        
        # Add creator name
        event_data.creator_name = event.creator.name if event.creator else "Unknown"
        
        # Add group names
        group_names = [eg.group.name for eg in event.event_groups if eg.group]
        event_data.groups = group_names
        
        # Add group IDs - CRITICAL for frontend filtering
        event_data.group_ids = [eg.group_id for eg in event.event_groups]"""

new_enrich = """    for event in all_events:
        # For virtual events, we might need to handle schema conversion manually 
        # because they are not attached to session
        
        event_data = EventSchema.from_orm(event)
        
        # Add creator name
        event_data.creator_name = event.creator.name if event.creator else "Unknown"
        
        # Add group names - use _group_ids for virtual events
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

if old_enrich in content:
    content = content.replace(old_enrich, new_enrich)
    changes_made += 1

if changes_made >= 3:  # At least 3 out of 4 fixes should be applied
    with open(file_path, 'w') as f:
        f.write(content)
    print(f"✓ events.py updated successfully ({changes_made} changes)")
    sys.exit(0)
else:
    print(f"✗ Only {changes_made} changes applied, expected at least 3")
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ events.py fixed${NC}"
else
    echo -e "${RED}✗ Failed to fix events.py${NC}"
    echo -e "${YELLOW}Restoring from backup...${NC}"
    cp "$BACKUP_DIR/event_service.py" src/services/
    cp "$BACKUP_DIR/events.py" src/routes/
    exit 1
fi

echo ""
echo -e "${GREEN}=== All fixes applied successfully ===${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Test the changes locally"
echo "2. Restart the backend service:"
echo "   - Docker: docker-compose restart web"
echo "   - SystemD: sudo systemctl restart lms-backend"
echo ""
echo -e "${YELLOW}Backup location: $BACKUP_DIR${NC}"
echo ""
echo -e "${GREEN}To rollback if needed:${NC}"
echo "  cp $BACKUP_DIR/event_service.py src/services/"
echo "  cp $BACKUP_DIR/events.py src/routes/"
echo "  docker-compose restart web"
