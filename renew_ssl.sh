#!/bin/bash
# Renew SSL certificates and restart nginx

echo "🔄 Renewing SSL certificates..."

# Renew certificates
sudo certbot renew --quiet

# Restart nginx container
cd ~/lms-master/backend
docker compose restart nginx

echo "✅ SSL certificates renewed and nginx restarted!"




