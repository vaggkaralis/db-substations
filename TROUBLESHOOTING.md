# Troubleshooting Android App Crashes

If the app crashes or fails to open a database file, follow these steps:

1. **Check for Error Popups**
   - The app displays all errors in a popup. Read the message for details.

2. **Review Log Output**
   - Connect your device to a computer and use `adb logcat` to view logs.
   - Look for lines starting with `APP:` for detailed logs and errors.

3. **Common Issues**
   - **Permissions**: Ensure storage permissions are granted. If prompted, allow access and retry.
   - **File Not Found**: Make sure the selected file exists and is accessible.
   - **Unsupported File**: Only valid SQLite `.db` files are supported.
   - **Android Content URI**: If using a file from another app, ensure the app provides access via SAF (Storage Access Framework).

4. **App Version**
   - Confirm you are using the latest version of the app and Kivy (2.3.0+).

5. **Device Storage**
   - Ensure there is enough free space in device storage for file operations.

6. **Reporting Issues**
   - When reporting a crash, include:
     - The error popup message
     - Relevant log lines from `adb logcat`
     - Steps to reproduce the issue
     - Device model and Android version

7. **Advanced Debugging**
   - If you have Python experience, run the app with debugging enabled and inspect the logs for stack traces.

---

For further help, contact the developer with the above information.
