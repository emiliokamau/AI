# Production Deployment Checklist - Medical AI Assistant

## Pre-Deployment Verification

### Code Quality & Security
- [ ] All files pass syntax validation (no errors reported)
- [ ] Debug mode hardcoded as disabled in app.py
- [ ] SSL/HTTPS support implemented in app.py
- [ ] CORS restricted to specific domains (not wildcard)
- [ ] Security headers added (HSTS, CSP, X-Frame-Options, etc.)
- [ ] Sensitive data not logged (API keys masked in output)
- [ ] File upload validation enforced (size + type checks)
- [ ] Health check endpoint `/health` available
- [ ] No hardcoded credentials in source code

### Environment Configuration
- [ ] `.env.template` created with all required variables
- [ ] `.env` file created from template with REAL secrets
- [ ] `.env` added to `.gitignore`
- [ ] All environment variables documented
- [ ] Database credentials secure (strong password, not root)
- [ ] API keys rotated and non-expired
- [ ] JWT_SECRET is cryptographically random (32+ chars)
- [ ] Encryption keys stored securely (not in code)

### SSL/TLS Certificates
- [ ] SSL certificate obtained (Let's Encrypt or commercial)
- [ ] Certificate path configured: `/etc/letsencrypt/live/yourdomain.com/fullchain.pem`
- [ ] Private key path configured: `/etc/letsencrypt/live/yourdomain.com/privkey.pem`
- [ ] Certificate is valid and not self-signed (for production)
- [ ] Certificate expiration monitored (alerts set for 30 days before)
- [ ] Auto-renewal configured (certbot renew cron job)
- [ ] Wildcard certificate obtained (if needed for subdomains)
- [ ] TLS 1.2+ enforced (no TLS 1.0 or 1.1)

### Database
- [ ] MySQL/MariaDB running and accessible
- [ ] Database created: `medical_ai_db`
- [ ] Database user created: `medical_user` (not root)
- [ ] User has appropriate privileges (not GRANT ALL)
- [ ] Database password is strong (20+ chars, mixed case, numbers, symbols)
- [ ] Database backups automated (daily)
- [ ] Backup storage is encrypted
- [ ] Database connection pooling configured
- [ ] Slow query logging enabled
- [ ] Audit logging enabled for sensitive operations

### Reverse Proxy (Nginx)
- [ ] Nginx installed and running
- [ ] Configuration file copied to `/etc/nginx/sites-available/medical-ai`
- [ ] Domain names replaced (yourdomain.com → real domain)
- [ ] SSL certificate paths updated
- [ ] DH parameters generated: `/etc/ssl/certs/dhparam.pem`
- [ ] Rate limiting zones configured
- [ ] Security headers configured
- [ ] Nginx configuration tested: `sudo nginx -t`
- [ ] Nginx reloaded: `sudo systemctl reload nginx`
- [ ] HTTP → HTTPS redirect working
- [ ] Static file caching configured

### WSGI Application Server (Gunicorn)
- [ ] Gunicorn installed in virtual environment
- [ ] `gunicorn_config.py` created and configured
- [ ] Worker count set appropriately (CPU cores * 2 + 1)
- [ ] Worker timeout set to 120 seconds
- [ ] Max requests set to 1000
- [ ] SSL context enabled in config
- [ ] Logging configured (access and error logs)
- [ ] Process name set to `medical-ai-assistant`

### Systemd Service
- [ ] `medical-ai.service` file created in `/etc/systemd/system/`
- [ ] Application user created: `medical-ai`
- [ ] Working directory set correctly
- [ ] Environment file path correct
- [ ] Restart policy set to `always`
- [ ] Resource limits configured
- [ ] Service enabled: `sudo systemctl enable medical-ai.service`
- [ ] Service starts successfully: `sudo systemctl start medical-ai.service`
- [ ] Service is active: `sudo systemctl is-active medical-ai.service`

### Logging & Monitoring
- [ ] Log directories created and permissions set
- [ ] Log rotation configured: `/etc/logrotate.d/medical-ai`
- [ ] Application logs location: `/var/log/medical-ai/`
- [ ] Nginx logs location: `/var/log/nginx/medical-ai_*.log`
- [ ] Systemd logs accessible: `sudo journalctl -u medical-ai.service`
- [ ] Log retention set (e.g., 30 days)
- [ ] Log aggregation service configured (optional: ELK, CloudWatch, Datadog)
- [ ] Error alerting configured
- [ ] Performance metrics monitored
- [ ] Health check endpoint monitored externally

### Application Startup
- [ ] Virtual environment created: `/path/to/venv`
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Gunicorn installed: `pip install gunicorn`
- [ ] Medication reminder worker starts successfully
- [ ] No error messages on startup
- [ ] Application listens on configured port (5000)

## Deployment Steps

### 1. Pre-Flight Checks
```bash
# Verify Python version
python3 --version  # Should be 3.9+

# Verify MySQL connectivity
mysql -u medical_user -p medical_ai_db -e "SELECT 1"

# Test DNS resolution
nslookup yourdomain.com
```

### 2. Copy Application Files
```bash
sudo mkdir -p /home/medical-ai/app
sudo cp -r /path/to/app/* /home/medical-ai/app/
sudo chown -R medical-ai:medical-ai /home/medical-ai/app
sudo chmod 755 /home/medical-ai/app
```

### 3. Create Virtual Environment
```bash
cd /home/medical-ai/app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

### 4. Configure Environment
```bash
cp .env.template .env
nano .env  # Edit with real secrets
chmod 600 .env
```

### 5. Initialize Database
```bash
source venv/bin/activate
python3 db.py  # Creates tables
```

### 6. Obtain SSL Certificate
```bash
sudo certbot certonly --webroot -w /var/www/certbot -d yourdomain.com
```

### 7. Configure Reverse Proxy
```bash
sudo cp medical-ai-nginx.conf /etc/nginx/sites-available/medical-ai
sudo sed -i 's/yourdomain.com/your.real.domain/g' /etc/nginx/sites-available/medical-ai
sudo ln -s /etc/nginx/sites-available/medical-ai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 8. Setup Gunicorn Service
```bash
sudo cp medical-ai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable medical-ai.service
sudo systemctl start medical-ai.service
```

### 9. Verify Service Status
```bash
sudo systemctl status medical-ai.service
curl https://yourdomain.com/health
```

### 10. Setup Certificate Auto-Renewal
```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
sudo certbot renew --dry-run  # Test renewal
```

## Post-Deployment Verification

### Health Checks
```bash
# 1. Check service is running
sudo systemctl status medical-ai.service

# 2. Check health endpoint
curl https://yourdomain.com/health
# Expected response: {"status": "healthy", "database": "connected", ...}

# 3. Check HTTPS connectivity
openssl s_client -connect yourdomain.com:443 -brief
# Should show: SSL-Session established

# 4. Test login endpoint
curl -X POST https://yourdomain.com/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}'

# 5. Monitor logs
sudo journalctl -u medical-ai.service -f
tail -f /var/log/nginx/medical-ai_access.log
tail -f /var/log/nginx/medical-ai_error.log
```

### Security Verification
```bash
# 1. Verify HSTS header
curl -I https://yourdomain.com | grep Strict-Transport-Security
# Expected: max-age=31536000; includeSubDomains; preload

# 2. Verify CSP header
curl -I https://yourdomain.com | grep Content-Security-Policy

# 3. Verify X-Frame-Options
curl -I https://yourdomain.com | grep X-Frame-Options
# Expected: DENY

# 4. Test SSL strength
openssl s_client -connect yourdomain.com:443 -tls1_2
# Should succeed with TLS 1.2 or 1.3

# 5. Check for weak ciphers
nmap --script ssl-enum-ciphers -p 443 yourdomain.com

# 6. Verify debug mode is disabled
curl https://yourdomain.com/invalid-endpoint
# Should return standard JSON error, not Flask debugger
```

### Performance Testing
```bash
# 1. Load testing (100 concurrent users, 1000 requests)
ab -n 1000 -c 100 https://yourdomain.com/health

# 2. Monitor server resources during load test
watch -n 1 'ps aux | grep medical-ai'
top -p $(pgrep -f medical-ai | tr '\n' ',')

# 3. Check for memory leaks (run periodically)
free -h
ps aux | grep gunicorn
```

## Security Hardening Verification

### Network Security
- [ ] Firewall rules configured
  - [ ] Port 80 open (HTTP redirect)
  - [ ] Port 443 open (HTTPS)
  - [ ] Port 22 open (SSH, from specific IPs only)
  - [ ] Port 3306 closed (MySQL not exposed)
  - [ ] Other unnecessary ports closed
- [ ] Rate limiting tested (20 req/s general, 5 req/min login)
- [ ] DDoS protection enabled (CloudFlare, AWS Shield)
- [ ] WAF rules configured if behind AWS/CloudFlare

### Application Security
- [ ] No sensitive data in logs
- [ ] File uploads validated (size, type, content)
- [ ] SQL injection prevention working
- [ ] XSS protection enabled (CSP headers)
- [ ] CSRF protection if applicable
- [ ] API key rotation mechanism in place
- [ ] Audit logging capturing sensitive operations
- [ ] Database encryption enabled (if supported)

### Access Control
- [ ] Application user (medical-ai) has minimal privileges
- [ ] File permissions: 644 (files), 755 (directories)
- [ ] Config files: 600 (readable by owner only)
- [ ] SSH key-based authentication only (no passwords)
- [ ] Root account disabled for application
- [ ] Service account has no shell access

### Backup & Recovery
- [ ] Database backups automated and tested
- [ ] Backups encrypted and offsite
- [ ] Recovery time objective (RTO) documented
- [ ] Recovery point objective (RPO) documented
- [ ] Restore procedure documented and tested
- [ ] Application code backups in version control
- [ ] Disaster recovery plan documented

## Ongoing Maintenance

### Daily Tasks
- [ ] Check application health endpoint
- [ ] Review error logs for issues
- [ ] Monitor disk space usage

### Weekly Tasks
- [ ] Review security logs/audit logs
- [ ] Check database backup completeness
- [ ] Verify certificate expiration
- [ ] Monitor performance metrics

### Monthly Tasks
- [ ] Rotate API keys and credentials
- [ ] Update dependencies (security patches)
- [ ] Test backup restoration
- [ ] Review and update security policies

### Quarterly Tasks
- [ ] Security audit of code changes
- [ ] Load testing and performance tuning
- [ ] Update OS and system packages
- [ ] Review and update incident response plan

### Annually Tasks
- [ ] Full security assessment
- [ ] Penetration testing
- [ ] Disaster recovery drill
- [ ] License and compliance review

## Emergency Procedures

### Application Crash
```bash
# Check if service is running
sudo systemctl status medical-ai.service

# Restart application
sudo systemctl restart medical-ai.service

# Check logs for error
sudo journalctl -u medical-ai.service -n 100

# If service won't start, check:
# 1. Database connectivity
# 2. Environment variables
# 3. File permissions
# 4. Port availability
```

### Database Issues
```bash
# Check MySQL status
sudo systemctl status mysql

# Test connection
mysql -u medical_user -p -h localhost medical_ai_db -e "SELECT 1"

# Check disk space
df -h

# View slow queries
mysql -u root -p -e "SHOW FULL PROCESSLIST" medical_ai_db
```

### SSL Certificate Expiration
```bash
# Check certificate expiration
openssl x509 -enddate -noout -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem

# Renew manually if auto-renewal failed
sudo certbot renew --force-renewal

# Check renewal logs
sudo cat /var/log/letsencrypt/letsencrypt.log
```

### High Load/DoS Attack
```bash
# Check connections
netstat -an | grep ESTABLISHED | wc -l

# Kill excessive connections
pkill -f "medical-ai"

# Temporarily enable stricter rate limiting in Nginx
sudo vim /etc/nginx/sites-available/medical-ai
# Reduce rate limits: rate=5r/s; (instead of 20r/s;)
sudo systemctl reload nginx

# Activate CloudFlare/AWS WAF rules
```

## Rollback Procedure

If deployment causes critical issues:

```bash
# 1. Stop current service
sudo systemctl stop medical-ai.service

# 2. Restore previous version from git
cd /home/medical-ai/app
git checkout previous-version-tag

# 3. Reinstall dependencies (if changed)
source venv/bin/activate
pip install -r requirements.txt

# 4. Restart service
sudo systemctl start medical-ai.service

# 5. Verify health
curl https://yourdomain.com/health
```

## Documentation

- [ ] Deployment process documented
- [ ] Runbook for common issues created
- [ ] Architecture diagram updated
- [ ] API documentation up to date
- [ ] Database schema documented
- [ ] Environment variables documented
- [ ] Incident response procedures documented
- [ ] Change log maintained

---

**Last Updated:** [DATE]  
**Deployed By:** [YOUR NAME]  
**Version:** [APP VERSION]  
**Environment:** Production  
**Domain:** yourdomain.com

