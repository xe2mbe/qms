#!/bin/bash

# Deployment Script for QMS Application
# This script handles the complete setup and configuration of the QMS application

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/var/www/qms"
DB_FILE="$APP_DIR/fmre_reports.db"
VENV_DIR="$APP_DIR/venv"
SERVICE_FILE="/etc/systemd/system/qms.service"
APACHE_CONF="/etc/apache2/sites-available/000-default.conf"

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${YELLOW}This script must be run as root. Please use sudo.${NC}"
    exit 1
fi

echo -e "${GREEN}Starting QMS Deployment...${NC}"

# Update system and install dependencies
echo -e "\n${GREEN}Updating system and installing dependencies...${NC}"
apt-get update
apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    apache2 \
    libapache2-mod-wsgi-py3 \
    sqlite3

# Enable required Apache modules
echo -e "\n${GREEN}Configuring Apache...${NC}"
a2enmod proxy proxy_http proxy_wstunnel rewrite headers
systemctl restart apache2

# Create application directory if it doesn't exist
mkdir -p $APP_DIR

# Set directory permissions
echo -e "\n${GREEN}Setting up directory permissions...${NC}"
chown -R www-data:www-data $APP_DIR
chmod 775 $APP_DIR
chmod g+s $APP_DIR

# Create and activate virtual environment
echo -e "\n${GREEN}Setting up Python virtual environment...${NC}
python3 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

# Install Python dependencies
echo -e "\n${GREEN}Installing Python dependencies...${NC}
pip install --upgrade pip
pip install -r $APP_DIR/requirements.txt

# Set up database
echo -e "\n${GREEN}Setting up database...${NC}
if [ ! -f "$DB_FILE" ]; then
    sqlite3 $DB_FILE ""
    chown www-data:www-data $DB_FILE
    chmod 664 $DB_FILE
    # Initialize database schema here if needed
    # python $APP_DIR/init_db.py
fi

# Configure Apache for QMS
echo -e "\n${GREEN}Configuring Apache virtual host...${NC}"\n
# Backup existing config
cp $APACHE_CONF "${APACHE_CONF}.bak"

# Write new configuration
cat > /tmp/qms_apache.conf << 'EOL'
<VirtualHost *:80>
    ServerAdmin webmaster@localhost
    DocumentRoot /var/www/html
    ServerName 299085.nodes.allstarlink.org

    # Configuración para /fmre (producción)
    ProxyPreserveHost On
    ProxyRequests Off

    RewriteEngine On
    RewriteRule ^/fmre$ /fmre/ [R=301,L]

    ProxyPass /fmre/_stcore/stream ws://127.0.0.1:8501/fmre/_stcore/stream
    ProxyPassReverse /fmre/_stcore/stream ws://127.0.0.1:8501/fmre/_stcore/stream

    ProxyPass /fmre/_stcore/health http://127.0.0.1:8501/fmre/_stcore/health
    ProxyPassReverse /fmre/_stcore/health http://127.0.0.1:8501/fmre/_stcore/health

    ProxyPass /fmre/ http://127.0.0.1:8501/fmre/
    ProxyPassReverse /fmre/ http://127.0.0.1:8501/fmre/

    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/fmre/_stcore/stream$ ws://127.0.0.1:8501/fmre/_stcore/stream [P,L]

    # Configuración para /qms (pruebas)
    RewriteRule ^/qms$ /qms/ [R=301,L]

    ProxyPass /qms/_stcore/stream ws://127.0.0.1:8502/qms/_stcore/stream
    ProxyPassReverse /qms/_stcore/stream ws://127.0.0.1:8502/qms/_stcore/stream

    ProxyPass /qms/_stcore/health http://127.0.0.1:8502/qms/_stcore/health
    ProxyPassReverse /qms/_stcore/health http://127.0.0.1:8502/qms/_stcore/health

    ProxyPass /qms/ http://127.0.0.1:8502/qms/
    ProxyPassReverse /qms/ http://127.0.0.1:8502/qms/

    RewriteCond %{HTTP:Upgrade} =websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/qms/_stcore/stream$ ws://127.0.0.1:8502/qms/_stcore/stream [P,L]

    ErrorLog ${APACHE_LOG_DIR}/error.log
    CustomLog ${APACHE_LOG_DIR}/access.log combined

    LimitRequestBody 52428800
</VirtualHost>
EOL

# Install the new configuration
cp /tmp/qms_apache.conf $APACHE_CONF

# Create systemd service for QMS
echo -e "\n${GREEN}Setting up QMS service...${NC}"
cat > /tmp/qms.service << 'EOL'
[Unit]
Description=QMS Streamlit Application
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/qms
Environment="PATH=/var/www/qms/venv/bin"
ExecStart=/var/www/qms/venv/bin/streamlit run app.py --server.port=8502 --server.address=127.0.0.1 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false --server.baseUrlPath=/qms --server.allowRunOnSave=false
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Install and enable the service
cp /tmp/qms.service $SERVICE_FILE
systemctl daemon-reload
systemctl enable qms.service
systemctl restart qms.service

# Restart Apache to apply changes
echo -e "\n${GREEN}Restarting Apache...${NC}"
systemctl restart apache2

echo -e "\n${GREEN}Deployment completed successfully!${NC}"
echo -e "\nAccess the application at: http://your-server-ip/qms/"
echo -e "Production site: http://your-server-ip/fmre/"
echo -e "\nTo check the service status: systemctl status qms"
echo -e "To view logs: journalctl -u qms -f"

exit 0
