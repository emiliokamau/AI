# Medical AI Assistant - Production Deployment Guide

## Overview
This guide covers deploying the Medical AI Assistant platform securely to production with:
- HTTPS/SSL encryption
- Debug mode disabled
- Production-grade security hardening
- Secrets management

---

## Part 1: SSL/HTTPS Certificate Setup

### Option A: Let's Encrypt (Recommended for Linux/Cloud)
```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx  # Ubuntu/Debian
# or
sudo yum install certbot python3-certbot-nginx      # CentOS/RHEL

# Obtain certificate for your domain
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Certificate location
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem (public key)
# /etc/letsencrypt/live/yourdomain.com/privkey.pem   (private key)

# Auto-renewal (runs twice daily)
sudo certbot renew --quiet
```

### Option B: AWS Certificate Manager (AWS users)
```bash
# Request certificate in AWS ACM console
# Add DNS validation records
# Use with AWS ALB/NLB in front of Flask

# ECS task definition example:
{
  "containerDefinitions": [
    {
      "portMappings": [
        {"containerPort": 5000, "hostPort": 5000, "protocol": "tcp"}
      ]
    }
  ]
}
```

### Option C: Self-Signed Certificate (Development/Testing Only)
```bash
# Generate certificate valid for 365 days
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

# Prompted values:
# Country Name: KE (or your country)
# State/Province: Nairobi (or your region)
# Organization: Your Medical Organization
# Common Name: yourdomain.com (IMPORTANT: must match your domain)
```

---

## Part 2: Python Environment Configuration

### 1. Create .env File (Do NOT commit to git)
```bash
# Production environment variables
export FLASK_ENV=production
export FLASK_DEBUG=0
export SECRET_KEY=your-very-long-secret-key-at-least-32-chars-random
export JWT_SECRET=your-jwt-secret-at-least-32-chars-random
export DATABASE_URL=mysql://user:password@prod-db-host:3306/medical_ai_db
export SENDGRID_API_KEY=SG.your-sendgrid-key
export GEMINI_API_KEY=your-gemini-api-key
export CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
export MEDICAL_HISTORY_KEY=your-fernet-encryption-key
export PORT=5000
export WORKERS=4
export WORKER_CLASS=sync
export WORKER_TIMEOUT=120
export MAX_REQUESTS=1000
export BIND=0.0.0.0:5000
export LOG_LEVEL=info
```

### 2. Add to `.gitignore`
```
.env
.env.local
.env.prod
*.pem
*.key
*.crt
*.pfx
__pycache__/
*.pyc
venv/
env/
.DS_Store
logs/
*.log
```

---

## Part 3: Update Flask Application (app.py)

Replace the Flask startup code:

**OLD CODE:**
```python
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    start_medication_reminder_worker()
    app.run(host="0.0.0.0", port=port, debug=True)
```

**NEW CODE:**
```python
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    start_medication_reminder_worker()
    
    # Production HTTPS configuration
    ssl_context = None
    if os.environ.get("FLASK_ENV") == "production":
        cert_path = os.environ.get("SSL_CERT_PATH", "/etc/letsencrypt/live/yourdomain.com/fullchain.pem")
        key_path = os.environ.get("SSL_KEY_PATH", "/etc/letsencrypt/live/yourdomain.com/privkey.pem")
        
        if os.path.exists(cert_path) and os.path.exists(key_path):
            ssl_context = (cert_path, key_path)
            print("[SECURITY] Running with HTTPS")
        else:
            print("[WARNING] HTTPS certificate files not found. Running without HTTPS.")
    
    # Production: disable debug mode, use production WSGI server instead
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    app.run(
        host=os.environ.get("BIND_HOST", "0.0.0.0"),
        port=port,
        debug=debug_mode,
        ssl_context=ssl_context,
        use_reloader=False  # Disable Werkzeug reloader in production
    )
```

---

## Part 4: Production WSGI Server Setup

**DO NOT use Flask's development server in production.** Use Gunicorn, uWSGI, or Waitress instead.

### Option A: Gunicorn (Recommended)

#### Installation
```bash
pip install gunicorn
```

#### Create `gunicorn_config.py`
```python
import os
import multiprocessing

# Server socket
bind = os.environ.get("BIND", "0.0.0.0:5000")
backlog = 2048
workers = int(os.environ.get("WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = os.environ.get("WORKER_CLASS", "sync")
worker_connections = 1000
timeout = int(os.environ.get("WORKER_TIMEOUT", 120))
keepalive = 2
max_requests = int(os.environ.get("MAX_REQUESTS", 1000))
max_requests_jitter = 100

# SSL/TLS
if os.environ.get("FLASK_ENV") == "production":
    certfile = os.environ.get("SSL_CERT_PATH", "/etc/letsencrypt/live/yourdomain.com/fullchain.pem")
    keyfile = os.environ.get("SSL_KEY_PATH", "/etc/letsencrypt/live/yourdomain.com/privkey.pem")
    if os.path.exists(certfile) and os.path.exists(keyfile):
        ca_certs = os.environ.get("SSL_CA_PATH")

# Logging
accesslog = "-"  # Log to stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
errorlog = "-"  # Log to stderr
loglevel = os.environ.get("LOG_LEVEL", "info")
capture_output = True
print_config = False

# Application
forwarded_allow_ips = "*"  # If behind reverse proxy
secure_scheme_headers = {
    'X-FORWARDED_PROTOCOL': 'ssl',
    'X-FORWARDED_PROTO': 'https',
    'X-FORWARDED_SSL': 'on',
}
```

#### Run Gunicorn
```bash
# Load environment from .env
source .env

# Start with 4 workers, HTTPS enabled
gunicorn -c gunicorn_config.py app:app

# Or with explicit parameters
gunicorn \
  --workers 4 \
  --worker-class sync \
  --bind 0.0.0.0:5000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  app:app
```

### Option B: Waitress (Windows-friendly)
```bash
pip install waitress

# Run with HTTPS
waitress-serve \
  --host=0.0.0.0 \
  --port=5000 \
  --threads=4 \
  app:app
```

---

## Part 5: Production Security Hardening

### 1. Add HSTS Header (HTTP Strict Transport Security)
Update `app.py` after_request section:

```python
@app.after_request
def set_security_headers(response):
    # Force HTTPS for 1 year (recommended: 31536000 seconds)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    
    # Control referrer information
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Restrict browser APIs
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), payment=()'
    
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' https://maps.googleapis.com; "
        "frame-ancestors 'none';"
    )
    
    return response
```

### 2. CORS Hardening
```python
# OLD: CORS(app)  # Allows all origins - INSECURE

# NEW: Restrict to specific domains
from flask_cors import CORS

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5000").split(",")
CORS(
    app,
    origins=cors_origins,
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    supports_credentials=True,
    max_age=3600  # Cache preflight for 1 hour
)
```

### 3. Session Security
```python
# In Flask app configuration
app.config['SESSION_COOKIE_SECURE'] = os.environ.get("FLASK_ENV") == "production"
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
```

### 4. Rate Limiting
```bash
pip install Flask-Limiter
```

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # Use Redis for distributed: redis://localhost:6379
)

# Apply to sensitive endpoints
@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  # Max 5 login attempts per minute
def login():
    ...

@app.route('/chat', methods=['POST'])
@limiter.limit("20 per minute")  # Max 20 chat requests per minute
def chat():
    ...
```

### 5. Database Connection Pooling
```python
# Install
pip install SQLAlchemy

# In db.py
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    os.environ.get("DATABASE_URL"),
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True  # Test connection before using
)
```

---

## Part 6: Reverse Proxy Setup

### Nginx Configuration
```nginx
upstream medical_ai {
    server 127.0.0.1:5000;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # SSL security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Client upload size limit
    client_max_body_size 5M;
    
    # Proxy to Flask
    location / {
        proxy_pass http://medical_ai;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 60s;
    }
}
```

### Apache Configuration
```apache
# Enable modules
a2enmod ssl
a2enmod proxy
a2enmod proxy_http
a2enmod rewrite
a2enmod headers

# Virtual host
<VirtualHost *:443>
    ServerName yourdomain.com
    ServerAlias www.yourdomain.com
    
    # SSL
    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/yourdomain.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/yourdomain.com/privkey.pem
    
    # Security headers
    Header set Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    Header set X-Frame-Options "DENY"
    Header set X-Content-Type-Options "nosniff"
    
    # Proxy
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:5000/
    ProxyPassReverse / http://127.0.0.1:5000/
</VirtualHost>

# Redirect HTTP to HTTPS
<VirtualHost *:80>
    ServerName yourdomain.com
    ServerAlias www.yourdomain.com
    RewriteEngine On
    RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
</VirtualHost>
```

---

## Part 7: Secrets Management

### Option A: Environment Variables with Vault
```bash
# Install Vault
# https://www.vaultproject.io/downloads.html

# Store secret
vault write secret/medical_ai/prod \
  JWT_SECRET="your-secret" \
  DATABASE_PASSWORD="your-db-pass" \
  GEMINI_API_KEY="your-api-key"

# Retrieve in Python
import hvac

client = hvac.Client(url='https://vault.yourdomain.com', token='your-token')
secrets = client.secrets.kv.v1.read_secret_version(path='medical_ai/prod')
for key, value in secrets['data']['data'].items():
    os.environ[key] = value
```

### Option B: AWS Secrets Manager
```python
import boto3
import json

def load_secrets():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    
    try:
        response = client.get_secret_value(SecretId='medical-ai/prod')
        secret = json.loads(response['SecretString'])
        
        for key, value in secret.items():
            os.environ[key] = value
    except Exception as e:
        print(f"Error loading secrets: {e}")

# Call at app startup
load_secrets()
```

### Option C: Azure Key Vault
```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

def load_secrets():
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url="https://yourvault.vault.azure.us/", credential=credential)
    
    os.environ['JWT_SECRET'] = client.get_secret("jwt-secret").value
    os.environ['DATABASE_URL'] = client.get_secret("database-url").value
    # ... load other secrets
```

---

## Part 8: Deployment Checklist

- [ ] SSL certificate obtained and installed
- [ ] `.env` file created with production secrets (NOT in git)
- [ ] `app.py` updated with HTTPS and debug=False
- [ ] Gunicorn/uWSGI/Waitress installed and configured
- [ ] Nginx/Apache reverse proxy configured with SSL
- [ ] CORS origins restricted to production domain only
- [ ] Database connection pooling implemented
- [ ] Rate limiting configured
- [ ] HSTS header added
- [ ] Security headers verified (use https://securityheaders.com/)
- [ ] Log aggregation set up (ELK stack, CloudWatch, Datadog)
- [ ] Database backups automated daily
- [ ] Monitoring/alerting configured (CPU, memory, disk, error rates)
- [ ] Secrets stored in vault (not in .env file on server)
- [ ] API keys rotated
- [ ] Database encryption enabled
- [ ] Audit logging verified
- [ ] Load testing completed
- [ ] DDoS protection configured (CloudFlare, AWS Shield)

---

## Part 9: Testing Production Setup

### Test HTTPS
```bash
# Verify SSL certificate
openssl s_client -connect yourdomain.com:443

# Check SSL strength
curl -I https://yourdomain.com

# Verify headers are present
curl -I https://yourdomain.com | grep -i "Strict-Transport-Security"
```

### Test Debug Mode is Disabled
```bash
# Should NOT see Flask's interactive debugger
curl -X POST https://yourdomain.com/invalid-endpoint

# Should return standard 404, not debugger
```

### Load Testing
```bash
# Install Apache Bench or similar
ab -n 1000 -c 10 https://yourdomain.com/

# Use Locust for complex scenarios
pip install locust
locust -f locustfile.py --host=https://yourdomain.com
```

---

## Part 10: Monitoring & Maintenance

### Log Rotation
```bash
# Create /etc/logrotate.d/medical-ai
/var/log/medical-ai/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload gunicorn-medical-ai > /dev/null 2>&1 || true
    endscript
}
```

### Automated Certificate Renewal
```bash
# Add to crontab for automatic renewal
0 3 * * * certbot renew --quiet --post-hook "systemctl reload nginx"
```

### Health Check Endpoint
```python
@app.route('/health', methods=['GET'])
def health_check():
    """Production health check endpoint"""
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT 1")
        db_ok = True
    except:
        db_ok = False
    
    status = 'healthy' if db_ok else 'degraded'
    return jsonify({
        'status': status,
        'database': db_ok,
        'timestamp': datetime.utcnow().isoformat()
    }), 200 if db_ok else 503
```

---

## Summary of Changes

| Component | Development | Production |
|-----------|-------------|-----------|
| **Server** | Flask dev server (debug=True) | Gunicorn/uWSGI (debug=False) |
| **Protocol** | HTTP (localhost:5000) | HTTPS (port 443) |
| **Reloader** | Enabled (hot reload) | Disabled |
| **Logging** | DEBUG level, console | INFO/WARNING level, files |
| **CORS** | `*` (all origins) | Specific domains only |
| **Secrets** | .env file | Vault/Secrets Manager |
| **Reverse Proxy** | None | Nginx/Apache |
| **SSL Context** | None | Full chain + key |
| **Connection Pool** | Direct connections | Pooled (10-20 connections) |
| **Rate Limiting** | None | 20-50 req/min per endpoint |
| **Certificates** | N/A | Let's Encrypt or ACM |
| **HSTS Header** | No | Yes (31536000 max-age) |

---

## Troubleshooting

### Certificate Issues
```bash
# Check certificate validity
openssl x509 -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem -text -noout

# Verify certificate matches key
openssl x509 -noout -modulus -in cert.pem | md5sum
openssl rsa -noout -modulus -in key.pem | md5sum
# Should produce same hash
```

### Port 443 Already in Use
```bash
# Find process using port 443
sudo lsof -i :443

# Kill the process
sudo kill -9 <PID>
```

### Gunicorn Connection Issues
```bash
# Check if Gunicorn is running
ps aux | grep gunicorn

# Check logs
tail -f gunicorn-access.log
tail -f gunicorn-error.log

# Test connection
curl -v https://localhost:5000
```

---

**Security Critical:** Never commit `.env` files, certificate keys, or secrets to version control. Use a secrets vault for production.
