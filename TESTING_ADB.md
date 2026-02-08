**ADB repro steps & logcat commands**

Use these steps to reproduce the Android file-picker / SAF and permission flows and collect logs.

- Build and install APK (from local buildozer or CI artifact).

- On the device or emulator connect via ADB:

```bash
adb devices
adb install -r bin/MyApp-debug.apk
```

- Reproduce the flow in the app (open DB via file picker, deny/allow permissions, pick content:// URI).

- Collect logcat while reproducing (filter to app package name, replace `com.example.app`):

```bash
adb logcat --buffer=main --regex "(Python|kivy|db_substations|com.example.app)" > ~/adb_logcat_dbsubstations.log
```

- Alternatively capture full log for timeframe (30s):

```bash
adb logcat -v time -d > ~/adb_full_log_$(date +%Y%m%d_%H%M%S).log
```

- If you need to restart the app and capture a fresh log:

```bash
adb shell am force-stop com.example.app
adb logcat -c
adb shell am start -n com.example.app/.MainActivity
adb logcat -v time > ~/adb_fresh_log.log
```

- To pull files saved to external storage (e.g., `change_log.txt`) from device:

```bash
adb shell ls -la /sdcard/Android/data/com.example.app/files
adb pull /sdcard/Android/data/com.example.app/files/change_log.txt ./
```

Notes:
- Replace `com.example.app` and APK paths with your actual package and file names.
- Use `adb logcat` timestamps to correlate UI actions and exceptions.
