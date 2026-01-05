#!/bin/bash

# WhatsApp API Nginx & SSL Setup Script
# Run with: sudo ./setup-nginx-ssl.sh

set -e

echo "=========================================="
echo "WhatsApp API - Nginx & SSL Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (use sudo)"
    exit 1
fi

DOMAIN="whatsapp-api.lumiera.paris"
CONFIG_FILE="/home/ceeai/whatsapp_api/whatsapp-api.lumiera.paris.conf"
SITES_AVAILABLE="/etc/nginx/sites-available/whatsapp-api.lumiera.paris.conf"
SITES_ENABLED="/etc/nginx/sites-enabled/whatsapp-api.lumiera.paris.conf"

echo "Step 1: Checking DNS resolution..."
if host $DOMAIN > /dev/null 2>&1; then
    echo "✓ DNS is configured for $DOMAIN"
    host $DOMAIN
else
    echo "⚠ Warning: DNS not yet propagated for $DOMAIN"
    echo "  Please ensure DNS A record is added before continuing."
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Step 2: Installing nginx configuration..."
cp $CONFIG_FILE $SITES_AVAILABLE
echo "✓ Config copied to sites-available"

# Remove SSL certificate lines temporarily (will be added by certbot)
sed -i '/ssl_certificate/d' $SITES_AVAILABLE
echo "✓ Removed SSL certificate lines (certbot will add them)"

if [ -L $SITES_ENABLED ]; then
    echo "✓ Symlink already exists"
else
    ln -s $SITES_AVAILABLE $SITES_ENABLED
    echo "✓ Created symlink in sites-enabled"
fi

echo ""
echo "Step 3: Testing nginx configuration..."
if nginx -t; then
    echo "✓ Nginx configuration is valid"
else
    echo "✗ Nginx configuration test failed"
    exit 1
fi

echo ""
echo "Step 4: Reloading nginx..."
systemctl reload nginx
echo "✓ Nginx reloaded"

echo ""
echo "Step 5: Checking if certbot is installed..."
if command -v certbot &> /dev/null; then
    echo "✓ Certbot is already installed"
else
    echo "Installing certbot..."
    apt update
    apt install -y certbot python3-certbot-nginx
    echo "✓ Certbot installed"
fi

echo ""
echo "Step 6: Obtaining SSL certificate..."
echo "This will prompt you for an email address if it's the first time."
echo ""

certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email || \
certbot --nginx -d $DOMAIN

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ SSL certificate obtained successfully!"
else
    echo ""
    echo "⚠ SSL certificate setup may have issues. You can run certbot manually:"
    echo "   sudo certbot --nginx -d $DOMAIN"
fi

echo ""
echo "Step 7: Reloading nginx with SSL..."
systemctl reload nginx
echo "✓ Nginx reloaded with SSL"

echo ""
echo "=========================================="
echo "✓ Setup Complete!"
echo "=========================================="
echo ""
echo "Your WhatsApp API is now available at:"
echo "  https://$DOMAIN"
echo ""
echo "Test it with:"
echo "  curl https://$DOMAIN/health"
echo ""
echo "Next step: Configure Twilio webhook to:"
echo "  https://$DOMAIN/webhook/whatsapp"
echo ""
