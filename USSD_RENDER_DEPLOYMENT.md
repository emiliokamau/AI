# Quick Deployment Guide for Render

## Pre-Deployment Checklist

### 1. Verify Local Setup ✅
```bash
cd "c:\Users\DIANNA\Documents\AI proj"
python test_ussd_integration.py
# Should show: ✅ USSD integration test completed!
```

### 2. All Files in Place ✅
- ✅ `app.py` - Updated with USSD import and blueprint
- ✅ `.env` - Contains all USSD configuration
- ✅ `ussd_module.py` - USSD handler code
- ✅ `requirements.txt` - All dependencies listed
- ✅ Database: 10 USSD tables created in production MySQL

---

## Deployment Steps

### Step 1: Push to GitHub
```bash
cd "c:\Users\DIANNA\Documents\AI proj"
git add .
git commit -m "feat: Add USSD integration for 2G phone access"
git push origin main
```

### Step 2: Render Deployment (Automatic)
- Render should auto-detect changes and redeploy
- Deployment logs at: https://dashboard.render.com/

### Step 3: Verify Deployment
```bash
# Check if app is running
curl https://yourdomain.com/

# Test USSD endpoint
curl -X POST https://yourdomain.com/ussd/callback \
  -d "sessionId=test&phone=%2B254712345678&text="

# Should return: CON Welcome to Medical AI...
```

### Step 4: Configure USSD Provider

#### Option A: Using Existing Twilio
1. Go to https://www.twilio.com/console
2. Navigate to "Phone Numbers" → "Incoming Settings"
3. Find your phone number with USSD enabled
4. Set webhook URL: `https://yourdomain.com/ussd/callback`
5. Method: HTTP POST
6. Save

#### Option B: Africa's Talking (Alternative)
1. Sign up at https://africastalking.com
2. Get API key and username
3. Update .env in Render:
   ```env
   USSD_PROVIDER=africastalking
   AFRICASTALKING_API_KEY=your_key_here
   AFRICASTALKING_USERNAME=your_username
   ```
4. In Africa's Talking dashboard, set callback:
   - URL: `https://yourdomain.com/ussd/callback`
   - Method: POST

---

## Environment Variables in Render

Go to Render dashboard → Settings → Environment:

```env
# Database (from your Aiven MySQL instance)
DB_HOST=your_aiven_host
DB_PORT=10375
DB_USER=your_aiven_user
DB_PASSWORD=your_aiven_password
DB_NAME=defaultdb
GEMINI_API_KEY=your_gemini_api_key

USSD_PROVIDER=twilio
USSD_SHORTCODE=*384*52351#
TWILIO_USSD_ENABLED=true
USSD_SESSION_TIMEOUT=600
USSD_SESSION_STORAGE=database
USSD_OTP_LENGTH=4
USSD_OTP_EXPIRY=300
USSD_REQUIRE_PHONE_VERIFICATION=true
USSD_LOG_LEVEL=INFO
USSD_ERROR_NOTIFICATIONS=true
USSD_ERROR_EMAIL=emiliokamau35@gmail.com

# (Include other existing env vars)
```

---

## Testing in Production

### Test 1: Basic USSD Call
```bash
curl -X POST https://yourdomain.com/ussd/callback \
  -d "sessionId=test123&phone=%2B254712345678&text=" \
  -H "Content-Type: application/x-www-form-urlencoded"

# Expected response: CON Welcome to Medical AI...
```

### Test 2: Menu Selection
```bash
# User selects "1" (Symptoms)
curl -X POST https://yourdomain.com/ussd/callback \
  -d "sessionId=test123&phone=%2B254712345678&text=1"
```

### Test 3: Metrics
```bash
curl https://yourdomain.com/ussd/metrics

# Should return:
# {"active_sessions": 1, "last_updated": "...", "total_sessions": 1}
```

---

## Monitoring After Deployment

### Check Logs
1. Go to Render dashboard
2. Select your service
3. View "Logs" tab for real-time output
4. Look for "USSD module registered" message

### Database Monitoring
```bash
# Connect to production MySQL
mysql -h mysql-2ed289c-kamauemilio466-7999.i.aivencloud.com \
      -P 10375 \
      -u avnadmin \
      -p defaultdb

# Check active sessions
SELECT COUNT(*) FROM ussd_sessions WHERE expires_at > NOW();

# Check errors
SELECT * FROM ussd_error_logs ORDER BY created_at DESC LIMIT 10;

# Check usage
SELECT menu_name, total_selections FROM ussd_menu_analytics;
```

---

## Rollback (If Issues)

If USSD is causing problems:

### Option 1: Disable USSD (Quick)
```env
USSD_PROVIDER=disabled
```
Then redeploy.

### Option 2: Revert to Previous Version
```bash
git revert HEAD
git push origin main
# Render auto-redeploys
```

### Option 3: Restore from Backup
1. Database tables remain intact (don't delete them)
2. Remove ussd_module import from app.py
3. Remove blueprint registration
4. Redeploy

---

## Success Indicators

After deployment, you should see:
- ✅ USSD module registered (in Render logs)
- ✅ `/ussd/callback` endpoint responding to requests
- ✅ Database tables accessible (ussd_sessions, etc)
- ✅ OTP delivery working (requires Twilio SMS)
- ✅ Metrics endpoint returning data

---

## Support

### Common Deployment Issues

**Issue**: 502 Bad Gateway
- Check Render logs: `tail -f /var/log/app.log`
- Verify database connection in .env
- Ensure all Python dependencies installed

**Issue**: 404 on /ussd/callback
- Check app.py line 783-786 (blueprint registration)
- Verify USSD module imported correctly
- Restart Render service

**Issue**: USSD menu not responding
- Check logs for Python errors
- Verify database tables exist
- Test with curl command above

---

## Next: User Communication

Once USSD is live:

1. **SMS Campaign**
   ```
   "Access Medical AI without WiFi! Dial *384*52351# 
    from your phone to check symptoms, book doctors, 
    and access health records. Works on all 2G phones!"
   ```

2. **Social Media**
   - Post about USSD access feature
   - Share tutorial videos
   - Highlight "no WiFi needed" advantage

3. **In-App Notification**
   - Add banner: "New: USSD access for all phones"
   - Include shortcode: *384*52351#

4. **Support Training**
   - Prepare team for USSD troubleshooting
   - Document common issues
   - Set up escalation path

---

## Completion

🎉 **USSD is now live on your production system!**

Users can now access Medical AI from any 2G phone by dialing: **\*384\*52351#**

This opens your service to millions more patients in regions with limited data connectivity.
