# USSD Configuration Setup Guide

## Quick Start for USSD Integration

### Step 1: Choose Your USSD Provider

#### Option A: Africa's Talking (Recommended for Africa)
```bash
# Install Africa's Talking SDK
pip install africastalking

# Register account at: https://africastalking.com
# Get API key from dashboard

# Set environment variables
export AFRICASTALKING_API_KEY="your_api_key"
export AFRICASTALKING_USERNAME="your_username"
export USSD_SHORTCODE="*384#"
export USSD_PROVIDER="africastalking"
```

#### Option B: Twilio USSD (Global Coverage)
```bash
# Already installed - Twilio supports USSD in 100+ countries
# Set environment variables
export TWILIO_USSD_ENABLED="true"
export USSD_SHORTCODE="*384#"
export USSD_PROVIDER="twilio"
```

---

### Step 2: Install Python Dependencies

```bash
pip install -r requirements-ussd.txt
```

**requirements-ussd.txt**:
```
flask-cors>=4.0.0
africastalking>=1.2.4  # If using Africa's Talking
twilio>=9.0.0  # Already installed
redis>=4.5.0  # For session caching (optional)
```

---

### Step 3: Setup Database

```bash
# Apply USSD schema to your database
mysql -h your_host -u your_user -p your_database < ussd_database_schema.sql

# Or run in Python:
# python
# >>> from app import get_db
# >>> db = get_db()
# >>> cur = db.cursor()
# >>> cur.execute(open('ussd_database_schema.sql').read())
# >>> db.commit()
```

---

### Step 4: Environment Configuration

Create `.env` file with:

```bash
# ============ USSD CONFIGURATION ============

# USSD Provider (africastalking or twilio)
USSD_PROVIDER=africastalking

# USSD Shortcode (e.g., *384#)
USSD_SHORTCODE=*384#

# ============ AFRICA'S TALKING ============
AFRICASTALKING_API_KEY=your_api_key_here
AFRICASTALKING_USERNAME=your_username_here

# ============ TWILIO USSD (if using) ============
TWILIO_USSD_ENABLED=true

# ============ SESSION CONFIG ============
USSD_SESSION_TIMEOUT=600  # 10 minutes in seconds
USSD_SESSION_STORAGE=redis  # redis or database

# ============ REDIS (Optional) ============
REDIS_URL=redis://localhost:6379
REDIS_DB=1

# ============ RATE LIMITING ============
USSD_RATE_LIMIT=10/minute  # Per phone number
USSD_SESSION_LIMIT=1  # Only 1 active session per phone

# ============ SMS GATEWAY ============
USSD_SMS_GATEWAY=twilio
USSD_SMS_RATE_LIMIT=5/hour

# ============ SECURITY ============
USSD_REQUIRE_PHONE_VERIFICATION=true
USSD_OTP_LENGTH=4
USSD_OTP_EXPIRY=300  # 5 minutes

# ============ MONITORING ============
USSD_LOG_LEVEL=INFO
USSD_ERROR_NOTIFICATIONS=true
USSD_ERROR_EMAIL=admin@medicalai.health
```

---

### Step 5: Integrate USSD Module into app.py

Add to your main `app.py`:

```python
# ============ USSD INTEGRATION ============

# Import the USSD blueprint
from ussd_module import ussd_bp

# Register USSD blueprint
app.register_blueprint(ussd_bp)

# Enable CORS for USSD (if needed)
from flask_cors import CORS
CORS(app, resources={r"/ussd/*": {"origins": "*"}})

# Initialize USSD provider
USSD_PROVIDER = os.environ.get('USSD_PROVIDER', 'twilio')
USSD_SHORTCODE = os.environ.get('USSD_SHORTCODE', '*384#')

if USSD_PROVIDER == 'africastalking':
    try:
        import africastalking
        
        AT_API_KEY = os.environ.get('AFRICASTALKING_API_KEY')
        AT_USERNAME = os.environ.get('AFRICASTALKING_USERNAME')
        
        africastalking.initialize(AT_USERNAME, AT_API_KEY)
        ussd_gateway = africastalking.USSD
        HAS_USSD = True
        print(f"✓ Africa's Talking USSD initialized")
    except Exception as e:
        HAS_USSD = False
        print(f"✗ Africa's Talking USSD init failed: {e}")
else:
    HAS_USSD = True  # Using Twilio (already configured)
    print(f"✓ Twilio USSD enabled")

# ============ USSD STARTUP ROUTINES ============

def cleanup_expired_ussd_sessions():
    """Periodically cleanup expired USSD sessions"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        DELETE FROM ussd_sessions 
        WHERE expires_at < NOW() 
        OR (DATE_ADD(created_at, INTERVAL 10 MINUTE) < NOW() AND status = 'active')
    """)
    db.commit()
    print(f"Cleaned up expired USSD sessions")

# Run cleanup every 5 minutes
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_expired_ussd_sessions, trigger="interval", minutes=5)
scheduler.start()

# ============ ROUTES TO ADD ====================

@app.route('/admin/ussd/dashboard', methods=['GET'])
@require_login
def ussd_admin_dashboard():
    """Admin dashboard for USSD monitoring"""
    
    db = get_db()
    cur = db.cursor()
    
    # Get statistics
    cur.execute("""
        SELECT 
            COUNT(DISTINCT session_id) as total_sessions,
            COUNT(DISTINCT phone_number) as unique_users,
            COUNT(*) as total_transactions,
            AVG(processing_time_ms) as avg_response_time,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful
        FROM ussd_transactions
        WHERE created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
    """)
    
    stats = cur.fetchone()
    
    # Get top errors
    cur.execute("""
        SELECT error_type, COUNT(*) as count
        FROM ussd_error_logs
        WHERE created_at > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        GROUP BY error_type
        ORDER BY count DESC
        LIMIT 5
    """)
    
    errors = cur.fetchall()
    
    return jsonify({
        'stats': dict(stats) if stats else {},
        'top_errors': [dict(e) for e in errors],
        'ussd_enabled': HAS_USSD,
        'provider': USSD_PROVIDER,
        'shortcode': USSD_SHORTCODE
    })


@app.route('/admin/ussd/sessions', methods=['GET'])
@require_login
def ussd_sessions_list():
    """List active USSD sessions (admin only)"""
    
    if not is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    db = get_db()
    cur = db.cursor()
    
    cur.execute("""
        SELECT 
            session_id, phone_number, user_id, 
            created_at, last_activity, status
        FROM ussd_sessions
        WHERE status = 'active'
        AND expires_at > NOW()
        ORDER BY last_activity DESC
    """)
    
    sessions = cur.fetchall()
    return jsonify([dict(s) for s in sessions])


@app.route('/ussd/status', methods=['GET'])
def ussd_status():
    """Check USSD service status"""
    
    db = get_db()
    cur = db.cursor()
    
    # Get last transaction time
    cur.execute("SELECT MAX(created_at) as last_transaction FROM ussd_transactions")
    last_tx = cur.fetchone()
    
    return jsonify({
        'ussd_enabled': HAS_USSD,
        'provider': USSD_PROVIDER,
        'shortcode': USSD_SHORTCODE,
        'status': 'operational',
        'last_transaction': last_tx['last_transaction'].isoformat() if last_tx['last_transaction'] else None,
        'active_sessions': len([s for s in USSD_SESSIONS.values() 
                               if (datetime.now().timestamp() - s['last_activity']) < 600])
    })
```

---

### Step 6: Configure USSD Gateway Webhook

#### For Africa's Talking:

1. Go to https://africastalking.com/dashboard
2. Navigate to **USSD Settings**
3. Set **Callback URL** to:
   ```
   https://your-domain.com/ussd/callback
   ```
4. Set **Method**: POST
5. Save

#### For Twilio:

1. Go to Twilio Console → Messaging → USSD
2. Create new USSD Application
3. Set **Webhook URL**:
   ```
   https://your-domain.com/ussd/callback
   ```
4. Set **Method**: POST

---

### Step 7: Test USSD Locally

```bash
# Test endpoint with cURL
curl -X POST http://localhost:5000/ussd/callback \
  -d "sessionId=test-session-123" \
  -d "phone=+254720123456" \
  -d "text=" \
  -d "serviceCode=*384#"

# Expected response:
# CON Welcome to Medical AI
# Accessible via SMS & USSD
# ...
```

---

### Step 8: Test with Real Phone

1. **Get a phone number** from your USSD provider
2. **Dial shortcode**: `*384#`
3. **Walk through menu**
4. **Monitor logs**: `tail -f ussd_transactions`

---

### Step 9: Deploy to Production

```bash
# Commit changes
git add .
git commit -m "Feat: Add USSD integration for low-connectivity users"

# Push to production
git push origin main

# The following auto-deploy:
# - Backend: Render
# - Frontend: Vercel
# - Database: Aiven MySQL

# Verify deployment
curl https://medic-ai-back-end.onrender.com/ussd/status
```

---

## Monitoring & Troubleshooting

### Check USSD Status
```bash
curl https://medic-ai-back-end.onrender.com/ussd/status
```

### View Active Sessions
```bash
curl -H "Authorization: Bearer admin-token" \
  https://medic-ai-back-end.onrender.com/admin/ussd/sessions
```

### View Dashboard Stats
```bash
curl -H "Authorization: Bearer admin-token" \
  https://medic-ai-back-end.onrender.com/admin/ussd/dashboard
```

### Common Issues

#### USSD Sessions Timing Out
```
Solution: Increase SESSION_TIMEOUT in ussd_module.py
Current: 600 seconds (10 minutes)
Increase to: 900 seconds (15 minutes)
```

#### Gateway Not Receiving Callbacks
```
1. Check firewall allows POST on /ussd/callback
2. Verify webhook URL in gateway settings
3. Check gateway error logs
4. Test with gateway's callback tester
```

#### High Response Times
```
1. Check database query performance
2. Enable Redis caching for sessions
3. Check server CPU/memory usage
4. Profile slow endpoints
```

---

## Supported Countries (USSD)

### Africa's Talking Coverage:
- Kenya, Uganda, Tanzania, Rwanda, South Sudan
- Nigeria, Ghana, Cameroon, Benin, Côte d'Ivoire
- Ethiopia, Zambia, Zimbabwe, Malawi, Botswana
- And 28 more African countries

### Twilio Coverage:
- 100+ countries including most of Africa, Asia, Europe

---

## Cost Estimate (Updated)

```
Monthly costs for 10,000 active USSD users:

USSD Requests:
  - 2 requests per user per month = 20,000 requests
  - Cost per request: $0.01 (Africa's Talking)
  - Monthly: $200

SMS Alerts (via existing Twilio):
  - 5,500 SMS per month
  - Cost: $275

Total: $475/month for 10,000 users
Cost per user: $0.048/month (less than $1/year!)
```

---

## Security Checklist

- [ ] All USSD traffic encrypted (HTTPS)
- [ ] OTP validation working
- [ ] Rate limiting per phone
- [ ] PII not exposed in USSD responses
- [ ] Audit logs for all transactions
- [ ] Error messages don't leak system info
- [ ] Session expiry after timeout
- [ ] Password reset via OTP working

---

## Next Steps

1. ✅ Review USSD Integration Guide
2. ⏳ Set up Africa's Talking account
3. ⏳ Configure environment variables
4. ⏳ Run database migrations
5. ⏳ Deploy to production
6. ⏳ Test with real phones
7. ⏳ Monitor metrics & optimize

---

**Last Updated**: February 2026  
**Status**: Ready for Production Deployment
