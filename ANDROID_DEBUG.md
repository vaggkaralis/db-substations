# Android App Debugging Guide

## 📱 How to View Android App Logs

The app now includes comprehensive logging to help diagnose crashes. Here's how to view the logs:

### Method 1: Using ADB (Android Debug Bridge) - RECOMMENDED

**Prerequisites:**
1. Enable Developer Options on your Android phone:
   - Go to Settings → About Phone
   - Tap "Build Number" 7 times
   - Developer Options will appear in Settings

2. Enable USB Debugging:
   - Settings → Developer Options
   - Enable "USB Debugging"

3. Install ADB on your computer:
   - Download Android Platform Tools: https://developer.android.com/studio/releases/platform-tools
   - Extract the ZIP file
   - No admin rights needed!

**View Live Logs:**
```powershell
# Navigate to platform-tools folder
cd C:\path\to\platform-tools

# Connect phone via USB and run:
.\adb.exe logcat | Select-String "APP:"

# OR filter for Python/Kivy logs:
.\adb.exe logcat | Select-String "python|kivy|APP:"
```

**View Crash Logs:**
```powershell
# Clear old logs first
.\adb.exe logcat -c

# Install and launch the app
# When it crashes, immediately run:
.\adb.exe logcat -d > crash_log.txt

# View the file - look for lines with "APP:", "FATAL", "ERROR"
```

### Method 2: Using Android Studio (if available)

1. Download Android Studio (free): https://developer.android.com/studio
2. Open Android Studio → Bottom toolbar → Logcat
3. Connect phone via USB
4. Filter by "APP:" or "python"
5. Launch the app and watch logs in real-time

### Method 3: Device Log Apps (No Computer Needed)

Install a log viewer app from Play Store:
- **Logcat Reader** (free, no root)
- **aLogcat** (free)
- **Logcat Extreme** (free trial)

Launch the log viewer BEFORE launching DB Substations app, then filter by "APP:" or "python".

---

## 🔍 What to Look For in Logs

The app logs important checkpoints:

### Startup Sequence:
```
APP: ========== Starting DB Substations App ==========
APP: Python version: 3.x.x
APP: Kivy version: 2.0.0
APP: Kivy UI imports successful
APP: UrlRequest import successful
APP: JSON import successful
APP: SSL module available: OpenSSL x.x.x
APP: Certifi available at: /path/to/certs
APP: urllib3 version: x.x.x
APP: All imports completed successfully
APP: Initializing SubstationAndroidApp
APP: SubstationAndroidApp initialized successfully
APP: Building UI
APP: Header added
APP: Content layout added
APP: Buttons added
APP: About to load substations
APP: UI build completed successfully
```

### If App Crashes During Imports:
Look for:
```
APP: FATAL - Import error: [specific module]
APP: Traceback: [detailed error]
```

### Normal/Ignorable Messages:
```
GetBestInfo: /data/app/.../base.apk has no usable artifacts
```
**What it means:** Android's profiling system can't find debug symbols. This is normal for release builds and can be safely ignored. It's not an error - just informational logging from Android's debugging infrastructure.

Common issues:
- `ModuleNotFoundError: No module named 'certifi'` → Missing SSL dependencies
- `ImportError: cannot import name 'UrlRequest'` → Kivy installation issue
- `SSL: CERTIFICATE_VERIFY_FAILED` → SSL certificates not found

### If App Crashes After Launch:
Look for:
```
APP: Error in build(): [error message]
APP: Traceback: [detailed error]
```

OR:
```
APP: Error in load_substations: [error message]
APP: Connection error: [network issue]
```

---

## 📋 Reporting Crash Information

When reporting crashes, please provide:

1. **Log excerpt** - Copy/paste lines starting with "APP:" especially around the crash
2. **Android version** - Settings → About Phone → Android version
3. **Device model** - Settings → About Phone → Model
4. **Installation method** - From GitHub Actions artifact
5. **Network status** - WiFi or Mobile Data when crash occurred

**Example useful log:**
```
APP: ========== Starting DB Substations App ==========
APP: Python version: 3.10.6
APP: Kivy version: 2.0.0
APP: SSL module available: OpenSSL 1.1.1
APP: Certifi available at: /data/data/org.test.dbsubstations/files/app/_python_bundle/site-packages/certifi/cacert.pem
APP: All imports completed successfully
APP: Initializing SubstationAndroidApp
APP: SubstationAndroidApp initialized successfully
APP: Building UI
[... more logs ...]
APP: FATAL ERROR in main: Connection refused
APP: Traceback: urllib.error.URLError: <urlopen error [Errno 111] Connection refused>
```

---

## 🛠️ Quick ADB Setup (No Admin Rights)

1. **Download Android SDK Platform Tools**:
   - https://dl.google.com/android/repository/platform-tools-latest-windows.zip
   - Extract to any folder (e.g., `C:\Users\YourName\AndroidTools`)

2. **Connect Phone**:
   - Enable USB Debugging (see above)
   - Connect USB cable
   - Allow USB debugging when prompted on phone

3. **Test Connection**:
   ```powershell
   cd C:\Users\YourName\AndroidTools\platform-tools
   .\adb.exe devices
   ```
   Should show your device listed

4. **View Logs**:
   ```powershell
   .\adb.exe logcat -s "python:* *:E"
   ```
   This shows Python logs and all Errors

---

## 🚀 Next Build

GitHub Actions is building a new APK with logging enabled. Once the build completes (~10-15 minutes):

1. Go to: https://github.com/vaggkaralis/db-substations/actions
2. Click the latest workflow run
3. Download the "db-substations-apk" artifact
4. Extract and install the APK
5. Set up ADB (above)
6. Launch app while viewing logs
7. Share the logs if it crashes

The logs will show EXACTLY where and why the crash occurs!
