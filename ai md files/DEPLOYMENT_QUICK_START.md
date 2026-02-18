# ✅ DEPLOYMENT QUICK START

## Step 1: Push to GitHub (2 min)
```powershell
cd "c:\Users\DIANNA\Documents\AI proj"
git add .
git commit -m "Deployment ready: Add gunicorn and Render DATABASE_URL support"
git push origin main
```

## Step 2: Deploy Backend to Render (15 min)

**1. Create Render Account** → https://render.com
- Sign up with GitHub
- Authorize repository access

**2. Create New Web Service**
- Click "New +" → "Web Service"
- Connect your GitHub repository
- Select **emiliokamau/AI**
- Choose the repository

**3. Configure Web Service**
- **Name**: medical-ai-backend (or your choice)
- **Environment**: Python 3.11
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app`
- **Plan**: Free (or paid for production)

**4. Add PostgreSQL Database**
- Click "New +" → "PostgreSQL"
- Name it: `medical-ai-db`
- Render auto-creates DATABASE_URL
- Connect it to your Web Service

**5. Set Environment Variables**
- In Web Service settings: Environment
- Add these variables:

```
FLASK_ENV=production
CORS_ORIGINS=http://localhost:5000,https://yourdomain.vercel.app
GEMINI_API_KEY=[REDACTED]
SENDGRID_API_KEY=[your key]
SENDGRID_FROM_EMAIL=emiliokamau35@gmail.com
```

*Note: DATABASE_URL is auto-provided by PostgreSQL instance*

**6. Deploy**
- Render auto-deploys from GitHub
- Watch deployment logs
- Once successful, you get URL: `https://medical-ai-backend.onrender.com`
- Copy this URL for next step

---

## Step 3: Deploy Frontend to Vercel (10 min)

**1. Create Vercel Account** → https://vercel.com
- Sign up with GitHub
- Authorize repository access

**2. Import Project**
- Click "New Project"
- Select **emiliokamau/AI**
- Click "Import"

**3. Configure Settings**
- Framework: Other
- Root Directory: ./
- Leave Build/Output empty

**4. Add Environment Variable**
```
NEXT_PUBLIC_BACKEND_URL=[Your Render URL from Step 2]
```

**5. Deploy**
- Click "Deploy"
- You'll get URL: `https://yourapp.vercel.app`

---

## Step 4: Update CORS for Production

Once Vercel is live:

1. Go back to Render Web Service
2. Environment variables
3. Update `CORS_ORIGINS`:
```
http://localhost:5000,https://yourapp.vercel.app
```
4. Render auto-redeploys in ~1 minute

---

## Step 5: Test Everything

**Test Backend:**
```bash
curl https://medical-ai-backend.onrender.com/health
```

**Test Frontend:**
1. Visit https://yourapp.vercel.app
2. Open DevTools (F12) → Network tab
3. Test login, chat, appointments
4. Verify no CORS errors

---

## ✅ Final Checklist

- [ ] Code pushed to GitHub (main branch)
- [ ] Render account created with GitHub
- [ ] PostgreSQL database created in Render
- [ ] All environment variables set in Render
- [ ] Backend deployed and running
- [ ] Vercel project created
- [ ] Frontend deployed
- [ ] CORS updated for production domain
- [ ] Successfully logged in from frontend
- [ ] Chat with AI works
- [ ] All major features tested

---

## 📞 Need Help?

**Render Logs**: Web Service → Logs tab  
**Vercel Logs**: Project → Deployments → View deployment logs  
**DevTools**: F12 → Network/Console to debug CORS or API errors

**Render Docs**: https://render.com/docs  
**Vercel Docs**: https://vercel.com/docs

---

## 🎉 You're Done!

Your app is now live in production for testing! 🚀

Current status: ✅ **DEPLOYMENT READY (Render + Vercel)**
