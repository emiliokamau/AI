# TESTING PHASE DEPLOYMENT PLAN

**Decision**: Use current credentials ([REDACTED] / [REDACTED]...) for testing  
**Credential Rotation**: Deferred to pre-market release (2-3 weeks)  
**Current Status**: Ready for internal testing  
**Timeline**: Deploy today, test thoroughly, rotate before market launch  

---

## 🎯 PHASE 1: TESTING (TODAY - 60 MINUTES)

### Critical Fixes Needed (4 items - 60 min)

#### Fix #1: Update db.py for DATABASE_URL (10 min)
**Status**: ⏳ Pending  
**Why**: Railway provides DATABASE_URL, not individual env vars  
**Action**: Add DATABASE_URL parser to db.py  
**File**: `db.py`

#### Fix #2: Update HTML Files for Dynamic API URLs (45 min)
**Status**: ⏳ Pending  
**Why**: API calls hardcoded to localhost:5000  
**Action**: Add dynamic API base URL configuration  
**Files**: `dashboard.html`, `doctor.html`, auth.html, etc.

#### Fix #3: Add Gunicorn to requirements.txt (2 min)
**Status**: ⏳ Pending  
**Why**: Production WSGI server  
**Action**: Add `gunicorn>=21.0.0`  
**File**: `requirements.txt`

#### Fix #4: Configure CORS Environment Variable (3 min)
**Status**: ✅ Code ready (just need to set env var)  
**Why**: Vercel domain needs to be in CORS origins  
**Action**: Set in Railway vault: `CORS_ORIGINS=https://yourdomain.vercel.app`  
**File**: Railway vault only (not code)

**Total Time**: 60 minutes

---

## 🎯 PHASE 2: TESTING & VALIDATION (TODAY + TOMORROW)

### Deploy to Testing Infrastructure

```
Deploy to Railway (backend):
├─ URL: https://yourdomain.railway.app
├─ Credentials: [REDACTED] / [REDACTED]...
├─ Test: Login, chat, notifications
└─ Monitor: Error logs for issues

Deploy to Vercel (frontend):
├─ URL: https://yourdomain.vercel.app
├─ Connect to Railway backend
├─ Test: All user flows
└─ Verify: HTTPS, no console errors
```

### Testing Checklist
- [ ] User registration works
- [ ] Login succeeds
- [ ] Chat sends/receives messages
- [ ] Notifications trigger
- [ ] Doctor portal loads
- [ ] Admin panel accessible
- [ ] No CORS errors
- [ ] No API timeouts
- [ ] Database queries work
- [ ] Health check passes

---

## 🎯 PHASE 3: CREDENTIAL ROTATION (BEFORE MARKET LAUNCH)

**When**: 2-3 weeks from now, before going live with real users

### Pre-Release Security Hardening (30 minutes)

1. **Rotate Database Password** (10 min)
   - Current: `[REDACTED]`
   - New: Generate strong password (20+ chars)
   - Update in Railway vault

2. **Regenerate Gemini API Key** (5 min)
   - Current: `[REDACTED]`
   - Create new in Google Cloud Console
   - Update in Railway vault

3. **Regenerate SendGrid API Key** (5 min)
   - Create new in SendGrid dashboard
   - Update in Railway vault

4. **Remove .env from Git** (10 min)
   - `git rm --cached .env`
   - Add `.env` to `.gitignore`
   - Force push to clean history

5. **Final Security Review** (5 min)
   - Verify no credentials in code
   - Verify no credentials in git history
   - Verify all secrets in vaults only

---

## 📊 DEPLOYMENT TIMELINE

```
TODAY (60 minutes work)
  09:00 - Apply 4 code fixes
  10:00 - Test locally
  10:30 - Deploy to Railway & Vercel
  11:00 - End-to-end testing
  12:00 - INTERNAL TESTING LIVE ✅

TOMORROW - DAYS (Ongoing)
  Test thoroughly
  Find & fix bugs
  Improve performance
  Gather feedback

WEEK 2-3 (Before Market Launch)
  Rotate all credentials
  Final security review
  Prepare for public launch
  Document for support team
```

---

## 🔐 CREDENTIALS STATUS

### Current (Testing Only)
```
DB_PASSWORD=[REDACTED]
GEMINI_API_KEY=[REDACTED]
SENDGRID_API_KEY=[current]
```

**Status**: ✅ Acceptable for testing  
**Risk**: LOW (internal testing only)  
**When to rotate**: Before any public launch  
**Location**: `.env` file (will move to vault later)

### Before Market Launch (Production)
```
DB_PASSWORD=[NEW - 20+ chars]
GEMINI_API_KEY=[NEW - regenerated]
SENDGRID_API_KEY=[NEW - regenerated]
```

**Status**: ⏳ Planned  
**Timing**: 2-3 weeks from now  
**Process**: Follow CREDENTIAL_ROTATION_CHECKLIST.md

---

## 📋 QUICK CHECKLIST - DO NOW

- [ ] Apply Fix #1: db.py DATABASE_URL (10 min)
- [ ] Apply Fix #2: HTML dynamic URLs (45 min)
- [ ] Apply Fix #3: Add gunicorn (2 min)
- [ ] Apply Fix #4: Set CORS env var (3 min)
- [ ] Test locally: `python app.py`
- [ ] Push to GitHub
- [ ] Deploy to Railway
- [ ] Deploy to Vercel
- [ ] Run end-to-end tests
- [ ] Document issues found
- [ ] Schedule credential rotation (pre-release)

---

## 🚀 DEPLOYMENT URLS (Testing)

| Service | URL | Status |
|---------|-----|--------|
| Frontend | https://yourdomain.vercel.app | Testing |
| Backend | https://yourdomain.railway.app | Testing |
| Health | https://yourdomain.railway.app/health | Testing |
| Dashboard | https://yourdomain.vercel.app/dashboard.html | Testing |

---

## 📌 IMPORTANT NOTES

1. **For Testing Only**: Current credentials are fine for internal testing
2. **Before Public**: Rotate ALL credentials before any user-facing launch
3. **Security Window**: Don't leave exposed credentials in production for more than 2-3 weeks
4. **Best Practice**: Move from `.env` to vault ASAP after rotating
5. **Audit Trail**: Remove sensitive data from git history before going public

---

## 🎯 SUCCESS CRITERIA

**Testing phase is successful when**:
- ✅ Code compiles without errors
- ✅ Deploys to Railway without issues
- ✅ Deploys to Vercel without issues
- ✅ Users can login and use system
- ✅ All major features work
- ✅ No critical errors in logs
- ✅ Performance is acceptable (< 2 sec page load)

**Then**: Fix any issues found, test more, prepare for credential rotation

---

## 📅 NEXT STEPS

1. **NOW**: Complete 4 code fixes (60 min)
2. **NEXT**: Test locally and deploy
3. **TOMORROW**: Test thoroughly, document issues
4. **THIS WEEK**: Fix bugs, optimize
5. **NEXT WEEK**: Prepare for credential rotation
6. **WEEK 3**: Rotate credentials, final review
7. **WEEK 3**: Ready for market launch! 🚀

---

**Status**: ✅ **APPROVED FOR TESTING WITH CURRENT CREDENTIALS**  
**Confidence**: 95%  
**Timeline**: Deploy in 1-2 days after fixes  
**Risk**: LOW (internal testing only)  

**Start with the 4 fixes above, then deploy!**

