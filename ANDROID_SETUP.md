# DB Substations - Multi-Platform Setup Guide

## Overview
This project now consists of:
1. **Flask API Server** - Shared backend for database operations
2. **Windows Desktop App** - Rich desktop interface with import/export
3. **Android Mobile App** - Mobile access to database

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│           Flask API Server (api_server.py)              │
│              SQLite Database (database.db)              │
└─────────────────────────────────────────────────────────┘
           ▲                              ▲
           │ HTTP                        │ HTTP
           │                             │
    ┌──────┴────┐              ┌────────┴──────┐
    │  Windows  │              │    Android    │
    │   App     │              │     App       │
    │(DBrun.py) │              │(android_app.py)
    └───────────┘              └───────────────┘
```

## Setup Instructions

### 1. API Server Setup

#### Prerequisites
- Python 3.8+
- Flask
- Flask-CORS

#### Installation
```bash
pip install flask flask-cors
```

#### Running the Server
```bash
python api_server.py
```

The server will start on `http://localhost:5000` (or your machine IP:5000 for network access).

**Important**: Change the API_BASE_URL in android_app.py to your server's IP address:
```python
API_BASE_URL = 'http://YOUR_MACHINE_IP:5000/api'
```

### 2. Windows App Setup

The Windows app (`DBrun.py`) will be updated to optionally use the API server (future enhancement).
For now, it continues to work with local SQLite database.

#### Running
```bash
python DBrun.py
```

### 3. Android App Setup

#### Prerequisites
- Ubuntu/Linux or Windows with WSL
- Java Development Kit (JDK 11+)
- Android NDK
- Buildozer

#### Installation (Linux/WSL)
```bash
pip install buildozer cython virtualenv
# Install Android SDK/NDK (Buildozer will prompt you)
```

#### Building APK
```bash
# Navigate to project directory
cd "path/to/DB Substations"

# Update API_BASE_URL in android_app.py first!

# Build debug APK
buildozer android debug

# Or release APK (requires keystore)
buildozer android release
```

The APK will be generated in `bin/dbsubstations-1.0-debug.apk`

#### Installation on Device
```bash
# Via ADB (requires Android Debug Bridge)
adb install bin/dbsubstations-1.0-debug.apk

# Or manually transfer APK and install
```

### 4. Network Configuration

For Android app to communicate with API server:

1. **Same Network**: Both device and PC must be on same WiFi
2. **Get Server IP**:
   - Windows: Run `ipconfig` in cmd, look for "IPv4 Address"
   - Linux: Run `hostname -I`
3. **Update Android App**:
   - Edit `android_app.py` line with `API_BASE_URL`
   - Set to `http://<YOUR_PC_IP>:5000/api`
4. **Rebuild APK** after changing IP

### 5. Database Sync

All three applications connect to the same Flask API server which manages the single SQLite database. This ensures:
- Real-time sync across platforms
- No duplicate data issues
- Single source of truth

#### Initial Setup
1. Start Flask server
2. Run Windows app (creates/uses local database)
3. Android app auto-syncs from server

## API Endpoints Reference

### Substations
- `GET /api/substations` - List all substations
- `POST /api/substations` - Add new substation
- `PUT /api/substations/<id>` - Update substation
- `DELETE /api/substations/<id>` - Delete substation

### Elements
- `GET /api/elements` - List all elements
- `GET /api/elements?substation_id=<id>` - Elements for specific substation
- `POST /api/elements` - Add new element
- `DELETE /api/elements/<id>` - Delete element

### Health
- `GET /api/health` - Check server status

## Feature Availability by Platform

### Windows App
- ✅ View database
- ✅ Add substations manually
- ✅ Add elements manually
- ✅ Edit substations
- ✅ Delete substations/elements
- ✅ Import from Excel/CSV
- ✅ Export templates
- ✅ Per-duplicate conflict resolution

### Android App
- ✅ View database (read-only initially)
- ✅ Add substations manually
- ✅ Add elements manually
- ✅ Delete substations/elements
- ❌ Import functionality (v1)
- ❌ Edit operations (v2 planned)

## Troubleshooting

### Android App Can't Connect to Server
1. Check both devices on same WiFi
2. Check firewall allows port 5000
3. Verify API_BASE_URL is correct
4. Test with: `curl http://<SERVER_IP>:5000/api/health`

### buildozer build fails
1. Ensure all prerequisites installed
2. Clear build: `buildozer android clean`
3. Check buildozer.spec has correct paths
4. For detailed logs: `buildozer android debug -- log_level debug`

### Database Lock Issues
- Only one app can write to local database at a time
- API server serializes requests automatically
- If issues persist, restart Flask server

## Future Enhancements
- [ ] Cloud database (PostgreSQL/Firebase)
- [ ] Offline mode with sync
- [ ] User authentication
- [ ] Data export from Android
- [ ] Android edit capabilities
- [ ] Push notifications
- [ ] Dark mode
