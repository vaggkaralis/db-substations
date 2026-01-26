# Flask + Railway Deployment Summary

## 🎯 Goal
Deploy Flask API server to Railway so Android app can access database anywhere with internet (WiFi or mobile data).

## 📋 Before You Start
- [ ] Git installed on Windows
- [ ] GitHub account created
- [ ] Railway account created (sign up with GitHub)
- [ ] Flask dependencies installed (already done)

## 🚀 Quick Start (Choose One)

### Option A: Automated (Easiest)
```powershell
# 1. Setup Git
cd "C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations"
git init
git add .
git commit -m "DB Substations with Flask API"

# 2. Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/db-substations.git
git push -u origin main

# 3. Go to Railway.app and:
#    - Click "New Project"
#    - Select "Deploy from GitHub"
#    - Choose db-substations repo
#    - Railway handles everything!
```

### Option B: Step by Step
See `FLASK_RAILWAY_SETUP.md` for detailed instructions

## 📊 What Gets Deployed

Your Flask server with these endpoints:
- `GET /api/health` - Check if server is running
- `GET /api/substations` - List all substations
- `POST /api/substations` - Add substation
- `PUT /api/substations/<id>` - Update substation
- `DELETE /api/substations/<id>` - Delete substation
- `GET /api/elements` - List all elements
- `POST /api/elements` - Add element
- `DELETE /api/elements/<id>` - Delete element

## 🔑 Environment Variables (Set in Railway Dashboard)
```
FLASK_ENV=production
DATABASE_PATH=/var/data/database.db
FLASK_HOST=0.0.0.0
FLASK_PORT=8000
```

## ✅ After Deployment

1. **Get Your URL**
   - Railway gives you: `https://YOUR_PROJECT-production.up.railway.app`
   - Save this URL!

2. **Test the Server**
   ```powershell
   curl "https://YOUR_PROJECT-production.up.railway.app/api/health"
   ```

3. **Update Android App**
   - Edit `android_app.py`
   - Change: `API_BASE_URL = 'https://YOUR_PROJECT-production.up.railway.app/api'`

4. **Build Android APK**
   ```bash
   buildozer android debug
   # Install: adb install -r bin/dbsubstations-1.0-debug.apk
   ```

5. **Test on Android**
   - Open app with mobile data ON
   - Should load substations from cloud
   - Can add/view/delete items

## 🧪 Testing Locally First

Before deploying to Railway, test Flask locally:

```powershell
# Start Flask server
python api_server.py

# In another PowerShell window, test:
python test_api.py
```

Expected output:
```
✅ Server is healthy
✅ Got 0 substations
✅ Added substation with ID 1
✅ Added element with ID 1
✅ Got 1 elements
```

## 📁 Files Involved

**Deploy to Railway:**
- `api_server.py` - Flask app ✅
- `database.py` - DB init ✅
- `Procfile` - Railway config ✅
- `.gitignore` - What not to upload ✅
- `requirements-prod.txt` - Dependencies ✅

**Update & Rebuild:**
- `android_app.py` - Update API URL
- `buildozer.spec` - Build config
- Rebuild APK with updated URL

## ⚡ Commands Cheat Sheet

```powershell
# Git commands
git status
git add .
git commit -m "message"
git push

# Test locally
python api_server.py
python test_api.py

# View logs
git log --oneline
```

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| "502 Bad Gateway" | Server still starting, wait 1-2 min |
| "Cannot connect" on Android | Check API URL uses HTTPS, not HTTP |
| Database not found | Verify DATABASE_PATH env var set |
| Git push fails | Ensure GitHub auth token set up |
| Flask won't start locally | Run `pip install -r requirements.txt` |

## 💰 Cost
- **Railway Free Tier**: Included
- **Paid Plan**: $5/month (recommended for reliability)
- **Database Size**: Up to 5GB free

## 🔒 Security Notes
- ✅ HTTPS encryption automatic
- ✅ CORS enabled for Android access
- ⚠️ No authentication yet (add in future if needed)
- ⚠️ Keep firebase-credentials.json out of git

## 📞 Support
- Railway docs: https://docs.railway.app/
- Flask docs: https://flask.palletsprojects.com/
- GitHub help: https://docs.github.com/

## 📈 Next Steps
1. Deploy Flask to Railway ✓
2. Build Android APK with cloud URL ✓
3. Test on real device with mobile data ✓
4. Monitor Railway dashboard for issues ✓
5. Optional: Add authentication ✓
6. Optional: Add Windows sync option ✓

---

**Status**: Ready to deploy! 🚀
