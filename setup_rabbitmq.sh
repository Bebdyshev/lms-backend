#!/bin/bash

# 🐰 LMS RabbitMQ Integration Setup & Test Script
# Этот скрипт настраивает и тестирует интеграцию LMS с Central Auth Service через RabbitMQ

set -e  # Exit on error

echo "=================================================="
echo "🚀 LMS RabbitMQ Integration Setup"
echo "=================================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Check RabbitMQ connection
echo ""
echo "📡 Step 1: Checking RabbitMQ connection..."
if nc -zv localhost 5672 2>&1 | grep -q succeeded; then
    echo -e "${GREEN}✅ RabbitMQ is running on localhost:5672${NC}"
else
    echo -e "${RED}❌ RabbitMQ is not accessible on localhost:5672${NC}"
    echo "Please start RabbitMQ first:"
    echo "  cd /path/to/central-service-master"
    echo "  docker-compose up -d rabbitmq"
    exit 1
fi

# 2. Check environment variables
echo ""
echo "📝 Step 2: Checking environment variables..."
if grep -q "RABBITMQ_URL=" .env; then
    echo -e "${GREEN}✅ RABBITMQ_URL is configured in .env${NC}"
    grep "RABBITMQ_URL=" .env
else
    echo -e "${RED}❌ RABBITMQ_URL not found in .env${NC}"
    echo "Please add to .env:"
    echo "  RABBITMQ_URL=amqp://auth:PASSWORD@localhost:5672/"
    exit 1
fi

# 3. Install dependencies
echo ""
echo "📦 Step 3: Installing Python dependencies..."
if python3 -m pip show pika > /dev/null 2>&1; then
    echo -e "${GREEN}✅ pika is already installed${NC}"
else
    echo "Installing pika..."
    python3 -m pip install pika==1.3.2
fi

# 4. Test RabbitMQ connection from Python
echo ""
echo "🔌 Step 4: Testing RabbitMQ connection..."
python3 - <<EOF
import pika
import os
from dotenv import load_dotenv

load_dotenv()

try:
    rabbitmq_url = os.getenv('RABBITMQ_URL')
    if not rabbitmq_url:
        print("❌ RABBITMQ_URL not found in environment")
        exit(1)
    
    # Remove credentials from display
    display_url = rabbitmq_url.replace(rabbitmq_url.split('@')[0].split('//')[1], 'auth:***')
    print(f"Connecting to: {display_url}")
    
    connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
    channel = connection.channel()
    
    # Check exchange
    channel.exchange_declare(
        exchange='user_events',
        exchange_type='topic',
        durable=True,
        passive=True  # Only check if exists
    )
    
    connection.close()
    print("✅ Successfully connected to RabbitMQ!")
    print("✅ Exchange 'user_events' exists")
    exit(0)
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ RabbitMQ connection test passed${NC}"
else
    echo -e "${RED}❌ RabbitMQ connection test failed${NC}"
    exit 1
fi

# 5. Show next steps
echo ""
echo "=================================================="
echo "✅ Setup Complete!"
echo "=================================================="
echo ""
echo "🎯 Next steps:"
echo ""
echo "1️⃣  Start LMS backend (consumer will auto-start):"
echo "   uvicorn src.app:app --reload"
echo ""
echo "2️⃣  Check logs for consumer status:"
echo "   Look for: ✅ RabbitMQ consumer initialized"
echo "   Look for: 🧵 RabbitMQ consumer thread started"
echo ""
echo "3️⃣  Test with Central Auth:"
echo "   - Create/update user in Central Auth frontend"
echo "   - Check LMS logs for: 📨 Received event"
echo ""
echo "4️⃣  OR run manual test:"
echo "   python3 test_rabbitmq.py"
echo ""
echo "5️⃣  Check RabbitMQ Management UI:"
echo "   http://localhost:15672"
echo "   Username: auth"
echo "   Password: NXsgvjB5Ff3VWHiKra1Boc3YIoXWAQYE2FBAikXNGg4="
echo ""
echo "📚 Documentation: RABBITMQ_INTEGRATION.md"
echo "=================================================="
