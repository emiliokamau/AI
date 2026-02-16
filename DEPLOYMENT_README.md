# Production Deployment Files - README

This directory contains complete production deployment configuration and documentation for the Medical AI Assistant platform.

## 📋 Quick Start

1. **Read First**: [DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md) - Overview of what's been completed
2. **Detailed Guide**: [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) - Step-by-step deployment instructions
3. **Checklist**: [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) - Verification checklist for each step
4. **Quick Commands**: [PRODUCTION_QUICK_REFERENCE.md](PRODUCTION_QUICK_REFERENCE.md) - Handy command reference

## 📁 Files Overview

### Configuration Files

| File | Purpose | Action |
|------|---------|--------|
| `.env.template` | Environment variables template | Copy to `.env` and fill with real values |
| `gunicorn_config.py` | Gunicorn WSGI server config | Copy to `/home/medical-ai/app/` |
| `medical-ai.service` | Systemd service file | Copy to `/etc/systemd/system/` |
| `medical-ai-nginx.conf` | Nginx reverse proxy config | Copy to `/etc/nginx/sites-available/` |

### Documentation Files

| File | Purpose | Audience |
|------|---------|----------|
| `DEPLOYMENT_SUMMARY.md` | High-level overview | Everyone |
| `PRODUCTION_DEPLOYMENT.md` | Comprehensive guide (92 KB) | DevOps/SysAdmin |
| `DEPLOYMENT_CHECKLIST.md` | Step-by-step checklist | DevOps/QA |
| `PRODUCTION_QUICK_REFERENCE.md` | Command reference | Operations/Support |

### Scripts

| File | Purpose | Usage |
|------|---------|-------|
| `deploy.sh` | Automated deployment | `chmod +x deploy.sh && sudo ./deploy.sh` |

### Application Files (Updated)

| File | Changes | Notes |
|------|---------|-------|
| `app.py` | Debug mode disabled, HTTPS/SSL support, security headers | Production-ready |
| `.gitignore` | Add `.env` files | Prevents secret commits |

## 🚀 Deployment Process

### For First-Time Deployment

```bash
# Step 1: Prepare configuration
cp .env.template .env
nano .env  # Edit with real secrets

# Step 2: Review deployment guide
cat PRODUCTION_DEPLOYMENT.md | less

# Step 3: Follow checklist
cat DEPLOYMENT_CHECKLIST.md

# Step 4: Run automated deployment (on target server)
chmod +x deploy.sh
sudo ./deploy.sh

# Step 5: Verify deployment
curl https://yourdomain.com/health
```

### For Updates/Redeployment

```bash
# 1. Backup current deployment
sudo systemctl stop medical-ai.service
cp -r /home/medical-ai/app /home/medical-ai/app.backup.$(date +%Y%m%d)

# 2. Update application files
cp app.py /home/medical-ai/app/
cp db.py /home/medical-ai/app/
# ... etc

# 3. Restart service
sudo systemctl start medical-ai.service

# 4. Verify
curl https://yourdomain.com/health
```

## 🔐 Security Checklist Before Deployment

**CRITICAL - Must Complete:**
- [ ] `.env` file has REAL secrets (not templates)
- [ ] `.env` is NOT in git (added to `.gitignore`)
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] Database user is NOT root
- [ ] Database password is strong (20+ chars)
- [ ] SSL certificate obtained and paths verified
- [ ] API keys rotated (not old/expired)
- [ ] JWT_SECRET is random (32+ chars)

**HIGHLY RECOMMENDED:**
- [ ] Firewall configured (port 80, 443 open; others closed)
- [ ] SSH key-based auth only (no passwords)
- [ ] Monitoring/alerting configured
- [ ] Database backups automated
- [ ] DDoS protection enabled (CloudFlare/AWS Shield)

## 📊 Configuration Summary

### Network
- **HTTP Port**: 80 (redirects to HTTPS)
- **HTTPS Port**: 443 (main application)
- **Application Server**: Gunicorn on localhost:5000
- **Reverse Proxy**: Nginx on port 443 (with SSL)

### Application
- **Framework**: Flask 3.x
- **WSGI Server**: Gunicorn (4 workers recommended)
- **Workers**: CPU cores × 2 + 1
- **Timeout**: 120 seconds
- **Max Requests**: 1000 per worker

### Security
- **TLS Version**: 1.2+ only
- **HSTS**: 1 year max-age
- **Rate Limiting**: 20 req/s (general), 5 req/min (login)
- **CORS**: Restricted to specific domains
- **CSP**: Restrictive with script/style/img/font controls

### Monitoring
- **Health Check**: `/health` endpoint
- **Logs**: `/var/log/medical-ai/` (rotated daily, 30-day retention)
- **Nginx Logs**: `/var/log/nginx/medical-ai_*.log`
- **Systemd Logs**: `journalctl -u medical-ai.service`

## 🛠️ Common Tasks

### Start/Stop Service
```bash
sudo systemctl start medical-ai.service
sudo systemctl stop medical-ai.service
sudo systemctl restart medical-ai.service
sudo systemctl status medical-ai.service
```

### View Logs
```bash
# Real-time application logs
sudo journalctl -u medical-ai.service -f

# Last 100 lines
sudo journalctl -u medical-ai.service -n 100

# Nginx access logs
sudo tail -f /var/log/nginx/medical-ai_access.log

# Nginx error logs
sudo tail -f /var/log/nginx/medical-ai_error.log
```

### Health Check
```bash
curl https://yourdomain.com/health
# Expected: {"status": "healthy", "database": "connected", ...}
```

### Database Backup
```bash
mysqldump -u medical_user -p medical_ai_db > backup.sql
```

### Certificate Status
```bash
openssl x509 -enddate -noout -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem
sudo certbot certificates
```

## ⚠️ Common Issues & Solutions

### Service Won't Start
**Problem**: `sudo systemctl start medical-ai.service` fails
**Solution**:
1. Check logs: `sudo journalctl -u medical-ai.service -n 50`
2. Verify .env file has real values: `cat /home/medical-ai/app/.env`
3. Test database connection: `mysql -u medical_user -p -h localhost medical_ai_db -e "SELECT 1"`
4. Check port 5000 not in use: `sudo lsof -i :5000`

### Database Connection Error
**Problem**: Application can't connect to MySQL
**Solution**:
1. Verify MySQL is running: `sudo systemctl status mysql`
2. Test connection: `mysql -u medical_user -p -h localhost medical_ai_db -e "SELECT 1"`
3. Check DATABASE_URL in `.env` is correct
4. Verify database exists: `mysql -u root -p -e "SHOW DATABASES"`

### SSL Certificate Error
**Problem**: Nginx gives certificate error
**Solution**:
1. Check certificate exists: `ls -la /etc/letsencrypt/live/yourdomain.com/`
2. Verify certificate validity: `openssl x509 -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem -text -noout`
3. Check Nginx has permission: `sudo -u www-data cat /etc/letsencrypt/live/yourdomain.com/fullchain.pem > /dev/null && echo OK || echo Permission Denied`
4. Test renewal: `sudo certbot renew --dry-run`

### High Memory Usage
**Problem**: Application consuming lots of memory
**Solution**:
1. Check memory usage: `ps aux --sort=-%mem | grep medical-ai`
2. Restart service: `sudo systemctl restart medical-ai.service`
3. Check for memory leaks in logs: `sudo journalctl -u medical-ai.service | grep -i memory`
4. Reduce workers if needed: Edit `gunicorn_config.py`, set `workers=2`

### Disk Space Low
**Problem**: Disk usage above 80%
**Solution**:
1. Check usage: `df -h`
2. Find large files: `du -sh /home/medical-ai/app/*`
3. Clean old logs: `find /var/log/medical-ai -name "*.log.*" -mtime +30 -delete`
4. Check if rotation is working: `ls -la /var/log/medical-ai/`

## 📞 Getting Help

**For specific commands:** See [PRODUCTION_QUICK_REFERENCE.md](PRODUCTION_QUICK_REFERENCE.md)

**For step-by-step deployment:** See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)

**For verification:** See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)

**For troubleshooting:** See "Troubleshooting" section in [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md#troubleshooting)

## 🔄 Maintenance Schedule

| Frequency | Task |
|-----------|------|
| Daily | Check health endpoint, review error logs |
| Weekly | Review security logs, verify backups, check certificate expiration |
| Monthly | Rotate API keys, update dependencies, test backup restore |
| Quarterly | Security audit, load testing, penetration testing |
| Annually | Full security assessment, disaster recovery drill |

## 📝 Documentation Structure

```
Medical AI Assistant Production Deployment
├── DEPLOYMENT_SUMMARY.md (Start here!)
│   └── Overview of what's been done
│
├── PRODUCTION_DEPLOYMENT.md (Comprehensive guide)
│   ├── SSL/TLS setup
│   ├── Flask configuration
│   ├── WSGI server setup
│   ├── Reverse proxy configuration
│   ├── Secrets management
│   └── Troubleshooting
│
├── DEPLOYMENT_CHECKLIST.md (Step verification)
│   ├── Pre-deployment checks
│   ├── Deployment steps
│   ├── Post-deployment verification
│   ├── Security hardening
│   └── Maintenance schedule
│
└── PRODUCTION_QUICK_REFERENCE.md (Quick lookup)
    ├── Essential commands
    ├── Log locations
    ├── Security checks
    ├── Troubleshooting
    └── Status indicators
```

## 🎯 Success Criteria

Your deployment is **successful** when:

✅ Application starts without errors: `sudo systemctl status medical-ai.service`
✅ Health endpoint responds: `curl https://yourdomain.com/health` → `{"status": "healthy"}`
✅ HTTPS is enforced: `curl http://yourdomain.com` → redirects to HTTPS
✅ Security headers present: `curl -I https://yourdomain.com | grep Strict-Transport-Security`
✅ No debug mode errors: Invalid endpoints return JSON, not HTML debugger
✅ Database is accessible: Application loads data correctly
✅ Logs are rotating: Files in `/var/log/medical-ai/` and `/var/log/nginx/`
✅ Service auto-restarts: Kill process, verify it restarts automatically

## ✨ Next Steps

1. **Read** [DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md) for overview
2. **Plan** using [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
3. **Follow** [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) step-by-step
4. **Reference** [PRODUCTION_QUICK_REFERENCE.md](PRODUCTION_QUICK_REFERENCE.md) for commands
5. **Deploy** using `deploy.sh` or manual steps
6. **Monitor** using health checks and logs

---

**Status**: ✅ Production Ready
**Last Updated**: Today
**Version**: 1.0
