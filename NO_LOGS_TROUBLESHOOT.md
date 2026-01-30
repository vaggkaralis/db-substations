# No Logs in Logcat - Native Crash Troubleshooting

## Problem
Logcat shows NO logs when filtering by `org.dbsubstations` - this means the app crashes before Python/Kivy initializes.

## Try These Steps in Order

### Step 1: Capture FULL Crash Without Any Filter

```powershell
# Clear logs first
adb logcat -c

# Start capturing EVERYTHING (no filter)
adb logcat > full_native_crash.txt

# NOW: Launch the app
# When it crashes, press Ctrl+C

# Open full_native_crash.txt and search for:
```

**Search for these keywords in full_native_crash.txt:**
1. `beginning of crash`
2. `FATAL EXCEPTION`
3. `AndroidRuntime`
4. `dbsubstations` (any case)
5. `java.lang.`
6. `Process:` (shows what crashed)
7. `Caused by:`

### Step 2: Check If App Is Actually Installed

```powershell
# List all packages containing "db"
adb shell pm list packages | Select-String db

# Should show: package:org.dbsubstations.dbsubstations

# Get detailed app info
adb shell dumpsys package org.dbsubstations.dbsubstations | Select-String "version|firstInstall|targetSdk"
```

### Step 3: Try Manual Launch with Error Capture

```powershell
# Clear logs
adb logcat -c

# Start logcat in background
Start-Job -ScriptBlock { adb logcat }

# Try to launch manually
adb shell am start -n org.dbsubstations.dbsubstations/org.kivy.android.PythonActivity

# Wait 5 seconds
Start-Sleep -Seconds 5

# Capture logs
adb logcat -d > manual_launch.txt

# Stop background job
Get-Job | Stop-Job
Get-Job | Remove-Job
```

### Step 4: Check for Specific Native Errors

```powershell
# Search for common native crashes
adb logcat -d | Select-String -Pattern "dlopen|UnsatisfiedLinkError|python|kivy|SDL" -Context 2,2
```

### Step 5: Check Android System Logs

```powershell
# System-level crashes
adb logcat -d -s System.err:* AndroidRuntime:* DEBUG:* > system_crash.txt
```

## Most Likely Issues (No Logs = Native Crash)

### Issue A: Python Shared Library Missing
**Symptom:** `dlopen failed: library "libpython3.10.so" not found`
**Cause:** Python wasn't packaged correctly
**Fix:** Architecture mismatch or NDK issue

### Issue B: SDL2 Bootstrap Failed
**Symptom:** App closes immediately, no activity
**Cause:** Missing `p4a.bootstrap = sdl2` (we added this)
**Status:** Should be fixed in latest build

### Issue C: Permission Denied
**Symptom:** `Permission denied` in logs
**Cause:** App lacks necessary permissions
**Fix:** Check AndroidManifest.xml generation

### Issue D: Architecture Mismatch
**Symptom:** `ELFCLASS64 (or 32)` error
**Cause:** App built for arm64 but device is arm32 (or vice versa)
**Fix:** Check device architecture:

```powershell
adb shell getprop ro.product.cpu.abi
# Should show: arm64-v8a (matches our buildozer.spec)
```

## Quick Diagnostic Commands

```powershell
# 1. Device architecture
adb shell getprop ro.product.cpu.abi

# 2. Android version
adb shell getprop ro.build.version.release

# 3. App installation status
adb shell pm list packages -f | Select-String dbsubstations

# 4. Last system error
adb logcat -d -s AndroidRuntime:E | Select-Object -Last 30
```

## What to Share for Help

Please run and share output of:

```powershell
# Create diagnostic report
"=== Device Info ===" | Out-File -FilePath diagnostic.txt
adb shell getprop ro.product.cpu.abi | Out-File -Append -FilePath diagnostic.txt
adb shell getprop ro.build.version.release | Out-File -Append -FilePath diagnostic.txt

"`n=== App Installation ===" | Out-File -Append -FilePath diagnostic.txt
adb shell pm list packages | Select-String dbsubstations | Out-File -Append -FilePath diagnostic.txt

"`n=== Recent Crashes ===" | Out-File -Append -FilePath diagnostic.txt
adb logcat -d -t 100 | Out-File -Append -FilePath diagnostic.txt

# Share diagnostic.txt
```

## Alternative: Use Android Studio Logcat

If PowerShell commands are difficult:

1. Open Android Studio (don't need a project)
2. Bottom toolbar → Click "Logcat"
3. Connect phone
4. **Don't filter anything** - leave dropdown as "No Filters"
5. Launch app
6. Look for red lines (errors)
7. Copy the crash section

## Test with Minimal App

The latest build includes `test_minimal.py` - a bare-bones Kivy app. If you can build it separately, it will help diagnose:

```python
# test_minimal.py - just shows "Kivy Works!"
```

If this crashes too → Kivy/SDL2 issue
If this works → Our app has specific problem (dependencies, imports)

---

**Next Step:** Run Step 1 (full crash capture without filter) and share the relevant section around the crash.
