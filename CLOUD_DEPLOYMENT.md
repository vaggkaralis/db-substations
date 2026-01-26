# DB Substations - Cloud Deployment Guide

## Option 1: Firebase Realtime Database (Recommended for Mobile)

### Why Firebase?
- ✅ Works worldwide with internet (no WiFi needed)
- ✅ Real-time sync across all devices
- ✅ No server to maintain
- ✅ Free tier sufficient for small apps
- ✅ Works with mobile data

### Setup Steps

#### 1. Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add Project"
3. Name it "DB Substations"
4. Accept defaults, click "Create Project"
5. Wait for project setup to complete

#### 2. Create Realtime Database
1. In Firebase Console, go to **Realtime Database**
2. Click **Create Database**
3. Choose region closest to you (e.g., `europe-west1` for EU)
4. Start in **Test mode** (for development)
5. Click **Enable**
6. Note your database URL: `https://YOUR_PROJECT.firebaseio.com`

#### 3. Setup Authentication (Optional but Recommended)
1. Go to **Authentication** > **Sign-in method**
2. Enable **Anonymous** authentication
3. Click **Save**

#### 4. Get Credentials for Android App
1. Go to **Project Settings** (gear icon)
2. Click **Service Accounts** tab
3. Click **Generate New Private Key**
4. Save as `firebase-credentials.json` in project folder
5. Keep this file SECRET - don't commit to git!

#### 5. Update Android App
Edit `android_firebase_app.py`:

```python
# Line ~67 - Update database URL
firebase_admin.initialize_app(
    cred,
    {
        'databaseURL': 'https://YOUR_PROJECT.firebaseio.com'  # ← CHANGE THIS
    }
)
```

Also update `buildozer.spec`:
```ini
[app]
title = DB Substations
package.name = dbsubstations
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json
requirements = python3,kivy,firebase-admin,pyjnius

permissions = INTERNET,ACCESS_NETWORK_STATE
```

#### 6. Build & Deploy APK
```bash
# Install buildozer (on Linux/WSL)
pip install buildozer cython

# Navigate to project
cd "DB Substations"

# Build debug APK
buildozer android debug

# APK will be in: bin/dbsubstations-1.0-debug.apk
```

#### 7. Install on Android Device
```bash
# Using ADB (Android Debug Bridge)
adb install bin/dbsubstations-1.0-debug.apk
```

### Firebase Data Structure
```
/
├── substations
│   ├── uuid1
│   │   ├── name: "Substation A"
│   │   ├── location: "Athens"
│   │   ├── adoption_date: "2024-01-01"
│   │   └── created_at: "2024-01-15T10:30:00"
│   └── uuid2
│       └── ...
└── elements
    ├── uuid1
    │   ├── substation_id: "uuid1"
    │   ├── element_type: "Διακόπτης Ισχύος"
    │   ├── name: "Element 1"
    │   ├── serial_number: "SN123"
    │   ├── maintenance_date: "2024-01-15"
    │   ├── voltage_level: "20 KV"
    │   ├── manufacturer: "Siemens"
    │   ├── type: "Type A"
    │   └── created_at: "2024-01-15T10:30:00"
    └── uuid2
        └── ...
```

### Firebase Security Rules (for Production)
Replace test rules in Firebase Console with:

```json
{
  "rules": {
    "substations": {
      ".read": true,
      ".write": true,
      ".indexOn": ["created_at"]
    },
    "elements": {
      ".read": true,
      ".write": true,
      ".indexOn": ["substation_id", "created_at"]
    }
  }
}
```

### Cost Estimate
- **Free Tier**: Up to 100 simultaneous connections, 1GB storage
- **Pay-as-you-go**: ~$0.06 per 100k read operations
- For small teams: Usually free or <$1/month

---

## Option 2: Cloud Flask Server (More Control)

### Why Flask on Cloud?
- ✅ Keeps current Windows/Android-REST architecture
- ✅ Works worldwide with internet
- ✅ More control over database
- ✅ Can add features easily
- ❌ Requires server maintenance
- ❌ Small monthly cost

### Deployment Platforms

#### A. Railway (Recommended - Easiest)
[Railway.app](https://railway.app)

**Pros:**
- Simple deployment
- $5/month free credits
- Good for Flask apps

**Steps:**
1. Create GitHub account and push code there:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/db-substations.git
git push -u origin main
```

2. Go to [Railway.app](https://railway.app)
3. Click "New Project" > "Deploy from GitHub"
4. Select your repository
5. Railway auto-detects Flask and deploys
6. Get your public URL (e.g., `https://db-substations.railway.app`)

**Environment Variables to set in Railway:**
```
FLASK_ENV=production
DATABASE_PATH=/data/database.db
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

#### B. PythonAnywhere
[PythonAnywhere.com](https://www.pythonanywhere.com)

**Pros:**
- Python-focused
- Simple web-based setup
- Free tier available

**Steps:**
1. Create account
2. Upload files via web interface
3. Create WSGI config file
4. Point custom domain (if needed)
5. Reload app
6. Get URL: `https://YOUR_USERNAME.pythonanywhere.com`

#### C. Heroku (Paid)
Note: Free tier discontinued, now ~$7/month minimum

#### D. Self-hosted VPS
DigitalOcean, AWS Lightsail (~$5-10/month)

### Prepare Flask for Cloud Deployment

**1. Create `Procfile` (for Railway/Heroku):**
```
web: python api_server.py
```

**2. Create `requirements-prod.txt`:**
```
flask==2.0.0
flask-cors==3.0.0
gunicorn==20.1.0
```

**3. Ensure database persistence:**
```python
# Already handled in updated api_server.py
# Uses DATABASE_PATH environment variable
```

### Update Windows/Android Apps to Use Cloud Server

Edit `api_server.py` in windows app or update the Android app:
```python
# OLD (local):
API_BASE_URL = 'http://localhost:5000/api'

# NEW (cloud):
API_BASE_URL = 'https://db-substations.railway.app/api'
```

---

## Hybrid Approach: Windows + Firebase, Android + Firebase

**Recommended Setup:**
- **Android**: Uses Firebase (mobile data compatible) - `android_firebase_app.py`
- **Windows**: Can keep using local DB or optional cloud sync
- **Benefits**: No server costs, all devices sync automatically

---

## Migration Checklist

### Firebase Migration
- [ ] Create Firebase project
- [ ] Create Realtime Database
- [ ] Download credentials JSON
- [ ] Update `android_firebase_app.py` with database URL
- [ ] Add permissions to `buildozer.spec`
- [ ] Test locally: `python android_firebase_app.py`
- [ ] Build APK: `buildozer android debug`
- [ ] Install on device: `adb install bin/...apk`
- [ ] Test add/view/delete operations

### Flask Cloud Migration
- [ ] Push code to GitHub
- [ ] Create account on Railway/PythonAnywhere
- [ ] Deploy Flask app
- [ ] Get public URL
- [ ] Update Android app with cloud URL
- [ ] Test connectivity
- [ ] Monitor server logs

---

## Troubleshooting

### Firebase App Won't Connect
```bash
# Check credentials file exists
ls firebase-credentials.json

# Check internet connection
ping firebase.google.com

# Check database URL in code
grep databaseURL android_firebase_app.py
```

### Flask Cloud Server Errors
```bash
# Check logs on Railway
# Dashboard > Logs tab

# Test API locally
curl http://localhost:5000/api/health

# Test from cloud
curl https://db-substations.railway.app/api/health
```

### Database Lock Issues
- Firebase: Automatic, no lock issues
- Flask: If using SQLite on shared hosting, may need migration to PostgreSQL

---

## Next Steps

1. **Choose deployment method** (Firebase or Flask Cloud)
2. **Follow setup steps** above
3. **Test thoroughly** before production
4. **Monitor usage** and costs
5. **Plan for scaling** if needed
