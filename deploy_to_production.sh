#!/bin/bash
# One-command deployment for event deduplication fix
# Run this on your LOCAL machine

echo "================================================================"
echo "  Event Deduplication Fix - Quick Deploy"
echo "================================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "src/services/event_service.py" ]; then
    echo "❌ Error: Not in backend directory!"
    echo "Please run: cd /Users/bebdyshev/Documents/Github/lms/backend"
    exit 1
fi

# Prompt for server address
read -p "Enter server address (e.g., root@1.2.3.4 or root@yourserver.com): " SERVER

if [ -z "$SERVER" ]; then
    echo "❌ Server address required"
    exit 1
fi

echo ""
echo "📦 Copying files to $SERVER..."
echo ""

# Copy files
scp src/services/event_service.py $SERVER:/root/projects/lms/src/services/ && \
scp src/routes/events.py $SERVER:/root/projects/lms/src/routes/

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Files copied successfully!"
    echo ""
    echo "================================================================"
    echo "  Next: Run these commands on your SERVER"
    echo "================================================================"
    echo ""
    echo "ssh $SERVER"
    echo "cd /root/projects/lms"
    echo "docker-compose restart web"
    echo "docker-compose logs web | tail -30"
    echo ""
    echo "Then check your calendar in browser - duplicates should be gone!"
    echo ""
else
    echo ""
    echo "❌ Failed to copy files"
    echo "Please check:"
    echo "  1. Server address is correct"
    echo "  2. You have SSH access"
    echo "  3. Path /root/projects/lms exists on server"
    echo ""
fi
