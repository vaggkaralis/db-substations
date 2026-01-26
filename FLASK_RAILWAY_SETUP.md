# Flask to Railway Deployment - Step by Step

## Step 1: Setup Git Repository (5 minutes)

If you don't have Git installed, download from https://git-scm.com/

### In PowerShell, navigate to your project folder:
```powershell
cd "C:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations"
```

### Initialize Git repository:
```powershell
git init
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

### Create `.gitignore` to exclude unnecessary files:
```powershell
@"
.venv/
__pycache__/
*.pyc
*.db
firebase-credentials.json
.env
.DS_Store
"@ | Out-File -Encoding UTF8 .gitignore
```

### Add all files and commit:
```powershell
git add .
git commit -m "Initial commit: DB Substations with Flask API"
```

### Check git status:
```powershell
git status
```

---

## Step 2: Create GitHub Repository (5 minutes)

1. Go to https://github.com/new
2. Create account if needed (or sign in)
3. **Repository name**: `db-substations`
4. **Description**: DB Substations Management System
5. **Public** (so Railway can access it)
6. Click **Create Repository**
7. Copy the repository URL (looks like `https://github.com/YOUR_USERNAME/db-substations.git`)

### Push code to GitHub:
```powershell
git remote add origin https://github.com/YOUR_USERNAME/db-substations.git
git branch -M main
git push -u origin main
```

**Note**: You'll be prompted for authentication. GitHub now requires personal access tokens (not passwords):
- Go to https://github.com/settings/tokens
- Click "Generate new token"
- Give it `repo` permission
- Copy token and paste when prompted

---

## Step 3: Deploy to Railway (10 minutes)

### 1. Create Railway Account
- Go to https://railway.app
- Click **Login** > **Sign up with GitHub**
- Authorize Railway to access your GitHub

### 2. Create New Project
- Click **New Project**
- Select **Deploy from GitHub repo**
- Search for `db-substations` repository
- Click to select it
- Railway will start deploying automatically

### 3. Set Environment Variables
While Railway deploys, add environment variables:

1. Click on your project name
2. Go to **Settings** tab
3. Add variables:
   ```
   FLASK_ENV=production
   FLASK_HOST=0.0.0.0
   FLASK_PORT=8000
   DATABASE_PATH=/var/data/database.db
   ```

### 4. Wait for Deployment
- Railway builds and deploys (takes 2-5 minutes)
- You'll see logs in the **Deploy** tab
- Status will show "Success" when done

### 5. Get Your Public URL
- Go to **Deployments** tab
- Click on successful deployment
- Look for **Public URL** (e.g., `https://db-substations-production.up.railway.app`)
- **Save this URL!**

---

## Step 4: Verify Flask Server is Running (2 minutes)

Test the health endpoint in your browser or PowerShell:

```powershell
# Replace with your Railway URL
$railwayUrl = "https://YOUR_RAILWAY_URL.up.railway.app"

# Test health check
Invoke-WebRequest "$railwayUrl/api/health" | Select-Object StatusCode, Content
```

Expected output:
```
StatusCode Content
----------- -------
200        {"success":true,"status":"Server is running"}
```

---

## Step 5: Test API Endpoints

### Get all substations:
```powershell
$railwayUrl = "https://YOUR_RAILWAY_URL.up.railway.app"
Invoke-WebRequest "$railwayUrl/api/substations" | Select-Object Content
```

Should return:
```json
{"success":true,"data":[]}
```

### Add a test substation:
```powershell
$body = @{
    name = "Test Substation"
    location = "Athens"
    adoption_date = "2024-01-01"
} | ConvertTo-Json

Invoke-WebRequest -Uri "$railwayUrl/api/substations" `
    -Method POST `
    -Headers @{"Content-Type"="application/json"} `
    -Body $body | Select-Object Content
```

---

## Step 6: Update Android App to Use Cloud Server

Edit `android_app.py` and change the API URL:

```python
# OLD (line ~21):
API_BASE_URL = 'http://192.168.1.100:5000/api'

# NEW:
API_BASE_URL = 'https://YOUR_RAILWAY_URL.up.railway.app/api'
```

Replace `YOUR_RAILWAY_URL` with your actual Railway URL.

---

## Step 7: Build Android APK with Cloud URL

### On Linux/WSL:
```bash
# Navigate to project
cd "DB Substations"

# Update buildozer.spec to use android_app.py
# Edit: source.main = org.dbsubstations.MainActivity

# Build debug APK
buildozer android debug

# APK location: bin/dbsubstations-1.0-debug.apk
```

### Install on Android device:
```bash
adb install -r bin/dbsubstations-1.0-debug.apk
```

---

## Step 8: Test on Android Device

1. **Open the app** on your Android phone
2. **Enable mobile data** (turn off WiFi to test fully)
3. **Click Refresh** button
4. Should load substations from cloud server
5. **Add a new substation** - should sync to cloud
6. **Go back** and refresh - should see new item

---

## Troubleshooting

### "Failed to connect"
```bash
# Check Railway logs
# 1. Go to Railway dashboard
# 2. Click your project
# 3. Go to Deployments > Logs
# 4. Look for errors

# Test API directly
curl https://YOUR_RAILWAY_URL.up.railway.app/api/health
```

### "502 Bad Gateway"
- Server may still be starting (Railway takes 1-2 min)
- Check Deployments > Logs for startup errors
- Common causes: Missing environment variables, Python errors

### Database Not Found
- Check `DATABASE_PATH` environment variable is set
- Railway uses `/var/data` for persistent storage
- Ensure Flask has permission to create directory

### Android App Still Says "Cannot connect"
```
1. Check WiFi/mobile data is ON
2. Verify API_BASE_URL uses full HTTPS URL
3. Ensure app rebuilt with new URL
4. Check firewall isn't blocking traffic
5. Try opening URL in mobile browser to test
```

---

## Next Steps

### ✅ Completed
- [x] Git setup
- [x] GitHub repository
- [x] Railway deployment
- [x] Android app updated

### 📝 Maintenance
- Monitor Railway logs regularly
- Keep code updated in GitHub (git push)
- Check database usage in Railway dashboard
- Railway will auto-redeploy on git push

### 💡 Optional Enhancements
- Add custom domain (Railway allows this)
- Setup automated backups
- Add user authentication
- Add more features to Windows app
- Monitor API performance

---

## Important Notes

### Database Persistence
- Railway stores persistent data in `/var/data/`
- Database survives app restarts
- But Railway accounts may reset if inactive (paid plan recommended)

### Free Tier Limits
- 5GB storage included
- Limited monthly usage credits
- Paid plan ($5/month) includes:
  - Unlimited projects
  - Better uptime guarantee
  - Priority support

### Security
- HTTPS (encrypted) by default ✅
- CORS enabled for Android access ✅
- No authentication (optional: add later)

---

## Commands Cheat Sheet

```powershell
# Push code changes to GitHub/Railway
git add .
git commit -m "Your message"
git push

# Check git status
git status

# View git log
git log --oneline
```

Once deployed, updates are automatic:
- Push to GitHub → Railway auto-deploys → Android app connects automatically
