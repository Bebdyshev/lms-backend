#!/bin/bash
# Sync deduplication fix files to production server

SERVER="root@your-server-ip"
REMOTE_PATH="~/projects/lms/backend"

echo "=== Syncing Deduplication Fix to Production ==="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}This will copy:${NC}"
echo "  1. Updated event_service.py"
echo "  2. Updated events.py"
echo "  3. Deployment scripts"
echo "  4. Documentation"
echo ""

read -p "Enter your server address (e.g., root@1.2.3.4): " SERVER
if [ -z "$SERVER" ]; then
    echo "Server address required"
    exit 1
fi

echo ""
echo -e "${YELLOW}Copying files...${NC}"

# Copy updated source files
echo "Copying event_service.py..."
scp src/services/event_service.py $SERVER:$REMOTE_PATH/src/services/

echo "Copying events.py..."
scp src/routes/events.py $SERVER:$REMOTE_PATH/src/routes/

# Copy scripts
echo "Copying deployment scripts..."
scp scripts/deploy_deduplication_fix.py $SERVER:$REMOTE_PATH/scripts/
scp scripts/verify_deduplication_fix.py $SERVER:$REMOTE_PATH/scripts/

# Copy documentation
echo "Copying documentation..."
scp DEDUPLICATION_FIX_DEPLOY.md $SERVER:$REMOTE_PATH/

echo ""
echo -e "${GREEN}✓ Files copied successfully${NC}"
echo ""
echo -e "${YELLOW}Next steps on server:${NC}"
echo "  1. SSH to server: ssh $SERVER"
echo "  2. cd $REMOTE_PATH"
echo "  3. python3 scripts/deploy_deduplication_fix.py --dry-run"
echo "  4. python3 scripts/deploy_deduplication_fix.py"
echo "  5. docker-compose restart web"
echo "  6. python3 scripts/verify_deduplication_fix.py"
echo ""
