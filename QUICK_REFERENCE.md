# DB Substations - Quick Reference

## Files Overview

### Core Application Files
- **`DBrun.py`** - Windows desktop app (Kivy)
- **`android_app.py`** - Android app (connects to Flask API)
- **`android_firebase_app.py`** - Android app (Firebase version - for mobile data)
- **`api_server.py`** - Flask backend server (REST API)
- **`database.py`** - SQLite database setup

### Deployment Files
- **`Procfile`** - Cloud platform deployment config
- **`Pipfile`** - Python dependencies (pipenv)
- **`requirements.txt`** - Python dependencies (pip)
- **`requirements-prod.txt`** - Production dependencies
- **`buildozer.spec`** - Android APK build config
- **`railway.toml`** - Railway.app deployment config

### Documentation
- **`README.md`** - Main documentation
- **`ANDROID_SETUP.md`** - Android WiFi setup (local)
- **`CLOUD_DEPLOYMENT.md`** - Cloud deployment guide

---

## Quick Start Commands

### Windows App
```powershell
# Run
python DBrun.py

# Or with virtual environment
.\.venv\Scripts\python.exe DBrun.py
```

### Flask API Server (Local)
```powershell
# Run locally
.\.venv\Scripts\python.exe api_server.py

# Server starts at http://localhost:5000
```

### Android App - Firebase Version
```bash
# Install dependencies
pip install firebase-admin kivy

# Run locally (desktop testing)
python android_firebase_app.py

# Build APK (requires buildozer)
buildozer android debug
```

### Android App - REST API Version
```bash
# Update API_BASE_URL first in android_app.py
# Then build APK
buildozer android debug
```

---

## Deployment Options Comparison

| Feature | Firebase | Flask Local | Flask Cloud |
|---------|----------|-------------|-------------|
| **Mobile Data** | ✅ Yes | ❌ WiFi only | ✅ Yes |
| **Setup Time** | 30 min | 5 min | 20 min |
| **Cost** | Free-$1/mo | Free | $5-15/mo |
| **Maintenance** | None | None | Low |
| **Real-time Sync** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Server Scaling** | Auto | Manual | Auto |
| **Database Type** | NoSQL | SQLite | SQLite/SQL |

---

## Environment Variables

### Flask Server
```bash
# Development
FLASK_ENV=development
DATABASE_PATH=database.db
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Production
FLASK_ENV=production
DATABASE_PATH=/data/database.db
FLASK_HOST=0.0.0.0
FLASK_PORT=8000
```

### Firebase Credentials
```bash
# Path to firebase-credentials.json
firebase-credentials.json  # Keep SECRET!
```

---

## Testing Checklist

### Windows App
- [ ] Run DBrun.py
- [ ] View database
- [ ] Add substation
- [ ] Add element
- [ ] Delete item
- [ ] Edit substation
- [ ] Import from Excel
- [ ] Export template

### Android App (Firebase)
- [ ] Install APK on device
- [ ] Check internet connection (WiFi or mobile data)
- [ ] View all substations
- [ ] View elements per substation
- [ ] Add new substation
- [ ] Add new element
- [ ] Delete substation
- [ ] Delete element
- [ ] Refresh data
- [ ] Test with mobile data (no WiFi)

### API Server
- [ ] Start server: `python api_server.py`
- [ ] Health check: `curl http://localhost:5000/api/health`
- [ ] List substations: `curl http://localhost:5000/api/substations`
- [ ] List elements: `curl http://localhost:5000/api/elements`

---

## Troubleshooting

### "No module named 'flask'"
```bash
pip install -r requirements.txt
# Or use virtual environment:
.\.venv\Scripts\pip.exe install flask
```

### Android App Can't Connect
```bash
# Check API_BASE_URL in android_app.py
# Check PC IP: ipconfig (Windows) or hostname -I (Linux)
# Ensure firewall allows port 5000
# Test: curl http://<PC_IP>:5000/api/health
```

### Firebase Connection Error
```bash
# Check internet connection
# Check firebase-credentials.json exists
# Verify database URL in code
# Check Firebase Console for errors
```

### APK Build Fails
```bash
# Clear cache
buildozer android clean

# Check buildozer.spec
# Ensure all paths are correct
# Try debug mode for more info
buildozer android debug -- log_level debug
```

---

## Project Structure
```
DB Substations/
├── DBrun.py                    # Windows app
├── android_app.py              # Android app (REST)
├── android_firebase_app.py     # Android app (Firebase)
├── api_server.py               # Flask server
├── database.py                 # DB init
├── importers.py                # Import logic
├── popups.py                   # UI popups
├── templates.py                # Export templates
├── Procfile                    # Cloud config
├── requirements.txt            # Dependencies
├── buildozer.spec              # Android build
├── railway.toml                # Railway config
├── README.md                   # Main docs
├── ANDROID_SETUP.md            # Android WiFi setup
├── CLOUD_DEPLOYMENT.md         # Cloud deployment
├── database.db                 # SQLite (local)
├── firebase-credentials.json   # Firebase key (SECRET!)
└── .venv/                      # Virtual environment
```

---

## Next Steps (Recommended Order)

1. **Test Windows app locally** ✓
2. **Test Flask API locally**
3. **Choose deployment** (Firebase or Cloud)
4. **Setup Firebase or Cloud**
5. **Build and test Android APK**
6. **Deploy to production**

---

## Support Resources

- **Kivy Docs**: https://kivy.org/doc/stable/
- **Flask Docs**: https://flask.palletsprojects.com/
- **Firebase Docs**: https://firebase.google.com/docs
- **Railway Docs**: https://docs.railway.app/
- **PythonAnywhere Help**: https://help.pythonanywhere.com/
