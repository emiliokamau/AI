# Phase 3: Communication Features - Testing Guide

## Overview
Phase 3 implements a comprehensive communication system with three channels:
1. **In-app notifications** (stored in database)
2. **Email notifications** (via SendGrid API or SMTP)
3. **SMS notifications** (via Daraja/M-Pesa API)

## Test Endpoint

### POST /test/notifications
Test email and SMS delivery without creating actual notifications.

**Authentication:** Requires valid JWT token

**Request Body:**
```json
{
  "email": "user@example.com",
  "phone": "254712345678"
}
```

**Response:**
```json
{
  "email_sent": true,
  "sms_sent": false,
  "email_configured": true,
  "sms_configured": false
}
```

**Example cURL:**
```bash
curl -X POST http://localhost:5000/test/notifications \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "phone": "254712345678"}'
```

## Environment Variables Configuration

### Email Notifications (SendGrid - Primary)
```bash
# SendGrid API (Recommended)
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxx
SENDGRID_FROM_EMAIL=noreply@yourdomain.com
SENDGRID_FROM_NAME="Medical AI Assistant"
```

**How to get SendGrid API Key:**
1. Sign up at https://sendgrid.com (Free tier: 100 emails/day)
2. Go to Settings → API Keys
3. Create API Key with "Mail Send" permissions
4. Copy the key (shown only once)

### Email Notifications (SMTP - Fallback)
```bash
# SMTP Fallback (if SendGrid not available)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com
```

**Gmail App Password Setup:**
1. Enable 2-factor authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate app password for "Mail"
4. Use the 16-character password in SMTP_PASSWORD

### SMS Notifications (Daraja API - Safaricom)
```bash
# Daraja M-Pesa API (Kenya)
DARAJA_CONSUMER_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
DARAJA_CONSUMER_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxx
DARAJA_SHORTCODE=174379
DARAJA_INITIATOR_NAME=testapi
DARAJA_SECURITY_CREDENTIAL=xxxxxxxxxxxxxxxx
DARAJA_ENVIRONMENT=sandbox  # or 'production'
ENABLE_DARAJA_SMS=1  # Set to 1 to enable SMS
```

**How to get Daraja API credentials:**
1. Sign up at https://developer.safaricom.co.ke
2. Create an app (sandbox or production)
3. Copy Consumer Key and Consumer Secret
4. For production, get shortcode from Safaricom business account

### Other Required Variables
```bash
# Existing variables (already configured)
GEMINI_API_KEY=your-gemini-api-key
JWT_SECRET=your-jwt-secret
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your-db-password
DB_NAME=medical_ai
```

## Setting Environment Variables

### Windows (PowerShell)
```powershell
# Temporary (current session only)
$env:SENDGRID_API_KEY="SG.xxxxxxxxxxxx"
$env:SENDGRID_FROM_EMAIL="noreply@yourdomain.com"

# Permanent (user-level)
[System.Environment]::SetEnvironmentVariable('SENDGRID_API_KEY', 'SG.xxxxxxxxxxxx', 'User')
[System.Environment]::SetEnvironmentVariable('SENDGRID_FROM_EMAIL', 'noreply@yourdomain.com', 'User')
```

### Windows (Command Prompt)
```cmd
REM Temporary (current session only)
set SENDGRID_API_KEY=SG.xxxxxxxxxxxx
set SENDGRID_FROM_EMAIL=noreply@yourdomain.com

REM Permanent (requires restart)
setx SENDGRID_API_KEY "SG.xxxxxxxxxxxx"
setx SENDGRID_FROM_EMAIL "noreply@yourdomain.com"
```

### Linux/Mac
```bash
# Add to ~/.bashrc or ~/.zshrc
export SENDGRID_API_KEY="SG.xxxxxxxxxxxx"
export SENDGRID_FROM_EMAIL="noreply@yourdomain.com"

# Then reload
source ~/.bashrc
```

### Using .env File (Development)
Create a `.env` file in the project root:
```env
# SendGrid Email
SENDGRID_API_KEY=SG.xxxxxxxxxxxx
SENDGRID_FROM_EMAIL=noreply@yourdomain.com
SENDGRID_FROM_NAME=Medical AI Assistant

# Daraja SMS
DARAJA_CONSUMER_KEY=xxxxxxxxxxxxxxxx
DARAJA_CONSUMER_SECRET=xxxxxxxxxxxxxxxx
DARAJA_SHORTCODE=174379
DARAJA_INITIATOR_NAME=testapi
DARAJA_SECURITY_CREDENTIAL=xxxxxxxxxxxxxxxx
DARAJA_ENVIRONMENT=sandbox
ENABLE_DARAJA_SMS=1
```

Install python-dotenv:
```bash
pip install python-dotenv
```

Add to top of app.py:
```python
from dotenv import load_dotenv
load_dotenv()
```

## Testing Workflow

### 1. Test Email Only (SendGrid)
```bash
# Set environment variables
$env:SENDGRID_API_KEY="SG.your-api-key"
$env:SENDGRID_FROM_EMAIL="noreply@yourdomain.com"

# Restart Flask app
# Test with your actual email
curl -X POST http://localhost:5000/test/notifications \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "your-email@example.com"}'

# Expected response:
# {"email_sent": true, "sms_sent": false, "email_configured": true, "sms_configured": false}
```

### 2. Test SMS Only (Daraja Sandbox)
```bash
# Set environment variables
$env:DARAJA_CONSUMER_KEY="your-consumer-key"
$env:DARAJA_CONSUMER_SECRET="your-consumer-secret"
$env:DARAJA_ENVIRONMENT="sandbox"
$env:ENABLE_DARAJA_SMS="1"

# Restart Flask app
# Test with Kenyan phone number (sandbox: use test numbers)
curl -X POST http://localhost:5000/test/notifications \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone": "254712345678"}'

# Expected response:
# {"email_sent": false, "sms_sent": true, "email_configured": false, "sms_configured": true}
```

### 3. Test Both Channels
```bash
# Configure both SendGrid and Daraja
# Restart Flask app
curl -X POST http://localhost:5000/test/notifications \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "your-email@example.com", "phone": "254712345678"}'

# Expected response:
# {"email_sent": true, "sms_sent": true, "email_configured": true, "sms_configured": true}
```

## Testing Real Notifications

Once the test endpoint works, verify actual notifications are sent:

### 1. Send Direct Message
- Login as a patient
- Go to dashboard → Direct Messages
- Send a message to a doctor
- Doctor should receive:
  - In-app notification (red badge)
  - Email notification (if configured)
  - SMS notification (if configured)

### 2. Create Forum Post
- Login as a patient
- Go to dashboard → Community Forum
- Create a new post
- Other users following that condition tag should receive notifications

### 3. Reply to Forum Post
- Login as another user
- Reply to the forum post
- Original poster should receive notifications

## Troubleshooting

### Email not sending
1. Check `email_configured` is `true` in test response
2. Verify SENDGRID_API_KEY is valid
3. Check SendGrid dashboard for delivery logs
4. Verify sender email is verified in SendGrid
5. Check spam folder

### SMS not sending
1. Check `sms_configured` is `true` in test response
2. Verify ENABLE_DARAJA_SMS=1 is set
3. Check Daraja credentials are correct
4. Verify phone number format (254XXXXXXXXX for Kenya)
5. Check Daraja sandbox logs
6. For production, verify shortcode is active

### Database errors
```bash
# Check if Phase 3 tables exist
python -c "from db import init_db; init_db()"

# Should create: direct_messages, notifications, forum_posts, forum_replies
```

### Authorization errors
- Ensure JWT token is included in Authorization header
- Token format: `Bearer eyJhbGciOiJIUzI1NiIs...`
- Get token from login response or browser sessionStorage

## Production Deployment Checklist

- [ ] Sign up for SendGrid account (free tier: 100 emails/day)
- [ ] Generate SendGrid API key with Mail Send permissions
- [ ] Verify sender email address in SendGrid
- [ ] Set SENDGRID_API_KEY environment variable
- [ ] Set SENDGRID_FROM_EMAIL environment variable
- [ ] (Optional) Sign up for Daraja production account
- [ ] (Optional) Get production shortcode from Safaricom
- [ ] (Optional) Set DARAJA_* environment variables
- [ ] Test notifications in production environment
- [ ] Monitor SendGrid dashboard for delivery rates
- [ ] Set up error logging for failed notifications
- [ ] Consider rate limiting (create_notification has anti-spam logic)

## API Rate Limits

### SendGrid Free Tier
- 100 emails/day
- Upgrade to paid plans for more volume

### Daraja Sandbox
- Limited test numbers only
- Not for production use

### Daraja Production
- Based on Safaricom business account
- Contact Safaricom for rates

## Next Steps

1. **Configure SendGrid** (recommended first):
   - Quick signup, free tier available
   - Most reliable for email delivery
   
2. **Test email delivery**:
   - Use /test/notifications endpoint
   - Verify in SendGrid dashboard

3. **Configure Daraja** (optional):
   - Only needed for Kenya-based SMS
   - Start with sandbox for testing

4. **Enable in production**:
   - Set environment variables on server
   - Restart Flask application
   - Monitor notification logs

## Support

For issues:
1. Check environment variables are set correctly
2. Restart Flask app after changing variables
3. Test with /test/notifications endpoint first
4. Check provider dashboards (SendGrid, Daraja) for logs
5. Review Flask console for error messages
