# ⚡ APPLY THESE 4 FIXES NOW (60 minutes)

**Status**: Ready to deploy with current credentials for testing  
**Timeline**: 60 minutes to fix, then deploy  
**Credentials**: Keep current for testing, rotate at pre-release  

---

## 🔴 FIX #1: Update db.py (10 minutes)

**File**: `db.py`  
**Why**: Railway provides DATABASE_URL, need to parse it

**Add these imports at the top:**
```python
import os
from urllib.parse import urlparse
```

**Add this function after imports:**
```python
def parse_database_url(url):
    """Parse Railway's DATABASE_URL format: mysql://user:pass@host:port/db"""
    parsed = urlparse(url)
    return {
        'host': parsed.hostname,
        'port': parsed.port or 3306,
        'user': parsed.username,
        'password': parsed.password,
        'db': parsed.path[1:] if parsed.path else 'medical_ai'
    }
```

**Replace db_connect() function with this:**
```python
def db_connect():
    """Create database connection - supports both local and Railway DATABASE_URL"""
    
    # Try to parse Railway's DATABASE_URL first
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        config = parse_database_url(database_url)
    else:
        # Fall back to individual env vars for local development
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

**Test locally:**
```bash
python -c "from db import db_connect; db_connect(); print('DB OK')"
```

---

## 🔴 FIX #2: Update HTML Files (45 minutes)

**Files to update**: 
- `dashboard.html`
- `doctor.html`
- `auth.html`
- `profile.html`
- `index.html`
- `login.html`
- `admin.html`
- Any other HTML with API calls

**What to do:**

**Step 1**: Add this at the top of each HTML file (in `<head>` before first script):
```html
<script>
    // Get API base URL from environment or use localhost for development
    window.API_BASE = window.BACKEND_URL || 'http://localhost:5000';
</script>
```

**Step 2**: Find and replace all API calls

**Option A - Quick Find & Replace** (VS Code):
1. Press `Ctrl+H` (Find & Replace)
2. Find: `'http://localhost:5000`
3. Replace: `${window.API_BASE}`
4. Replace All

**Option B - Manual** (if above doesn't work):
```javascript
// OLD:
fetch('http://localhost:5000/chat', { ... })

// NEW:
fetch(`${window.API_BASE}/chat`, { ... })
```

**Examples of what to find & replace:**
```
'http://localhost:5000/chat'
'http://localhost:5000/patient/health-dashboard'
'http://localhost:5000/doctor/patients'
'http://localhost:5000/notifications'
'http://localhost:5000/login'
'http://localhost:5000/register'
```

**Test locally:**
```bash
python app.py
# Open dashboard.html in browser
# Open DevTools (F12) → Network tab
# Verify API calls go to http://localhost:5000 (not localhost:8000)
```

---

## 🟡 FIX #3: Add Gunicorn (2 minutes)

**File**: `requirements.txt`

**Add this line at the end:**
```
gunicorn>=21.0.0
```

**Test:**
```bash
pip install -r requirements.txt
gunicorn --version
```

---

## 🟡 FIX #4: Configure CORS (2 minutes)

**Status**: Code is ready, just need environment variable

**In Railway vault, set:**
```
CORS_ORIGINS=https://yourdomain.vercel.app,https://yourdomain.com
```

(Replace `yourdomain` with your actual domain)

**Current code in app.py already supports this:**
```python
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5000").split(",")
```

No code changes needed - just set the environment variable!

---

## ✅ VERIFICATION CHECKLIST

Before you deploy:

```bash
# 1. No syntax errors
python -m py_compile app.py db.py

# 2. Database connection works
python -c "from db import db_connect; db_connect(); print('DB OK')"

# 3. Can import app
python -c "import app; print('Import OK')"

# 4. Start app locally (Ctrl+C to stop)
python app.py

# 5. No localhost URLs in code
grep -r "localhost:5000" *.html  # Should be minimal (mostly in comments)

# 6. Requirements file is valid
pip install -r requirements.txt
```

---

## 📊 TIMELINE

```
Min 0-10:   Fix #1 (db.py) ✏️
Min 10-55:  Fix #2 (HTML) ✏️
Min 55-57:  Fix #3 (gunicorn) ✏️
Min 57-60:  Fix #4 (CORS) ✏️
```

**Total**: 60 minutes of work

---

## 🚀 AFTER FIXES - DEPLOY

Once all 4 fixes are done:

```bash
# 1. Test locally
python app.py
# Visit http://localhost:5000 in browser
# Test login, chat, dashboard
# Ctrl+C to stop

# 2. Push to GitHub
git add .
git commit -m "Prepare for testing: add DATABASE_URL support, dynamic API URLs"
git push origin main

# 3. Deploy to Railway
# Follow DEPLOYMENT_SETUP_GUIDE.md

# 4. Deploy to Vercel
# Follow DEPLOYMENT_SETUP_GUIDE.md

# 5. Test end-to-end
# Test login from Vercel domain
# Verify API calls work
# Check health endpoint
```

---

## 💡 IMPORTANT REMINDERS

✅ **Keep current credentials for testing**
- DB: `42125811Kamau`
- API: `AIzaSyBmrPjE9kPdR4_g61vQfFUuRUNXAlw5VIQ`
- SendGrid: [current]

⚠️ **Before market launch** (in 2-3 weeks):
- Rotate ALL credentials
- Remove .env from git

📌 **If you get errors:**
1. Check the error message
2. Search in DEPLOYMENT_SETUP_GUIDE.md troubleshooting
3. Verify environment variables are set
4. Restart the service

---

## 📋 DO THIS NOW

1. ✏️ Open `db.py` → Apply Fix #1
2. ✏️ Open `dashboard.html` → Apply Fix #2 (find & replace)
3. ✏️ Open `doctor.html` → Apply Fix #2 (find & replace)
4. ✏️ Open other HTML files → Apply Fix #2
5. ✏️ Open `requirements.txt` → Apply Fix #3
6. ✅ Run verification commands
7. 📤 Push to GitHub
8. 🚀 Deploy!

---

**Status**: Ready to execute  
**Effort**: 60 minutes of focused work  
**Result**: Deploy to Railway + Vercel for testing  
**Next**: Test thoroughly, find bugs, prepare credential rotation for pre-release

**Start with Fix #1 now!** ⏰

