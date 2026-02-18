# Deployment Setup Guide - Vercel + Railway

This guide walks you through deploying the Medical AI Assistant to production using Vercel (frontend) and Railway (backend).

**Estimated Time**: 4-6 hours  
**Difficulty**: Intermediate  
**Prerequisites**: Git account, Vercel account, Railway account

---

## Step 1: Pre-Deployment Security (30 minutes)

### 1.1 Rotate Credentials

Before deploying, you MUST rotate credentials to prevent unauthorized access.

```bash
# 1. Rotate database password
mysql -u root -p
> ALTER USER 'medical_user'@'localhost' IDENTIFIED BY 'NewStrongPassword123!';
> FLUSH PRIVILEGES;
> EXIT;

# 2. Create new Gemini API key
# - Go to console.cloud.google.com
# - Select your project
# - API Library → Google Generative AI
# - Create new API key
# - Copy the key

# 3. Create new SendGrid API key (if using)
# - Go to app.sendgrid.com/settings/api_keys
# - Create new API key with Mail Send permission
# - Copy the key
```

### 1.2 Prepare .env.production

Create a new file with production secrets (DO NOT commit to git):

```bash
cat > .env.production << 'EOF'
# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=your-long-random-secret-key-here
JWT_SECRET=your-long-random-jwt-secret-key-here

# Database (Will be provided by Railway)
DATABASE_URL=mysql://user:password@host:3306/medical_ai

# API Keys
GEMINI_API_KEY=your-new-gemini-api-key
SENDGRID_API_KEY=SG.your-sendgrid-api-key
SENDGRID_FROM_EMAIL=noreply@yourdomain.com

# CORS
CORS_ORIGINS=https://yourdomain.vercel.app,https://yourdomain.com

# Gunicorn
WORKERS=4
WORKER_CLASS=sync
WORKER_TIMEOUT=120
EOF

# DO NOT commit this file!
echo ".env.production" >> .gitignore
```

### 1.3 Remove .env from Git

```bash
# Remove .env from git history
git rm --cached .env
git commit -m "Remove .env file from git tracking"

# Verify .gitignore has .env
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Add .env to .gitignore"
```

---

## Step 2: Prepare Backend for Railway (1 hour)

### 2.1 Update Database Configuration

Edit `db.py` and add support for Railway's DATABASE_URL:

```python
# Find this section in db.py:
import urllib.parse

# Add after imports:
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Parse Railway MySQL URL: mysql://user:pass@host:port/dbname
    parsed = urllib.parse.urlparse(DATABASE_URL)
    DB_HOST = parsed.hostname
    DB_PORT = parsed.port or 3306
    DB_USER = parsed.username
    DB_PASSWORD = parsed.password
    DB_NAME = parsed.path.lstrip('/')
else:
    # Fallback to individual environment variables
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "medical_ai")
```

### 2.2 Update CORS Configuration

Edit `app.py` around line 640:

```python
# OLD:
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5000").split(",")

# NEW:
cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5000,http://127.0.0.1:5000,https://yourdomain.vercel.app"
).split(",")
cors_origins = [origin.strip() for origin in cors_origins]  # Remove whitespace
```

### 2.3 Add Production Logging

At the top of `app.py`, ensure proper logging:

```python
import logging

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log startup
logger.info("Medical AI Assistant starting...")
logger.info(f"Environment: {os.environ.get('FLASK_ENV', 'development')}")
logger.info(f"Debug mode: {os.environ.get('FLASK_DEBUG', '0')}")
```

### 2.4 Ensure requirements.txt is Updated

```bash
# Add gunicorn for production
pip install gunicorn

# Update requirements
pip freeze > requirements.txt

# Verify gunicorn is listed
grep gunicorn requirements.txt
```

---

## Step 3: Prepare Frontend for Vercel (45 minutes)

### 3.1 Update API URLs in HTML Files

You need to update all fetch calls to use the backend URL dynamically.

Create a file `js/config.js` or add to top of each HTML file:

```javascript
// Get API base URL from environment or detect from domain
const API_BASE_URL = (() => {
  // For local development
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:5000';
  }
  
  // For production - Railway backend
  const backendUrl = localStorage.getItem('api_url');
  if (backendUrl) return backendUrl;
  
  // Default production URL
  return 'https://medical-ai-backend.railway.app'; // Replace with your Railway app URL
})();

// Helper function for API calls
async function apiCall(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };
  
  // Add authorization token if available
  const token = sessionStorage.getItem('jwt_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  return fetch(url, { ...options, headers });
}
```

Then in HTML files, find all `fetch` calls and replace:

```javascript
// OLD:
fetch('http://localhost:5000/chat', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + token },
  body: JSON.stringify(data)
})

// NEW:
apiCall('/chat', {
  method: 'POST',
  body: JSON.stringify(data)
})
```

**Important files to update**:
- `dashboard.html` - Patient dashboard endpoints
- `doctor.html` - Doctor portal endpoints
- `auth.html` - Login endpoint
- `index.html` - Any API calls
- `profile.html` - User profile endpoints

---

## Step 4: Deploy Backend to Railway (1-2 hours)

### 4.1 Create Railway Account

1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub (recommended)
3. Authorize Railway to access your repositories

### 4.2 Create Railway Project

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Navigate to project directory
cd "c:\Users\DIANNA\Documents\AI proj"

# Initialize Railway project
railway init

# Follow prompts:
# - Create new project
# - Name: medical-ai-backend
# - Region: Choose closest to you
```

### 4.3 Set Up MySQL Database

In Railway dashboard:
1. Click "New Service"
2. Select "MySQL"
3. Choose plan (Free tier available)
4. Railway will automatically set `DATABASE_URL` environment variable

### 4.4 Configure Environment Variables

In Railway dashboard → Project → Variables:

```bash
# Flask
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=<your-generated-secret-key>
JWT_SECRET=<your-generated-jwt-secret>

# API Keys
GEMINI_API_KEY=<your-gemini-api-key>
SENDGRID_API_KEY=<your-sendgrid-api-key>
SENDGRID_FROM_EMAIL=noreply@yourdomain.com

# CORS
CORS_ORIGINS=https://yourdomain.vercel.app,https://yourdomain.com,http://localhost:3000

# Gunicorn
WORKERS=4
WORKER_TIMEOUT=120
```

### 4.5 Deploy Backend

```bash
# Make sure all changes are committed
git add .
git commit -m "Prepare for production deployment"

# Push to Railway
railway up

# Or if using GitHub:
git push origin main
# Railway will automatically deploy on push if configured

# Monitor deployment
railway logs --follow

# Get your Railway app URL
railway domain

# Save this URL - you'll need it for frontend config!
```

### 4.6 Test Backend Deployment

```bash
# Test health endpoint
curl https://your-railway-app.up.railway.app/health

# Should return: {"status": "healthy", "database": true}
```

---

## Step 5: Deploy Frontend to Vercel (30-45 minutes)

### 5.1 Create Vercel Account

1. Go to [vercel.com](https://vercel.com)
2. Sign up with GitHub (recommended)
3. Authorize Vercel to access your repositories

### 5.2 Connect GitHub Repository

1. In Vercel dashboard, click "New Project"
2. Import your GitHub repository
3. Select the repository with your Medical AI project

### 5.3 Configure Environment Variables

In Vercel → Project Settings → Environment Variables:

```bash
BACKEND_URL=https://your-railway-app.up.railway.app
GEMINI_API_KEY=<your-gemini-api-key> (optional, if needed client-side)
```

### 5.4 Configure Build Settings

In Vercel → Project Settings → Build & Development:

- **Build Command**: `echo 'Static site - no build needed'`
- **Output Directory**: `.` (current directory)
- **Install Command**: `npm install` (if package.json exists)

### 5.5 Deploy Frontend

Once configured:
1. Click "Deploy" button
2. Vercel will automatically build and deploy
3. You'll get a URL like `medical-ai.vercel.app`

### 5.6 Test Frontend Deployment

```bash
# Visit your Vercel app
# https://your-domain.vercel.app

# Test login
# Should redirect to auth.html
# Enter credentials
# Should connect to Railway backend
```

---

## Step 6: Post-Deployment Configuration (30 minutes)

### 6.1 Update Vercel Environment Variables

Now that you have both URLs, update Vercel:

```bash
BACKEND_URL=https://your-railway-app.up.railway.app
CORS_ALLOWED_ORIGINS=https://your-domain.vercel.app,https://yourdomain.com
```

### 6.2 Update Railway CORS

Update Railway environment variable:

```bash
CORS_ORIGINS=https://your-domain.vercel.app,https://yourdomain.com,https://www.yourdomain.com
```

### 6.3 Set Up Custom Domain (Optional)

**For Vercel**:
1. Project Settings → Domains
2. Add your domain (yourdomain.com)
3. Follow DNS instructions

**For Railway** (optional, for API):
1. Project Settings → Domains
2. Add custom domain
3. Point DNS to Railway

### 6.4 Verify HTTPS

Both Vercel and Railway provide free SSL certificates automatically. Verify:

```bash
# Vercel
curl -I https://yourdomain.vercel.app
# Should show 200 OK with Strict-Transport-Security header

# Railway
curl -I https://your-railway-app.up.railway.app/health
# Should show 200 OK
```

---

## Step 7: Testing & Validation (1-2 hours)

### 7.1 Functional Testing

- [ ] Homepage loads
- [ ] Can access login page
- [ ] Can create account
- [ ] Can login with account
- [ ] Can access dashboard
- [ ] Can send chat messages
- [ ] Can view doctor portal (if doctor)
- [ ] Can upload documents
- [ ] Notifications work

### 7.2 Performance Testing

```bash
# Measure page load time
time curl https://yourdomain.vercel.app > /dev/null

# Check API response time
time curl https://your-railway-app.up.railway.app/health

# Should be < 500ms for health check
```

### 7.3 Security Testing

```bash
# Check security headers
curl -I https://yourdomain.vercel.app | grep -E "Strict-Transport|X-Frame|Content-Security"

# Should include:
# - Strict-Transport-Security
# - X-Frame-Options: DENY
# - X-Content-Type-Options: nosniff

# Check with securityheaders.com
# Visit: https://securityheaders.com/?q=yourdomain.com
```

### 7.4 Database Testing

```bash
# Verify data persists
# 1. Create account
# 2. Wait 1 hour
# 3. Login again
# 4. Should see previous data
```

---

## Step 8: Monitoring & Maintenance

### 8.1 Set Up Alerts

**Railway**:
1. Project Settings → Notifications
2. Enable email notifications for:
   - Deployment failures
   - Memory exceeds 80%
   - CPU exceeds 80%
   - Crashes

**Vercel**:
1. Project Settings → Notifications
2. Enable for failed deployments

### 8.2 Monitor Logs

```bash
# Railway backend logs
railway logs --follow

# Check for errors
railway logs --error

# Vercel logs (in dashboard)
# Project → Deployments → Logs
```

### 8.3 Database Backups

Railway automatically backs up MySQL. To manually backup:

```bash
# SSH into Railway MySQL (optional)
# Or use Railway dashboard to export

# For scheduled backups, set up:
# - Daily exports
# - S3 storage (optional)
# - 30-day retention
```

---

## Troubleshooting

### Issue: CORS Error - "No 'Access-Control-Allow-Origin' header"

**Solution**:
1. Check CORS_ORIGINS in Railway environment
2. Verify Vercel domain is listed
3. Clear browser cache and reload
4. Check browser console for exact error

### Issue: Database Connection Failed

**Solution**:
1. Verify DATABASE_URL is set in Railway
2. Check MySQL service is running (Railway dashboard)
3. Verify DB_HOST, DB_USER, DB_PASSWORD if using individual vars
4. Test connection: `railway shell mysql -u root -p`

### Issue: API Returns 404 Not Found

**Solution**:
1. Check backend is deployed and running
2. Verify endpoint exists in app.py
3. Check for typos in API URL
4. Ensure API_BASE_URL is correct in frontend

### Issue: Slow Page Load

**Solution**:
1. Check Railway worker count (increase if needed)
2. Enable Railway caching
3. Optimize images/assets on Vercel
4. Monitor database query times
5. Consider CDN (Cloudflare, Vercel Edge)

### Issue: Email Not Sending

**Solution**:
1. Verify SENDGRID_API_KEY is set
2. Check SendGrid sender email is verified
3. Review SendGrid logs (app.sendgrid.com)
4. Test with /test/notifications endpoint

---

## Production Checklist

Before going live:

- [ ] All environment variables set in Railway
- [ ] Database backups configured
- [ ] Monitoring alerts enabled
- [ ] Email/SMS configured and tested
- [ ] Custom domain pointing to Vercel
- [ ] SSL certificates working (HTTPS only)
- [ ] API rate limiting enabled (if needed)
- [ ] Error logging configured
- [ ] Support documentation ready
- [ ] Incident response plan created
- [ ] Team trained on operations
- [ ] Go-live schedule announced

---

## Support & Escalation

**Issues with**:
- **Railway backend**: Check railway.app dashboard, contact Railway support
- **Vercel frontend**: Check vercel.com dashboard, contact Vercel support
- **MySQL database**: Check Railway MySQL settings, restart if needed
- **API connectivity**: Verify CORS_ORIGINS and environment variables

**Emergency Contact**:
- Railway Status: status.railway.app
- Vercel Status: vercel.com/statuspage
- SendGrid Status: sendgrid.com/statuspage

---

**Deployment Date**: [Fill in date]  
**Deployed By**: [Your name]  
**Backend URL**: [Railway app URL]  
**Frontend URL**: [Vercel app URL]  
**Support Contact**: [Email/Phone]  

---

For detailed information, see:
- `DEPLOYMENT_READINESS_REPORT.md` - Complete deployment analysis
- `PRODUCTION_DEPLOYMENT.md` - Security hardening guide
- `PRODUCTION_QUICK_REFERENCE.md` - Daily operations guide
