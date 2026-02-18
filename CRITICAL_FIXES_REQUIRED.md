# CRITICAL FIXES REQUIRED - DO NOT DEPLOY WITHOUT THESE

**Status**: 🔴 BLOCKING DEPLOYMENT  
**Time to Fix**: 90 minutes  
**Difficulty**: EASY (copy-paste code changes)  

---

## FIX #1: Remove Exposed Credentials from Git (30 min)

### ⚠️ CRITICAL SECURITY ISSUE
Your `.env` file contains production credentials and has been committed to git:
```
DB_PASSWORD=[REDACTED]
GEMINI_API_KEY=[REDACTED]
```

### STEPS TO FIX:

**Step 1: Rotate all credentials immediately**
```bash
# 1. Go to your database admin panel and change password
#    Old: 42125811Kamau
#    New: [generate random 20+ char password]

# 2. Go to Google Cloud Console and regenerate API key
#    https://console.cloud.google.com/apis/credentials

# 3. Go to SendGrid dashboard and create new API key
#    https://app.sendgrid.com/settings/api_keys
#
# Old credentials: [REDACTED]
```

**Step 2: Remove .env from git history**
```bash
git rm --cached .env
git add .gitignore
git commit -m "Remove .env from version control (security)"
git push origin main --force-with-lease
```

**Step 3: Update .gitignore**
```bash
echo ".env" >> .gitignore
git add .gitignore
git commit -m "Add .env to .gitignore"
git push origin main
```

**Step 4: Create .env.production (local only)**
```bash
# Store in: ~/.env.production
# Use Railway vault for production (never commit)
```

---

## FIX #2: Update database.py for Railway (10 min)

**Add this function after imports in db.py**:
```python
from urllib.parse import urlparse

def parse_database_url(url):
    """Parse Railway's DATABASE_URL format"""
    parsed = urlparse(url)
    return {
        'host': parsed.hostname,
        'port': parsed.port or 3306,
        'user': parsed.username,
        'password': parsed.password,
        'db': parsed.path[1:] if parsed.path else 'medical_ai'
    }
```

**Update db_connect function**:
```python
def db_connect():
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        config = parse_database_url(database_url)
    else:
        config = {
            'host': os.environ.get('DB_HOST', '127.0.0.1'),
            'port': int(os.environ.get('DB_PORT', '3306')),
            'user': os.environ.get('DB_USER', 'root'),
            'password': os.environ.get('DB_PASSWORD', ''),
            'db': os.environ.get('DB_NAME', 'medical_ai'),
            'charset': 'utf8mb4'
        }
    
    try:
        connection = pymysql.connect(
            host=config['host'],
            port=config['port'],
            user=config['user'],
            password=config['password'],
            database=config['db'],
            charset='utf8mb4'
        )
        return connection
    except Exception as e:
        print(f"Database connection failed: {e}")
        raise
```

---

## FIX #3: Update HTML Files for Dynamic API URLs (45 min)

**Add to top of each HTML file** (in `<head>`):
```html
<script>
    window.API_BASE = window.BACKEND_URL || 'http://localhost:5000';
    function apiUrl(path) {
        return `${window.API_BASE}${path}`;
    }
</script>
```

**Use Find & Replace in VS Code**:
1. Press `Ctrl+H`
2. Find: `'http://localhost:5000`
3. Replace: `${window.API_BASE}`
4. Click "Replace All"

**Files to update**:
- dashboard.html
- doctor.html
- auth.html
- profile.html
- index.html
- login.html
- admin.html

---

## FIX #4: CORS Configuration (Already Done ✅)

**Good news**: Code already reads `CORS_ORIGINS` from environment variable.

Just set in Railway:
```
CORS_ORIGINS=https://yourdomain.vercel.app,https://yourdomain.com
```

---

## FIX #5: Add Gunicorn (2 min)

**Add to requirements.txt**:
```
gunicorn>=21.0.0
```

---

## DEPLOYMENT BLOCKER CHECKLIST

- [ ] Credentials rotated (DB, API keys)
- [ ] `.env` removed from git
- [ ] `db.py` updated for DATABASE_URL
- [ ] HTML files updated with dynamic API URLs
- [ ] gunicorn added to requirements.txt
- [ ] Code tested locally
- [ ] No localhost URLs remain
- [ ] Ready to push to GitHub

---

**Cannot deploy without completing all above items.**

**Total Time**: 90 minutes

**Start with Fix #1** (credential rotation - most critical).

