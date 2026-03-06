# OneDrive Links for Model Manuals and Maintenance Media

## Overview
This feature allows users to store and access OneDrive links for:
- **Model Manuals**: Technical documentation and schematics for element models (stored once per model type)
- **Maintenance Media**: Photos, videos, and inspection reports for specific maintenance records (stored per maintenance event)

Both desktop and Android users can access these links directly from the database.

---

## Desktop Application

### Managing Model Manuals

1. **Add a New Model**:
   - Go to **Models Management** → **+ Προσθήκη Νέου Μοντέλου**
   - Fill in model details (name, manufacturer, cycle, etc.)
   - In the **Σύνδεσμος Σχεδίου/Εγχειριδίου (OneDrive)** field, paste the OneDrive web link
   - Click **Αποθήκευση** (Save)

2. **Edit Existing Model**:
   - Go to **Models Management** → Select a model → Edit
   - Update the **Σύνδεσμος Σχεδίου/Εγχειριδίου (OneDrive)** field
   - Click **Αποθήκευση** to save

### Managing Maintenance Media Links

1. **Add New Maintenance Record**:
   - Go to **Συντήρηση** (Maintenance) → **+ Νέα Συντήρηση**
   - Fill in maintenance details (date, type, comments, elements, crew)
   - In the **Σύνδεσμος Φάκελο Εικόνων/Βίντεο (OneDrive)** field, paste the OneDrive folder link
   - Click **Αποθήκευση** to save

2. **Edit Existing Maintenance Record**:
   - Go to **Συντήρηση** → Select a record → Edit
   - Update the **Σύνδεσμος Φάκελο Εικόνων/Βίντεο (OneDrive)** field
   - Click **Αποθήκευση** to save

---

## Android Application

### Viewing Model Manuals
The model name and optional manual link are displayed in the element details view. Users can tap the link (when available) to open it in their browser or OneDrive app.

### Viewing Maintenance Media
When viewing an element's maintenance history:
1. Open the element → tap **📋 Maintenance History Button**
2. Each maintenance record displays:
   - **Date** and **Maintenance Type**
   - **📁 Εικόνες/Βίντεο (OneDrive)** button (if photos/videos are available)
   - Element comments, measurements, and overall comments

3. Tap the **📁 Εικόνες/Βίντεο** button to open the OneDrive folder in your device's browser or OneDrive app

---

## How to Create OneDrive Web Links

### For Model Manuals (Document)
1. Upload your PDF schematic/manual to a OneDrive folder
2. Right-click the file → **Share** → **Copy link** (ensure link is set to view-only)
3. Paste the link into the model's **Σύνδεσμος Σχεδίου/Εγχειριδίου (OneDrive)** field

### For Maintenance Media (Folder)
1. Create a new folder in OneDrive for the maintenance (e.g., `/Substations/Subst-Name/Maintenance-2024-03-06`)
2. Upload photos and videos to this folder
3. Share the folder → **Copy link** (ensure link is set to view-only or editable)
4. Paste the link into the maintenance record's **Σύνδεσμος Φάκελο Εικόνων/Βίντεο (OneDrive)** field

---

## Database Schema

### New Columns

#### `element_models` Table
- **`onedrive_manual_link`** (TEXT): OneDrive web link to technical documentation/manual for this model type

#### `maintenance` Table
- **`onedrive_media_folder_link`** (TEXT): OneDrive web link to folder containing photos, videos, and inspection reports for this maintenance record

---

## Data Synchronization

- **Desktop → Android**: OneDrive links are synced to Android devices when the database is shared/downloaded
- **Android → Desktop**: If you edit maintenance records on Android, the links are preserved when syncing back to desktop
- **Live Access**: Users always get the current link (changes to OneDrive folder contents are immediately reflected)

---

## Privacy & Security Considerations

- **Link Sharing**: Ensure OneDrive folder/file sharing is configured correctly before distributing links
- **Expiration**: Monitor share link expiration dates (consider setting long-term access)
- **Access Control**: Use OneDrive's sharing settings to restrict who can access the content
- **Android**: Links open in the device's default browser or OneDrive app; ensure users have necessary OneDrive permissions

---

## Examples

### Model Manual Link Format
```
https://1drv.ms/b/s!AxxxxxxxxxxxxxxxxxxXXXXXXXXXXXX?e=xxxxxx
https://onedrive.live.com/view.aspx?resid=xxxxxxxxxxxxxxxxxxxxx
```

### Maintenance Media Folder Link Format
```
https://1drv.ms/f/s!AxxxxxxxxxxxxxxxxxxXXXXXXXXXXXX?e=xxxxxx
https://onedrive.live.com/?id=xxxxxxxxxxxxxxxxxxxxx&cid=xxxxxxxxxxxxxxxxxxxxx
```

---

## Troubleshooting

### Link Not Opening on Android
- Ensure you have OneDrive app installed or a web browser configured
- Check that the link is valid and not expired
- Verify OneDrive folder/file sharing settings are correct

### Link Not Syncing to Android
- Ensure the database has been fully synchronized to your Android device
- Re-download the latest database version if needed

### Cannot Edit Model/Maintenance After Adding Link
- Check that the OneDrive link format is valid (should start with `https://`)
- Ensure no special characters are breaking the link

---

## Related Features
- [Element Model Management](./model_management.py)
- [Maintenance Tracking](./maintenance.py)
- [Android App](./android_app.py)
