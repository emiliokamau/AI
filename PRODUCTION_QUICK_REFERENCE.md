# Medical AI Assistant - Production Quick Reference

## Essential Commands

### Service Management
```bash
# Start service
sudo systemctl start medical-ai.service

# Stop service
sudo systemctl stop medical-ai.service

# Restart service
sudo systemctl restart medical-ai.service

# Check status
sudo systemctl status medical-ai.service

# View logs (real-time)
sudo journalctl -u medical-ai.service -f

# View last 100 log lines
sudo journalctl -u medical-ai.service -n 100
```

### Health Checks
```bash
# Check application health
curl https://yourdomain.com/health

# Check Nginx status
sudo systemctl status nginx

# Check MySQL status
sudo systemctl status mysql

# Check disk space
df -h

# Check memory usage
free -h

# Check running processes
ps aux | grep medical-ai
```

### Log Locations
```
Application logs:        /var/log/medical-ai/
Nginx access logs:       /var/log/nginx/medical-ai_access.log
Nginx error logs:        /var/log/nginx/medical-ai_error.log
Systemd logs:            journalctl -u medical-ai.service
Certbot renewal logs:    /var/log/letsencrypt/letsencrypt.log
```

### Configuration Files
```
Application config:      /home/medical-ai/app/.env
Nginx config:            /etc/nginx/sites-available/medical-ai
Systemd service:         /etc/systemd/system/medical-ai.service
Gunicorn config:         /home/medical-ai/app/gunicorn_config.py
Logrotate config:        /etc/logrotate.d/medical-ai
SSL certificates:        /etc/letsencrypt/live/yourdomain.com/
```

### Database Operations
```bash
# Connect to database
mysql -u medical_user -p -h localhost medical_ai_db

# Backup database
mysqldump -u medical_user -p medical_ai_db > backup.sql

# Restore database
mysql -u medical_user -p medical_ai_db < backup.sql

# Check database size
mysql -u medical_user -p -e "SELECT table_schema, SUM(data_length + index_length) / 1024 / 1024 AS size_mb FROM information_schema.tables GROUP BY table_schema;" medical_ai_db

# View slow queries
mysql -u root -p -e "SHOW FULL PROCESSLIST;" medical_ai_db
```

### SSL Certificate Management
```bash
# Check certificate expiration date
openssl x509 -enddate -noout -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem

# Check certificate validity
openssl x509 -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem -text -noout

# Test certificate renewal
sudo certbot renew --dry-run

# Renew immediately (if needed)
sudo certbot renew --force-renewal

# List all certificates
sudo certbot certificates
```

### Performance & Monitoring
```bash
# Monitor real-time resource usage
watch -n 1 'ps aux | grep [m]edical-ai; free -h; df -h'

# Load test health endpoint
ab -n 1000 -c 100 https://yourdomain.com/health

# Check network connections
netstat -an | grep ESTABLISHED | wc -l

# Monitor Gunicorn worker processes
ps aux | grep gunicorn

# Check file descriptor usage
lsof -p $(pgrep -f medical-ai) | wc -l
```

## Security Checks

### Verify HTTPS Configuration
```bash
# Check that HTTP redirects to HTTPS
curl -I http://yourdomain.com
# Should show: 301 Moved Permanently

# Verify HTTPS is working
curl -I https://yourdomain.com
# Should show: 200 OK

# Verify TLS version
openssl s_client -connect yourdomain.com:443 -tls1_2
```

### Verify Security Headers
```bash
# Check all security headers
curl -I https://yourdomain.com

# Check specific headers
curl -I https://yourdomain.com | grep -i "strict-transport-security"
curl -I https://yourdomain.com | grep -i "x-frame-options"
curl -I https://yourdomain.com | grep -i "x-content-type-options"
curl -I https://yourdomain.com | grep -i "content-security-policy"
```

### Test Debug Mode is Disabled
```bash
# Send invalid request to non-existent endpoint
curl -X POST https://yourdomain.com/invalid-endpoint \
  -H "Content-Type: application/json" \
  -d '{"test":"data"}'

# Should return standard JSON error, NOT Flask debugger HTML
```

### Rate Limiting Test
```bash
# Simulate rapid requests
for i in {1..30}; do
  curl -s -o /dev/null -w "%{http_code}\n" https://yourdomain.com/health
done

# Should see 200 for first requests, then 429 (Too Many Requests)
```

## Troubleshooting

### Application Won't Start
```bash
# Check logs
sudo journalctl -u medical-ai.service -n 50

# Common issues:
# 1. Port already in use: sudo lsof -i :5000
# 2. Database connection failed: check DATABASE_URL in .env
# 3. Missing environment variables: cat /home/medical-ai/app/.env
# 4. Permission denied: sudo chown -R medical-ai:medical-ai /home/medical-ai/app
```

### Database Connection Error
```bash
# Test MySQL connectivity
mysql -u medical_user -p -h localhost -e "SELECT 1"

# Check if MySQL is running
sudo systemctl status mysql

# Check MySQL error log
sudo tail -f /var/log/mysql/error.log

# Verify database exists
mysql -u root -p -e "SHOW DATABASES;"
```

### SSL Certificate Issues
```bash
# Check certificate path
ls -la /etc/letsencrypt/live/yourdomain.com/

# Check certificate is readable
sudo cat /etc/letsencrypt/live/yourdomain.com/fullchain.pem

# Verify certificate and key match
openssl x509 -noout -modulus -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem | md5sum
openssl rsa -noout -modulus -in /etc/letsencrypt/live/yourdomain.com/privkey.pem | md5sum
# Should produce same hash

# Check Nginx has permission to read certificates
sudo -u www-data cat /etc/letsencrypt/live/yourdomain.com/fullchain.pem > /dev/null && echo "OK" || echo "Permission Denied"
```

### High Memory Usage
```bash
# Identify memory-heavy process
ps aux --sort=-%mem | head -n 5

# Check for memory leaks in Gunicorn
ps aux | grep gunicorn
# Note PID and monitor over time

# Restart service to clear memory
sudo systemctl restart medical-ai.service
```

### Disk Space Issues
```bash
# Check disk usage
df -h

# Find large files/directories
du -sh /home/medical-ai/app/*
du -sh /var/log/medical-ai/*

# Clean old logs
find /var/log/medical-ai -name "*.log.*" -mtime +30 -delete

# Check if rotation is working
ls -la /var/log/medical-ai/
ls -la /var/log/nginx/medical-ai*
```

## Deployment Status Indicators

### Green (All Good)
- Service is active and running
- Health endpoint returns {"status": "healthy"}
- SSL certificate valid and not expiring soon
- Low CPU/memory usage
- No errors in logs
- Database responsive

### Yellow (Warning)
- High memory usage but service still responsive
- Some non-critical errors in logs
- Rate limiting being triggered (normal under load)
- SSL certificate expiring within 30 days
- Disk usage above 70%

### Red (Critical - Action Required)
- Service is not running or crashing
- Health endpoint returns {"status": "degraded"}
- Database connection failed
- SSL certificate expired
- Disk usage above 90%
- Out of memory errors
- Port conflicts

## Useful Links

- Let's Encrypt: https://letsencrypt.org/
- Nginx Documentation: https://nginx.org/en/docs/
- Gunicorn Documentation: https://gunicorn.org/
- Flask Documentation: https://flask.palletsprojects.com/
- MySQL Documentation: https://dev.mysql.com/doc/
- SSL Labs Test: https://www.ssllabs.com/ssltest/
- Security Headers Check: https://securityheaders.com/

## Contact & Support

**Critical Issues:**
- Escalate to: [ADMIN EMAIL]
- On-call: [PHONE NUMBER]

**Monitoring/Alerts:**
- Status Page: https://yourdomain.com/health
- Monitoring Dashboard: [URL if applicable]
- Alert Email: [EMAIL]

**Incident Response:**
- Response time: 15 minutes
- Resolution time target: 1 hour
- Communication: [SLACK/EMAIL/etc]

---

**Version:** 1.0  
**Last Updated:** [DATE]  
**Next Review:** [DATE + 3 MONTHS]
