#!/bin/bash
# Medical AI Assistant - Production Deployment Script
#
# This script automates the deployment process for production
#
# Usage: chmod +x deploy.sh && ./deploy.sh
#
# Prerequisites:
# - Ubuntu/Debian-based system
# - Python 3.9+ installed
# - MySQL/MariaDB running
# - Nginx installed
# - SSL certificate obtained (Let's Encrypt recommended)

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/home/medical-ai/app"
APP_USER="medical-ai"
APP_GROUP="medical-ai"
VENV_DIR="$APP_DIR/venv"
DOMAIN="yourdomain.com"
EMAIL="admin@yourdomain.com"

echo -e "${YELLOW}=== Medical AI Assistant Production Deployment ===${NC}"

# ============================================================================
# Step 1: Validate prerequisites
# ============================================================================
echo -e "\n${YELLOW}Step 1: Checking prerequisites...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Install with: sudo apt install python3${NC}"
    exit 1
fi

if ! command -v mysql &> /dev/null; then
    echo -e "${RED}❌ MySQL client not found. Install with: sudo apt install mysql-client${NC}"
    exit 1
fi

if ! command -v nginx &> /dev/null; then
    echo -e "${YELLOW}⚠️  Nginx not installed. Install with: sudo apt install nginx${NC}"
fi

echo -e "${GREEN}✓ Prerequisites validated${NC}"

# ============================================================================
# Step 2: Create application user and directories
# ============================================================================
echo -e "\n${YELLOW}Step 2: Setting up user and directories...${NC}"

if ! id "$APP_USER" &>/dev/null; then
    echo "Creating user: $APP_USER"
    sudo useradd -r -s /bin/bash -d "$APP_DIR" "$APP_USER" || true
fi

# Create directories
sudo mkdir -p "$APP_DIR"
sudo mkdir -p /var/log/medical-ai
sudo mkdir -p /var/run/medical-ai
sudo mkdir -p "$APP_DIR/uploads"

# Set permissions
sudo chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
sudo chown -R "$APP_USER:$APP_GROUP" /var/log/medical-ai
sudo chown -R "$APP_USER:$APP_GROUP" /var/run/medical-ai
sudo chmod -R 755 "$APP_DIR"
sudo chmod -R 755 /var/log/medical-ai

echo -e "${GREEN}✓ User and directories configured${NC}"

# ============================================================================
# Step 3: Install Python dependencies
# ============================================================================
echo -e "\n${YELLOW}Step 3: Installing Python dependencies...${NC}"

cd "$APP_DIR"

# Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created"
fi

# Activate and upgrade pip
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel

# Install production dependencies
echo "Installing requirements..."
pip install -r requirements.txt
pip install gunicorn

# Install additional production packages
pip install python-dotenv  # For loading .env files

echo -e "${GREEN}✓ Dependencies installed${NC}"

# ============================================================================
# Step 4: Configure environment variables
# ============================================================================
echo -e "\n${YELLOW}Step 4: Configuring environment...${NC}"

if [ ! -f "$APP_DIR/.env" ]; then
    echo "Creating .env file (YOU MUST EDIT THIS WITH REAL VALUES)..."
    cp "$APP_DIR/.env.template" "$APP_DIR/.env"
    sudo chmod 600 "$APP_DIR/.env"
    sudo chown "$APP_USER:$APP_GROUP" "$APP_DIR/.env"
    echo -e "${YELLOW}⚠️  IMPORTANT: Edit $APP_DIR/.env with your production secrets!${NC}"
else
    echo "✓ .env file already exists"
fi

echo -e "${GREEN}✓ Environment configured${NC}"

# ============================================================================
# Step 5: Initialize database
# ============================================================================
echo -e "\n${YELLOW}Step 5: Initializing database...${NC}"

read -p "Initialize database? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    source "$APP_DIR/.env"
    python3 "$APP_DIR/db.py"
    echo -e "${GREEN}✓ Database initialized${NC}"
else
    echo "Skipping database initialization"
fi

# ============================================================================
# Step 6: Generate SSL certificate
# ============================================================================
echo -e "\n${YELLOW}Step 6: SSL Certificate Setup...${NC}"

read -p "Obtain Let's Encrypt certificate? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v certbot &> /dev/null; then
        echo "Getting certificate for $DOMAIN..."
        sudo certbot certonly --standalone -d "$DOMAIN" -d "www.$DOMAIN" -m "$EMAIL" --agree-tos --non-interactive || true
        
        # Generate Diffie-Hellman parameters for stronger security
        if [ ! -f /etc/ssl/certs/dhparam.pem ]; then
            echo "Generating Diffie-Hellman parameters (this takes a minute)..."
            sudo openssl dhparam -out /etc/ssl/certs/dhparam.pem 2048
        fi
        
        echo -e "${GREEN}✓ SSL certificate obtained${NC}"
    else
        echo "Installing Certbot..."
        sudo apt install certbot python3-certbot-nginx -y
        echo -e "${YELLOW}⚠️  Please run: sudo certbot certonly --standalone -d $DOMAIN${NC}"
    fi
else
    echo "Skipping Let's Encrypt setup. Ensure you have SSL certificates at:"
    echo "  /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
    echo "  /etc/letsencrypt/live/$DOMAIN/privkey.pem"
fi

# ============================================================================
# Step 7: Configure Nginx
# ============================================================================
echo -e "\n${YELLOW}Step 7: Configuring Nginx...${NC}"

read -p "Configure Nginx reverse proxy? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Copy and customize Nginx config
    echo "Copying Nginx configuration..."
    sudo cp "$APP_DIR/medical-ai-nginx.conf" /etc/nginx/sites-available/medical-ai
    
    # Replace domain in config
    sudo sed -i "s/yourdomain.com/$DOMAIN/g" /etc/nginx/sites-available/medical-ai
    
    # Enable site
    sudo ln -sf /etc/nginx/sites-available/medical-ai /etc/nginx/sites-enabled/medical-ai
    
    # Disable default site
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Test Nginx configuration
    if sudo nginx -t; then
        echo -e "${GREEN}✓ Nginx configuration valid${NC}"
        sudo systemctl reload nginx
    else
        echo -e "${RED}❌ Nginx configuration error${NC}"
    fi
else
    echo "Skipping Nginx configuration"
fi

# ============================================================================
# Step 8: Setup systemd service
# ============================================================================
echo -e "\n${YELLOW}Step 8: Installing systemd service...${NC}"

echo "Installing medical-ai.service..."
sudo cp "$APP_DIR/medical-ai.service" /etc/systemd/system/

# Customize paths in service file
sudo sed -i "s|/home/medical-ai/app|$APP_DIR|g" /etc/systemd/system/medical-ai.service
sudo sed -i "s|medical-ai:medical-ai|$APP_USER:$APP_GROUP|g" /etc/systemd/system/medical-ai.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable medical-ai.service

echo -e "${GREEN}✓ Systemd service installed${NC}"

# ============================================================================
# Step 9: Setup log rotation
# ============================================================================
echo -e "\n${YELLOW}Step 9: Configuring log rotation...${NC}"

sudo tee /etc/logrotate.d/medical-ai > /dev/null <<EOF
/var/log/medical-ai/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    create 0640 $APP_USER $APP_GROUP
    sharedscripts
    postrotate
        systemctl reload medical-ai > /dev/null 2>&1 || true
    endscript
}
EOF

echo -e "${GREEN}✓ Log rotation configured${NC}"

# ============================================================================
# Step 10: Setup certificate auto-renewal
# ============================================================================
echo -e "\n${YELLOW}Step 10: Setting up certificate auto-renewal...${NC}"

if command -v certbot &> /dev/null; then
    echo "Enabling certbot auto-renewal..."
    sudo systemctl enable certbot.timer
    sudo systemctl start certbot.timer
    echo -e "${GREEN}✓ Certificate auto-renewal enabled${NC}"
fi

# ============================================================================
# Step 11: Start application
# ============================================================================
echo -e "\n${YELLOW}Step 11: Starting application...${NC}"

echo "Starting medical-ai.service..."
sudo systemctl start medical-ai.service
sleep 2

if sudo systemctl is-active --quiet medical-ai.service; then
    echo -e "${GREEN}✓ Application started successfully${NC}"
else
    echo -e "${RED}❌ Failed to start application${NC}"
    echo "Check logs with: sudo journalctl -u medical-ai.service -f"
    exit 1
fi

# ============================================================================
# Step 12: Verify deployment
# ============================================================================
echo -e "\n${YELLOW}Step 12: Verifying deployment...${NC}"

echo "Checking health endpoint..."
if curl -s -k https://localhost/health | grep -q healthy; then
    echo -e "${GREEN}✓ Health check passed${NC}"
else
    echo -e "${YELLOW}⚠️  Health check returned non-healthy status${NC}"
    echo "Check logs with: sudo journalctl -u medical-ai.service -f"
fi

# ============================================================================
# Deployment complete
# ============================================================================
echo -e "\n${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Application URL: https://$DOMAIN"
echo "Health check: https://$DOMAIN/health"
echo ""
echo "Useful commands:"
echo "  Service control:"
echo "    sudo systemctl start|stop|restart|status medical-ai.service"
echo ""
echo "  View logs:"
echo "    sudo journalctl -u medical-ai.service -f"
echo "    sudo tail -f /var/log/nginx/medical-ai_access.log"
echo "    sudo tail -f /var/log/nginx/medical-ai_error.log"
echo ""
echo "  View status:"
echo "    sudo systemctl status medical-ai.service"
echo "    curl https://$DOMAIN/health"
echo ""
echo "IMPORTANT SECURITY REMINDERS:"
echo "  1. Edit .env with real secrets: nano $APP_DIR/.env"
echo "  2. Change database password: mysql -u root -e \"ALTER USER 'medical_user'@'localhost' IDENTIFIED BY 'new_password';\""
echo "  3. Restrict file permissions: sudo chmod 600 $APP_DIR/.env"
echo "  4. Review Nginx logs: sudo tail -f /var/log/nginx/medical-ai_error.log"
echo "  5. Test HTTPS: curl -v https://$DOMAIN/health"
echo ""
echo -e "${YELLOW}Do NOT forget to rotate API keys and database passwords regularly!${NC}"
