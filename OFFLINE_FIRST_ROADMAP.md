# Offline-First Architecture Roadmap

## Vision
Enable both desktop and Android apps to work offline with local databases, syncing changes to cloud when internet is available.

---

## Phase 1: Quick Fix (TODAY) ⚡

**Goal:** Get Android app working with cloud API

**Tasks:**
- [x] Increase Android timeout from 30→60 seconds for Render.com cold starts
- [ ] Test Android app connects successfully to cloud
- [ ] Verify data loads from Render.com database

**Status:** IN PROGRESS

**Estimated Time:** 30 minutes (build + test)

---

## Phase 2: Basic Sync Implementation (NEXT WEEK) 🔄

**Goal:** Manual sync between local databases and cloud

### 2.1 Database Schema Updates (~2 hours)
- [ ] Add `last_modified TIMESTAMP` to substations table
- [ ] Add `last_modified TIMESTAMP` to elements table
- [ ] Add `sync_status TEXT` field ('pending', 'synced')
- [ ] Add `deleted INTEGER` field for soft deletes
- [ ] Create `sync_metadata` table (last_sync_timestamp, device_id)
- [ ] Write migration script

### 2.2 API Server Updates (~2-3 hours)
- [ ] Add endpoint: `GET /sync/substations?since=TIMESTAMP`
- [ ] Add endpoint: `POST /sync/substations` (batch upload)
- [ ] Add endpoint: `GET /sync/elements?since=TIMESTAMP`
- [ ] Add endpoint: `POST /sync/elements` (batch upload)
- [ ] Add endpoint: `GET /sync/status` (health check)

### 2.3 Desktop App (DBrun.py) (~4-5 hours)
- [ ] Keep local SQLite database
- [ ] Add "Sync" button to main UI
- [ ] Implement `sync_to_cloud()` function
  - [ ] Upload pending local changes
  - [ ] Download cloud changes since last sync
  - [ ] Merge with last-write-wins strategy
- [ ] Add sync status indicator: "Last synced: 5 minutes ago"
- [ ] Handle sync errors gracefully (show error popup)

### 2.4 Android App (android_app.py) (~2-3 hours)
- [ ] Create local SQLite database (same schema as desktop)
- [ ] Modify app to read from local database first
- [ ] Add "Sync" button to main screen
- [ ] Implement sync functions (same logic as desktop)
- [ ] Show sync progress indicator
- [ ] Store sync metadata in local database

### 2.5 Sync Algorithm - Last-Write-Wins
```python
def sync():
    # 1. Upload local changes
    local_pending = get_records_where(sync_status='pending')
    for record in local_pending:
        api.post('/sync/substations', record)
        mark_as_synced(record.id)
    
    # 2. Download cloud changes
    last_sync = get_last_sync_timestamp()
    cloud_changes = api.get(f'/sync/substations?since={last_sync}')
    
    # 3. Merge (newer timestamp wins)
    for cloud_record in cloud_changes:
        local_record = get_local_record(cloud_record.id)
        if not local_record or cloud_record.last_modified > local_record.last_modified:
            update_local(cloud_record)
    
    # 4. Save sync timestamp
    save_last_sync_timestamp(now())
```

**Status:** NOT STARTED

**Estimated Time:** 8-12 hours total

---

## Phase 3: Polish & Auto-Sync (LATER) ✨

**Goal:** Automatic background sync with conflict handling

### 3.1 Auto-Sync Features (~6-8 hours)
- [ ] Auto-sync on app startup
- [ ] Background sync timer (every 5 minutes)
- [ ] Retry queue for failed sync attempts
- [ ] Network connectivity detection

### 3.2 Conflict Resolution (~4-6 hours)
- [ ] Detect conflicting changes (both modified same record)
- [ ] Show conflict dialog to user
- [ ] Let user choose: Keep local / Keep cloud / Merge manually

### 3.3 Performance Optimization (~4-6 hours)
- [ ] Partial sync (only changed records, not full database)
- [ ] Batch operations for faster sync
- [ ] Compress sync payloads
- [ ] Cache sync metadata

### 3.4 UI Improvements (~2-3 hours)
- [ ] Sync progress bar
- [ ] "Syncing..." animation
- [ ] Sync history log
- [ ] Visual indicators for unsynced changes

**Status:** NOT STARTED

**Estimated Time:** 16-23 hours total

---

## Architecture Diagram

```
LAPTOP:                    CLOUD (Render.com):           PHONE:
┌────────────────┐        ┌────────────────┐        ┌────────────────┐
│ DBrun.py       │        │ api_server.py  │        │ android_app.py │
│                │        │ Flask API      │        │                │
├────────────────┤        ├────────────────┤        ├────────────────┤
│substations.db  │◄─sync─►│  database.db   │◄─sync─►│substations.db  │
│(LOCAL)         │        │  (MASTER)      │        │(LOCAL)         │
│                │        │                │        │                │
│ Works offline! │        │ Always online  │        │ Works offline! │
└────────────────┘        └────────────────┘        └────────────────┘
```

---

## Benefits

✅ **Offline functionality** - Work without internet
✅ **Fast startup** - No waiting for cloud
✅ **Cloud backup** - Data safe in cloud
✅ **Multi-device sync** - Desktop ↔ Phone
✅ **Reliability** - Local copy always available
✅ **Flexibility** - Manual or auto sync

---

## Trade-offs

⚠️ **Complexity** - More code to maintain
⚠️ **Conflicts possible** - Need resolution strategy
⚠️ **Storage** - Each device stores full database
⚠️ **Sync time** - User must wait for sync to complete

---

## Progress Tracking

- **Phase 1:** IN PROGRESS (50% complete)
- **Phase 2:** NOT STARTED (0% complete)
- **Phase 3:** NOT STARTED (0% complete)

**Overall:** ~5% complete

---

## Next Steps

1. ✅ Document roadmap (this file)
2. ⏳ Increase timeout and rebuild Android APK
3. ⏳ Test Android connection to cloud
4. ⏳ Plan Phase 2 implementation schedule

---

**Last Updated:** January 30, 2026
**Status:** Phase 1 in progress
