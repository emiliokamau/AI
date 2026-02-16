# ✅ DEPLOYMENT QUICK START

## Step 1: Push to GitHub (2 min)
```powershell
cd "c:\Users\DIANNA\Documents\AI proj"
git add .
git commit -m "Deployment ready: Add gunicorn and Railway DATABASE_URL support"
git push origin main
```

## Step 2: Deploy Backend to Railway (15 min)

**1. Create Railway Account** → https://railway.app
- Sign up with GitHub
- Authorize repository access

**2. Create New Project**
- Click "New Project"
- Select "Deploy from GitHub"
- Choose **emiliokamau/AI**
- Click "Confirm deploy"

**3. Add MySQL Database**
- Click "Add"
- Select "MySQL"
- Railway auto-creates and provides DATABASE_URL

**4. Set Environment Variables**
- Project → Settings → Variables
- Add these variables:

```
FLASK_ENV=production
CORS_ORIGINS=http://localhost:5000,https://yourdomain.vercel.app
GEMINI_API_KEY=AIzaSyBmrPjE9kPdR4_g61vQfFUuRUNXAlw5VIQ
SENDGRID_API_KEY=[your key]
SENDGRID_FROM_EMAIL=emiliokamau35@gmail.com
```

**5. Deploy**
- Railway auto-deploys using Procfile
- You'll get public URL: `https://api-production-xxxxx.railway.app`
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
NEXT_PUBLIC_BACKEND_URL=[Your Railway URL from Step 2]
```

**5. Deploy**
- Click "Deploy"
- You'll get URL: `https://yourapp.vercel.app`

---

## Step 4: Update CORS for Production

Once Vercel is live:

1. Go back to Railway
2. Settings → Variables
3. Update `CORS_ORIGINS`:
```
http://localhost:5000,https://yourapp.vercel.app
```
4. Railway auto-redeploys

---

## Step 5: Test Everything

**Test Backend:**
```bash
curl https://api-production-xxxxx.railway.app/health
```

**Test Frontend:**
1. Visit https://yourapp.vercel.app
2. Open DevTools (F12) → Network tab
3. Test login, chat, appointments
4. Verify no CORS errors

---

## ✅ Final Checklist

- [ ] Code pushed to GitHub (main branch)
- [ ] Railway project created with MySQL
- [ ] All environment variables set in Railway
- [ ] Backend deployed and running
- [ ] Vercel project created
- [ ] Frontend deployed
- [ ] CORS updated for production domain
- [ ] Successfully logged in from frontend
- [ ] Chat with AI works
- [ ] All major features tested

---

## 📞 Need Help?

**Railway Logs**: Project → Deployments → View full logs
**Vercel Logs**: Project → Deployments → View deployment logs
**DevTools**: F12 → Network/Console to debug CORS or API errors

---

## 🎉 You're Done!

Your app is now live in production for testing! 🚀

Current status: ✅ **DEPLOYMENT READY**
