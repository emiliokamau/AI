# USSD Implementation Checklist
## Step-by-Step Deployment Guide

---

## PHASE 0: PRE-IMPLEMENTATION (Do This First)

### Understanding & Approval
- [ ] Read USSD_INTEGRATION_GUIDE.md (20 min)
- [ ] Read SMS_EMERGENCY_VS_USSD_COMPARISON.md (15 min)
- [ ] Review this checklist (10 min)
- [ ] Discuss timeline with team
- [ ] Get stakeholder approval
- [ ] Allocate developer time (80 hours)
- [ ] Budget $4,500-5,000 for setup

### Market Research
- [ ] Identify target user demographics
- [ ] Research feature phone prevalence in target regions
- [ ] Check USSD availability in each country
- [ ] Verify regulatory requirements (HIPAA, local laws)
- [ ] Plan marketing strategy

---

## PHASE 1: PROVIDER SETUP (Week 1, Days 1-2)

### Option A: Africa's Talking (RECOMMENDED)

#### Account Creation
- [ ] Go to https://africastalking.com/register
- [ ] Create account with company email
- [ ] Verify email address
- [ ] Complete KYC (Know Your Customer) verification
- [ ] Add billing information
- [ ] Set spending limit ($1,000/month for safety)

#### Sandbox Testing
- [ ] Login to Dashboard
- [ ] Copy Sandbox API Key
- [ ] Test API with sandbox credentials
- [ ] Request shortcode: 
  - [ ] Go to USSD Settings
  - [ ] Click "Request Shortcode"
  - [ ] Choose shortcode (e.g., *384#)
  - [ ] Select countries (Kenya, Uganda, Tanzania, etc)
  - [ ] Fill application form
  - [ ] Submit (processing: 1-2 weeks)

#### Production Setup
- [ ] Wait for shortcode approval email
- [ ] Copy Production API Key
- [ ] Enable Production Mode in Dashboard
- [ ] Set webhook URL: `https://medic-ai-back-end.onrender.com/ussd/callback`
- [ ] Test webhook with callback tester
- [ ] Set Callback URL format: JSON
- [ ] Enable SMS gateway for confirmation messages

### Option B: Twilio USSD (ALTERNATIVE)

#### Account Creation
- [ ] Twilio account already exists
- [ ] Go to Console → Messaging → USSD
- [ ] Create new USSD Application
- [ ] Name: "Medical AI"
- [ ] Webhook URL: `https://medic-ai-back-end.onrender.com/ussd/callback`
- [ ] Method: POST

#### Configuration
- [ ] Buy USSD-enabled phone number
- [ ] Associate with USSD application
- [ ] Set callback method to POST
- [ ] Enable error webhook (for monitoring)
- [ ] Configure rate limiting

---

## PHASE 2: LOCAL DEVELOPMENT (Week 1, Days 3-5)

### Environment Setup

#### Clone/Update Repository
- [ ] `git pull origin main`
- [ ] Check current branch is `main`
- [ ] Verify workspace is clean (`git status`)

#### Create .env File
```bash
# Create file: .env in project root
cp .env.example .env
```

Add these variables:
```
# USSD Configuration
USSD_PROVIDER=africastalking
USSD_SHORTCODE=*384#
USSD_SESSION_TIMEOUT=600
USSD_SESSION_STORAGE=database

# Africa's Talking (if chosen)
AFRICASTALKING_API_KEY=your_api_key_here
AFRICASTALKING_USERNAME=your_username_here

# Twilio USSD (if chosen)
TWILIO_USSD_ENABLED=true

# Database
DB_HOST=your_host
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=medical_ai

# Security
USSD_OTP_LENGTH=4
USSD_OTP_EXPIRY=300
USSD_REQUIRE_PHONE_VERIFICATION=true
USSD_LOG_LEVEL=INFO

# Monitoring
USSD_ERROR_NOTIFICATIONS=true
USSD_ERROR_EMAIL=admin@medicalai.health
```

#### Install Dependencies
```bash
# Check if requirements-ussd.txt needed
pip install flask-cors
pip install africastalking  # If using Africa's Talking
pip install redis  # Optional but recommended for sessions
```

#### Create Database Schema
```bash
# Backup current database (IMPORTANT!)
mysqldump -u root -p medical_ai > backup_$(date +%Y%m%d).sql

# Apply USSD schema
mysql -u root -p medical_ai < ussd_database_schema.sql

# Verify tables created
mysql -u root -p medical_ai -e "SHOW TABLES LIKE 'ussd_%';"
```

#### Copy Module Files
```bash
# Files should be in project root:
# - ussd_module.py (already created)
# - ussd_database_schema.sql (already created)
# - Check they exist:
ls -la ussd_module.py ussd_database_schema.sql
```

### Code Integration

#### Update app.py
Add at the imports section:
```python
from ussd_module import ussd_bp
```

Add after Flask app initialization:
```python
# Register USSD blueprint
app.register_blueprint(ussd_bp)

# Initialize USSD provider
USSD_PROVIDER = os.environ.get('USSD_PROVIDER', 'twilio')
USSD_SHORTCODE = os.environ.get('USSD_SHORTCODE', '*384#')

if USSD_PROVIDER == 'africastalking':
    try:
        import africastalking
        AT_API_KEY = os.environ.get('AFRICASTALKING_API_KEY')
        AT_USERNAME = os.environ.get('AFRICASTALKING_USERNAME')
        africastalking.initialize(AT_USERNAME, AT_API_KEY)
        HAS_USSD = True
        print(f"✓ Africa's Talking USSD initialized")
    except Exception as e:
        HAS_USSD = False
        print(f"✗ Africa's Talking USSD init failed: {e}")
else:
    HAS_USSD = True
    print(f"✓ Twilio USSD enabled")
```

Add cleanup job (around line 100):
```python
from apscheduler.schedulers.background import BackgroundScheduler

def cleanup_expired_ussd_sessions():
    """Cleanup expired USSD sessions"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        DELETE FROM ussd_sessions 
        WHERE expires_at < NOW() 
        OR (DATE_ADD(created_at, INTERVAL 10 MINUTE) < NOW() AND status = 'active')
    """)
    db.commit()
    print(f"✓ Cleaned up expired USSD sessions")

scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_expired_ussd_sessions, trigger="interval", minutes=5)
scheduler.start()
```

### Local Testing

#### Test 1: Check Module Imports
```bash
python -c "from ussd_module import ussd_bp; print('✓ Module imports OK')"
```

#### Test 2: Check Database Connection
```bash
python -c "
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='your_pass', database='medical_ai')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) as count FROM ussd_sessions')
print(f'✓ Database OK: {cur.fetchone()[0]} sessions')
conn.close()
"
```

#### Test 3: Check Flask App
```bash
python -c "from app import app; print('✓ App imports OK')"
```

#### Test 4: Mock USSD Request (Local)
```bash
curl -X POST http://localhost:5000/ussd/callback \
  -d "sessionId=test-123" \
  -d "phone=+254720123456" \
  -d "text=" \
  -d "serviceCode=*384#"

# Expected response:
# CON Welcome to Medical AI...
```

---

## PHASE 3: STAGING DEPLOYMENT (Week 2, Days 6-7)

### Deploy to Render

#### Commit Changes
```bash
cd c:\Users\DIANNA\Documents\AI proj

# Check status
git status

# Stage all changes
git add app.py ussd_module.py .env

# Create commit message
git commit -m "Feat: Add USSD integration for low-connectivity users"

# Verify commit
git log --oneline -1
```

#### Push to GitHub
```bash
git push origin main

# Verify on GitHub
# https://github.com/emiliokamau/AI
# Should show new commit in main branch
```

#### Update Render Environment
1. Go to Render Dashboard
2. Select "medic-ai-back-end" service
3. Click "Settings" → "Environment"
4. Add environment variables:
   - `USSD_PROVIDER=africastalking`
   - `AFRICASTALKING_API_KEY=your_key`
   - `AFRICASTALKING_USERNAME=your_username`
   - `USSD_SHORTCODE=*384#`
5. Click "Save"
6. Wait for auto-deployment (~3 min)

#### Verify Staging
```bash
# Check if deployed
curl https://medic-ai-back-end.onrender.com/ussd/status

# Expected response:
# {
#   "ussd_enabled": true,
#   "provider": "africastalking",
#   "shortcode": "*384#",
#   "status": "operational"
# }
```

### Configure USSD Provider Webhook

#### Africa's Talking
1. Dashboard → USSD Settings
2. Callback URL: `https://medic-ai-back-end.onrender.com/ussd/callback`
3. Callback Method: POST
4. Callback Format: JSON
5. Save

#### Twilio
1. Console → Messaging → USSD
2. Select application
3. Webhook URL: `https://medic-ai-back-end.onrender.com/ussd/callback`
4. Save

### Staging Testing

#### Test 1: Callback Endpoint
```bash
curl -X POST https://medic-ai-back-end.onrender.com/ussd/callback \
  -d "sessionId=staging-test-123" \
  -d "phone=+254720123456" \
  -d "text=" \
  -d "serviceCode=*384#"

# Should receive main menu
```

#### Test 2: Check Database
```bash
# Verify session was stored
mysql -h your_host -u root -p your_database \
  -e "SELECT COUNT(*) as count FROM ussd_sessions;"

# Should be > 0
```

#### Test 3: Menu Navigation
```bash
# Test pressing "1" (Symptom Checker)
curl -X POST https://medic-ai-back-end.onrender.com/ussd/callback \
  -d "sessionId=staging-test-123" \
  -d "phone=+254720123456" \
  -d "text=1" \
  -d "serviceCode=*384#"

# Should get symptom menu
```

#### Test 4: Emergency Alert Flow
```bash
# Test emergency (choice 2)
curl -X POST https://medic-ai-back-end.onrender.com/ussd/callback \
  -d "sessionId=staging-test-123" \
  -d "phone=+254720123456" \
  -d "text=2" \
  -d "serviceCode=*384#"

# Should get severity menu (1-5)
```

### Monitor Logs
```bash
# View Render logs
# https://dashboard.render.com
# Select "medic-ai-back-end"
# Click "Logs" tab
# Monitor for errors

# Should see:
# ✓ Africa's Talking USSD initialized
# ✓ Cleaned up expired USSD sessions (every 5 min)
```

---

## PHASE 4: PHONE TESTING (Week 2, Days 8-10)

### Get Test Phone Numbers

#### Option 1: Use Developer Phone
- [ ] Get smartphone that can switch to 2G
- [ ] Get basic feature phone (recommended)
- [ ] Ensure phone is registered with telco
- [ ] Have at least 3 phone numbers (for testing)

#### Option 2: Use Provider's Testing Service
- [ ] Africa's Talking offers testing sandbox
- [ ] Twilio has testing webhooks
- [ ] Test without real phone first

### Test Flow Matrix

Create spreadsheet with test cases:

```
Test #  | Flow             | Phone      | Expected | Status | Notes
--------|------------------|------------|----------|--------|--------
1       | Main Menu        | +254720... | Menu 1-5 | [ ]    |
2       | Symptom Check    | +254720... | Symptoms | [ ]    |
3       | Emergency L1     | +254720... | Not Urg  | [ ]    |
4       | Emergency L5     | +254720... | Alert!   | [ ]    |
5       | Doctor Booking   | +254720... | Specty   | [ ]    |
6       | Health History   | +254720... | Summary  | [ ]    |
7       | Medications      | +254720... | Med list | [ ]    |
8       | Back/Exit        | +254720... | Confirm  | [ ]    |
9       | Timeout (10min)  | +254720... | Expired  | [ ]    |
10      | Invalid Input    | +254720... | Retry    | [ ]    |
```

### Execute Tests

#### Test 1: Main Menu
```
1. Dial *384#
2. Wait for menu
3. Check: Shows options 1-5
4. Check: All text is clear and readable
5. Check: Response time < 2 seconds
✓ Mark complete
```

#### Test 2: Symptom Checker
```
1. Dial *384#
2. Press 1
3. Wait for symptoms menu
4. Check: Shows 5 symptom options
5. Check: Can press back (0)
✓ Mark complete
```

#### Test 3: Emergency Alert (Level 5)
```
1. Dial *384#
2. Press 2 (Emergency)
3. Press 5 (Critical)
4. Press 1 (Chest Pain - example)
5. Press 1 (Confirm)
6. Check: Get success message
7. VERIFY: SMS sent to test doctor phone
   - Should receive SMS with:
     - Emergency severity
     - Patient name
     - Symptoms
     - Triage ID
✓ Mark complete
```

#### Test 4: Doctor Booking
```
1. Dial *384#
2. Press 3 (Book Doctor)
3. Press 1 (General Practice)
4. Press 1 (Today)
5. Press 1 (Confirm)
6. Check: Get confirmation message
7. Check: SMS confirmation received
✓ Mark complete
```

#### Test 5: Session Timeout
```
1. Dial *384#
2. Do NOT respond for 11 minutes
3. Try to respond
4. Check: Session has expired message
✓ Mark complete
```

### Document Issues
- [ ] Screenshot any errors
- [ ] Note exact phone model & OS
- [ ] Note network type (2G/3G/4G)
- [ ] Note response times
- [ ] Report bugs in GitHub issues

---

## PHASE 5: PRODUCTION DEPLOYMENT (Week 3, Day 1)

### Pre-Deployment Checklist

#### Code Quality
- [ ] All tests passing
- [ ] No syntax errors
- [ ] No console warnings
- [ ] Database queries optimized
- [ ] Rate limiting configured

#### Security
- [ ] All environment variables set
- [ ] No hardcoded credentials
- [ ] HTTPS enforced
- [ ] Rate limiting in place
- [ ] OTP expiry set to 5 minutes
- [ ] Session timeout set to 10 minutes

#### Database
- [ ] All 10 USSD tables created
- [ ] Indexes created
- [ ] Stored procedures working
- [ ] Backup taken
- [ ] Test data cleared

#### Monitoring
- [ ] Error logging configured
- [ ] Metrics endpoint ready
- [ ] Alert email configured
- [ ] Dashboard ready

### Deploy to Production

#### Final Commit
```bash
# Status check
git status

# If any uncommitted changes
git add .
git commit -m "Chore: Final production prep for USSD"

# Push
git push origin main

# Verify in GitHub
```

#### Update Production Environment (Render)

1. Dashboard → medic-ai-back-end
2. Settings → Environment
3. Update (if needed):
   - Ensure all USSD variables are set
   - Verify database credentials

#### Manual Database Migration (If Needed)
```bash
# SSH into production (if needed)
# Or use database client to run:

# 1. Backup production database
mysqldump -h production-host -u user -p database_name > backup_prod_$(date +%Y%m%d).sql

# 2. Apply USSD schema
mysql -h production-host -u user -p database_name < ussd_database_schema.sql

# 3. Verify
mysql -h production-host -u user -p database_name -e "SHOW TABLES LIKE 'ussd_%';"
```

### Verify Production

#### Test 1: Service Status
```bash
curl https://medic-ai-back-end.onrender.com/ussd/status

# Response should show operational
```

#### Test 2: Production Phone Test
```
1. Get one test number
2. Dial *384#
3. Verify main menu appears
4. Test emergency alert flow
5. Verify SMS received
6. Check database for new records
```

#### Test 3: Check Logs
```bash
# Render dashboard → Logs
# Should show:
# - USSD requests being processed
# - No errors
# - Session cleanup running
```

#### Test 4: Admin Metrics
```bash
# If authenticated, check:
curl -H "Authorization: Bearer admin-token" \
  https://medic-ai-back-end.onrender.com/admin/ussd/dashboard

# Should show statistics
```

---

## PHASE 6: MONITORING (Week 3, Days 2-7)

### Daily Checks

#### Morning (9 AM)
- [ ] Check error logs for overnight issues
- [ ] Verify all sessions cleaned up
- [ ] Check SMS delivery logs
- [ ] Review user feedback

#### Afternoon (2 PM)
- [ ] Check active USSD sessions count
- [ ] Verify emergency alerts processed
- [ ] Check response times
- [ ] Monitor CPU/memory usage

#### Evening (5 PM)
- [ ] Prepare daily report
- [ ] Note any trends or issues
- [ ] Check for database growth

### Weekly Reporting

Create report with:
```
Date: [Week]
Active Users: [Count]
Total Sessions: [Count]
Emergency Alerts: [Count]
Avg Response Time: [X seconds]
Error Rate: [X%]
Top Errors: [List]
Issues Fixed: [List]
Next Week Plans: [List]
```

### Dashboard Setup

#### Create Monitoring Dashboard
```
Go to: https://medic-ai-back-end.onrender.com/admin/ussd/dashboard
Metrics to monitor:
  - Active sessions
  - Transactions/minute
  - Average response time
  - Error rate
  - Top menus used
```

#### Set Up Alerts
- [ ] Email alert if error rate > 5%
- [ ] Email alert if response time > 5 seconds
- [ ] Email alert if downtime > 5 minutes
- [ ] SMS alert for critical errors

---

## PHASE 7: USER EDUCATION (Week 3, Days 3-5)

### Create User Documentation

#### In-App Messages
- [ ] Add USSD info to dashboard
- [ ] Create help section for USSD
- [ ] Add USSD tutorial video

#### Promotional SMS Campaign
```
Template:
"Get Medical AI on any phone!
No internet needed.
Dial *384# to:
- Check symptoms
- Get emergency help
- Book doctor
- View health info

Works on all phones.
Learn more: medicalai.health/ussd"
```

### Select Target Users
```sql
SELECT user_id, phone_number 
FROM users 
WHERE country IN ('KE', 'UG', 'TZ')
AND NOT ussd_enabled
LIMIT 1000;  -- Start with 1,000 users
```

### Send SMS Invitations
- [ ] Create SMS campaign in marketing system
- [ ] Target 1,000 users first (Week 3)
- [ ] Expand to 10,000 (Week 4)
- [ ] Expand to all (Week 5)

### Track Adoption
```
Metrics to watch:
  - % of invited users who try USSD
  - % of trialed users who continue
  - Most popular USSD features
  - Emergency response time improvement
```

---

## PHASE 8: OPTIMIZATION (Week 4+)

### Performance Tuning

#### If Response Time > 2 seconds:
- [ ] Check database query plans
- [ ] Add missing indexes
- [ ] Enable Redis caching
- [ ] Profile slow endpoints

#### If Error Rate > 5%:
- [ ] Review error logs
- [ ] Fix common errors
- [ ] Improve error messages
- [ ] Add better validation

#### If Low Adoption:
- [ ] Improve USSD menu design
- [ ] Add more tutorial messages
- [ ] Gather user feedback
- [ ] Iterate on features

### Scaling

#### When > 10,000 users:
- [ ] Switch session storage to Redis
- [ ] Add read replicas for database
- [ ] Implement caching layer
- [ ] Load test to 1000 concurrent sessions

### Phase 2 Planning

- [ ] Gather user feedback
- [ ] Plan multi-language support
- [ ] Plan payment integration (M-Pesa)
- [ ] Plan advanced features

---

## SUCCESS CRITERIA

### Week 1 ✓ Setup Complete
- [ ] Account created with USSD provider
- [ ] Shortcode registered and pending approval
- [ ] Database schema applied
- [ ] Module integrated into app.py
- [ ] Local testing passing

### Week 2 ✓ Staging & Phone Testing
- [ ] Deployed to staging (Render)
- [ ] Webhook configured
- [ ] Phone tests passing on real devices
- [ ] Emergency alerts working
- [ ] No critical bugs found

### Week 3 ✓ Production Live
- [ ] Deployed to production
- [ ] 100+ users accessed USSD
- [ ] 10+ emergency alerts processed
- [ ] Average response time < 2 seconds
- [ ] Error rate < 2%

### Week 4 ✓ Growth & Optimization
- [ ] 1,000+ active users
- [ ] 100+ daily active users
- [ ] Metrics dashboard live
- [ ] User feedback collected
- [ ] Optimization plan created

---

## GO/NO-GO DECISION POINTS

### Day 5 Checkpoint
**Decision**: Deploy to staging or continue fixing?

Go if:
- [ ] All unit tests passing
- [ ] No critical bugs
- [ ] Database schema working
- [ ] API responding correctly

No-go if:
- [ ] Security vulnerabilities found
- [ ] Critical database issues
- [ ] API crashes on test

### Day 10 Checkpoint
**Decision**: Deploy to production or continue staging?

Go if:
- [ ] Emergency alerts tested on real phones
- [ ] < 3 critical issues in logs
- [ ] Response time consistently < 2 seconds
- [ ] All menu flows working

No-go if:
- [ ] SMS not being delivered
- [ ] High error rate
- [ ] Database connection issues
- [ ] Security issues found

### Day 15 Checkpoint
**Decision**: Full rollout to all users or limited beta?

Go if:
- [ ] 100+ users tested without major issues
- [ ] Emergency flow working correctly
- [ ] Metrics dashboard monitoring
- [ ] Support team trained

No-go if:
- [ ] Multiple bugs reported
- [ ] User complaints about UX
- [ ] Performance degradation
- [ ] Unresolved security issues

---

## ROLLBACK PLAN

### If Critical Issues in Production:

#### Immediate (< 5 minutes)
```bash
# 1. Disable USSD endpoint
# In Render settings, set:
USSD_PROVIDER=disabled

# 2. Verify fallback to web/SMS
curl https://medic-ai-back-end.onrender.com/ussd/status
# Should show "disabled"

# 3. Notify users via SMS
send_sms_to_all("USSD temporarily offline. Use web app or call doctors. Apologize for inconvenience.")
```

#### Short-term (< 1 hour)
```bash
# 1. Identify the bug
# Check logs, error rate, response times

# 2. Create fix locally
# Update code, test, verify

# 3. Deploy fix
git commit -m "Fix: USSD critical bug"
git push origin main
# Wait for Render auto-deploy (~3 min)

# 4. Re-enable USSD
# Update Render environment variable

# 5. Verify fix
curl https://medic-ai-back-end.onrender.com/ussd/status
```

#### Worst case (> 1 hour)
```bash
# 1. Revert to previous commit
git revert HEAD
git push origin main

# 2. Wait for Render deployment

# 3. Verify working
# 4. Post incident report
# 5. Schedule fix for next maintenance window
```

---

## DOCUMENTATION CHECKLIST

- [ ] README updated with USSD info
- [ ] API documentation includes /ussd/callback
- [ ] Admin guide includes USSD monitoring
- [ ] User guide includes USSD tutorial
- [ ] Developer guide includes USSD setup
- [ ] Troubleshooting guide has USSD section
- [ ] Architecture diagram updated

---

## SIGN-OFF

### Developer Sign-Off
```
Name: _________________
Date: _________________
I confirm all checklist items are complete and tested.
```

### QA Sign-Off
```
Name: _________________
Date: _________________
I confirm all tests passed and no critical bugs remain.
```

### Product Manager Sign-Off
```
Name: _________________
Date: _________________
I approve deployment to production.
```

---

## NOTES FOR NEXT IMPLEMENTER

```
What worked well:
- [Document successes]

What was challenging:
- [Document difficulties]

Improvements for next phase:
- [Document learnings]

Contact for questions:
- [Your contact info]

Last updated: [Date]
```

---

**Congratulations!** 🎉  
You now have a complete, step-by-step implementation plan.  
Estimated time: 2-3 weeks to full production deployment.

**Good luck!** 🚀
