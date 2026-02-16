"""
Gunicorn configuration for production deployment of Medical AI Assistant.

Usage: gunicorn -c gunicorn_config.py app:app
Or set environment variables: WORKERS, WORKER_CLASS, WORKER_TIMEOUT, etc.
"""

import os
import multiprocessing

# ============================================================================
# Server Socket
# ============================================================================
bind = os.environ.get("BIND", "0.0.0.0:5000")
backlog = 2048

# Worker configuration
cpu_count = multiprocessing.cpu_count()
workers = int(os.environ.get("WORKERS", cpu_count * 2 + 1))
worker_class = os.environ.get("WORKER_CLASS", "sync")
worker_connections = 1000
timeout = int(os.environ.get("WORKER_TIMEOUT", 120))
keepalive = 2

# Graceful restart
graceful_timeout = 30
max_requests = int(os.environ.get("MAX_REQUESTS", 1000))
max_requests_jitter = 100

# ============================================================================
# SSL/TLS Configuration
# ============================================================================
if os.environ.get("FLASK_ENV") == "production":
    cert_path = os.environ.get("SSL_CERT_PATH", "/etc/letsencrypt/live/yourdomain.com/fullchain.pem")
    key_path = os.environ.get("SSL_KEY_PATH", "/etc/letsencrypt/live/yourdomain.com/privkey.pem")
    
    # Only enable SSL if certificates exist
    if os.path.exists(cert_path) and os.path.exists(key_path):
        certfile = cert_path
        keyfile = key_path
        
        # Optional CA certificates for client certificate verification
        ca_certs = os.environ.get("SSL_CA_PATH")
        
        # SSL protocol versions (TLS 1.2+ only)
        ssl_version = 17  # PROTOCOL_TLSv1_2
        
        # Cipher suite (high security)
        ciphers = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!eNULL:!EXPORT:!DSS:!DES:!RC4:!3DES:!MD5:!PSK"

# ============================================================================
# Logging Configuration
# ============================================================================
# Log to stdout/stderr for container/systemd logging
accesslog = "-"  # stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
errorlog = "-"   # stderr
loglevel = os.environ.get("LOG_LEVEL", "info")

# Detailed logging
capture_output = True
print_config = False

# Log access
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" '
    'response_time=%(D)sμs'
)

# ============================================================================
# Application Configuration
# ============================================================================
# Proxy headers (set by Nginx/Apache reverse proxy)
forwarded_allow_ips = "*"
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on',
}

# Response headers
response_headers = [
    ('Server', 'Medical-AI/1.0'),
]

# ============================================================================
# Performance Tuning
# ============================================================================
preload_app = False  # Set to True if using shared resources
daemon = False       # Don't daemonize, let systemd/supervisor manage it
threads = 1          # Number of threads per worker (for thread-based worker)
processes = workers

# ============================================================================
# Process Naming
# ============================================================================
proc_name = "medical-ai-assistant"

# ============================================================================
# Health Check
# ============================================================================
# Gunicorn will check if worker can handle requests
check_config = True
