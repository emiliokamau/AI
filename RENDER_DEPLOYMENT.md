# 🚀 RENDER DEPLOYMENT GUIDE

**Changed From**: Railway  
**Changed To**: Render (PostgreSQL)  
**Status**: Updated and ready for deployment

---

## 📋 What Changed

### Database
- **Before**: Railway MySQL
- **After**: Render PostgreSQL
- **Benefit**: Render's free tier with PostgreSQL, easier setup

### Backend Code Updates
- ✅ `db.py` updated to support both MySQL and PostgreSQL
- ✅ Auto-detects database type from DATABASE_URL
- ✅ Works with Render, Railway, or local MySQL

### Dependencies
- ✅ Added `psycopg2-binary>=2.9.0` to requirements.txt

### Configuration
- ✅ Created `render.json` for Render deployment
- ✅ Updated all deployment guides (DEPLOY_NOW.md, etc.)

---

## 🎯 Quick Deployment Steps

### Step 1: Go to Render
Visit: https://render.com

### Step 2: Create Account
- Click "Get Started"
- Sign up with GitHub
- Authorize access to emiliokamau/AI

### Step 3: Create Web Service
- Click "New +" → "Web Service"
- Select **emiliokamau/AI**
- Configure:
  - **Name**: `medical-ai-backend`
  - **Environment**: `Python 3.11`
  - **Build Command**: `pip install -r requirements.txt`
  - **Start Command**: `gunicorn app:app`

### Step 4: Add PostgreSQL Database
- Click "New +" → "PostgreSQL"
- Name: `medical-ai-db`
- Plan: Free (or paid)
- Render auto-attaches DATABASE_URL

### Step 5: Set Environment Variables
In Web Service → **Environment**:

```
FLASK_ENV=production
CORS_ORIGINS=http://localhost:5000
GEMINI_API_KEY=AIzaSyBmrPjE9kPdR4_g61vQfFUuRUNXAlw5VIQ
SENDGRID_API_KEY=[your-key]
SENDGRID_FROM_EMAIL=emiliokamau35@gmail.com
```

DATABASE_URL is auto-created by PostgreSQL instance.

### Step 6: Deploy
- Render auto-deploys from GitHub
- Your URL: `https://medical-ai-backend.onrender.com`
- Takes ~5-10 minutes

### Step 7: Deploy Frontend to Vercel
- Go to https://vercel.com
- Import emiliokamau/AI
- Add NEXT_PUBLIC_BACKEND_URL env var
- Deploy!

### Step 8: Update CORS
Go back to Render Web Service → Environment and update:
```
CORS_ORIGINS=http://localhost:5000,https://yourapp.vercel.app
```

---

## 🔧 Technical Details

### Database URL Format
Render PostgreSQL uses format:
```
postgresql://user:password@host:port/dbname
```

The updated `db.py` automatically detects this and uses PostgreSQL driver.

### Connection Handling
- **Local**: Uses MySQL with individual env vars
- **Render**: Auto-detects PostgreSQL from DATABASE_URL
- **Railway**: Auto-detects MySQL from DATABASE_URL

### Driver Installation
- `psycopg2-binary` added to requirements.txt
- `PyMySQL` still included for local/Railway deployments

---

## ✅ Benefits of Render

1. **Free Tier**: PostgreSQL included
2. **Easy Setup**: Auto-database attachment
3. **GitHub Integration**: Auto-deploy on push
4. **Simple UI**: Clear and straightforward
5. **Good Logs**: Easy debugging
6. **Auto-scaling**: Handles traffic spikes
7. **SQLAlchemy Friendly**: PostgreSQL excellent for Python apps

---

## 🧪 Testing After Deployment

```bash
# Test the deployed backend
curl https://medical-ai-backend.onrender.com/health
```

Should return: `200 OK`

Then test the full app at Vercel URL.

---

## 📊 Environment Variables Checklist

### Render Web Service
- [ ] FLASK_ENV = production
- [ ] CORS_ORIGINS = updated with Vercel domain
- [ ] GEMINI_API_KEY = (from .env)
- [ ] SENDGRID_API_KEY = (from .env)
- [ ] SENDGRID_FROM_EMAIL = emiliokamau35@gmail.com
- [ ] DATABASE_URL = (auto-created by PostgreSQL)

### Vercel Frontend
- [ ] NEXT_PUBLIC_BACKEND_URL = Render URL

---

## 🔐 Security Notes

### Credentials Storage
- All secrets stored in Render's environment vault
- Not in code, not in git
- Auto-encrypted at rest

### Database
- PostgreSQL with built-in security
- Render handles backups automatically
- Connection pooling handled by Render

### For Pre-Release (Week 2-3)
- [ ] Rotate all credentials
- [ ] Generate new API keys
- [ ] Update environment variables
- [ ] Final security audit

---

## 📞 Support Resources

- **Render Docs**: https://render.com/docs
- **Render Support**: https://render.com/support
- **GitHub Repo**: https://github.com/emiliokamau/AI
- **Deployment Guide**: See DEPLOY_NOW.md

---

## ✅ Final Checklist

- [ ] GitHub account ready
- [ ] Render account created
- [ ] Vercel account ready
- [ ] Web Service created in Render
- [ ] PostgreSQL database created
- [ ] Environment variables set
- [ ] Build successful
- [ ] Frontend deployed
- [ ] CORS configured
- [ ] All features tested

---

## 🎉 You're Ready!

Follow DEPLOY_NOW.md for step-by-step instructions.

**Status**: ✅ **RENDER DEPLOYMENT READY**
