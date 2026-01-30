# Build Android APK using Google Colab (Free)

Google Colab provides free cloud computing with better support for Android builds.

## Steps:

1. **Go to Google Colab**: https://colab.research.google.com

2. **Create a new notebook** and create 4 separate code cells

**IMPORTANT: Copy only the code below, NOT the ```python lines!**

---

### Cell 1: Install dependencies
Copy and paste this into the first cell:

```
!apt-get update
!apt-get install -y openjdk-17-jdk wget unzip autoconf libtool pkg-config
!pip3 install --upgrade pip
!pip3 install --upgrade buildozer cython==0.29.33
!buildozer --version
```

Run it (Shift+Enter), wait for completion (~2 minutes)

---

### Cell 2: Upload your files
Copy and paste this into the second cell (copy ALL lines at once):

```
from google.colab import files

# Upload your dbsubstations.zip
uploaded = files.upload()

# Extract
!unzip -q dbsubstations.zip
!ls -la

# Rename android_app.py to main.py (required by buildozer)
!mv android_app.py main.py

# Create buildozer.spec
spec = """[app]
title = DB Substations
package.name = dbsubstations
package.domain = org.dbsubstations

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0
requirements = python3,kivy==2.0.0,requests

permissions = INTERNET,ACCESS_NETWORK_STATE

orientation = portrait
fullscreen = 0

android.api = 31
android.minapi = 21
android.ndk = 25b
android.arch = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
"""

with open('buildozer.spec', 'w') as f:
    f.write(spec)

print("buildozer.spec created and android_app.py renamed to main.py")
```

Run it, click "Choose Files" button, select `dbsubstations.zip`

---

### Cell 3: Accept licenses and build
Copy and paste this into the third cell:

```
import os
os.chdir('/content')

# Clean any cache and build fresh
!rm -rf .buildozer

# Accept Android SDK licenses and build
!python3 -m buildozer android debug
```

Run it - this will take 15-30 minutes for first build

---

### Cell 4: Download APK
Copy and paste this into the fourth cell:

```
from google.colab import files
import glob

# Find and download the APK
apk_files = glob.glob('bin/*.apk')
if apk_files:
    files.download(apk_files[0])
    print(f"Downloading: {apk_files[0]}")
else:
    print("No APK found. Check build errors above.")
```

Run it to download your APK file

---

## Advantages:
- ✅ Free (no cost)
- ✅ No local admin rights needed
- ✅ Better dependency handling than GitHub Actions
- ✅ Can monitor build progress in real-time
- ✅ 15-30 min first build, ~5 min subsequent builds

## Your dbsubstations.zip is ready!
Located at: `c:\Users\e.karalis\OneDrive - Hellenic Electricity Distribution Network Operator S.A\60_Projects\DB Substations\dbsubstations.zip`

Just upload it to Colab and run the cells in order.
