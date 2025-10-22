# Google Sheets Export Setup Guide

This guide explains how to set up Google Sheets integration for analytics export.

## Prerequisites

- Google Account
- Access to Google Cloud Console
- Backend already running

## Setup Steps

### 1. Google Cloud Console Setup

1. **Go to Google Cloud Console**
   - Visit: https://console.cloud.google.com/

2. **Create a New Project** (if not already created)
   - Click "Select a project" → "New Project"
   - Name: `master-lms-475912` (or your preferred name)
   - Click "Create"

3. **Enable Required APIs**
   - Go to "APIs & Services" → "Library"
   - Search and enable:
     - **Google Sheets API**
     - **Google Drive API**

4. **Create Service Account**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "Service Account"
   - Fill in:
     - Name: `lms-analytics-service`
     - Description: `Service account for LMS analytics export`
   - Click "Create and Continue"
   - Grant role: **Editor** or **Owner**
   - Click "Done"

5. **Download Service Account Key**
   - In the Credentials page, find your service account
   - Click on it
   - Go to "Keys" tab
   - Click "Add Key" → "Create new key"
   - Select **JSON** format
   - Click "Create"
   - File will download (e.g., `master-lms-475912-xxxxx.json`)

6. **Save the Credentials File**
   - Move the downloaded JSON file to:
     ```
     /home/bebdyshev/Documents/GitHub/lms-master/backend/
     ```
   - Rename it to match the path in code or update the path in `google_sheets_service.py`

### 2. Backend Configuration

The service is already configured to use the credentials file at:
```
/home/bebdyshev/Documents/GitHub/lms-master/backend/master-lms-475912-d0afe7611b8b.json
```

If you want to use a different path, update the `get_sheets_service()` function in:
```python
# /backend/src/services/google_sheets_service.py
credentials_path = os.getenv(
    'GOOGLE_SERVICE_ACCOUNT_FILE',
    '/path/to/your/credentials.json'  # Update this
)
```

Or set environment variable:
```bash
export GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/credentials.json
```

### 3. Verify Installation

1. **Check Dependencies**
   ```bash
   cd /home/bebdyshev/Documents/GitHub/lms-master/backend
   source venv/bin/activate
   pip list | grep -E "gspread|google-auth"
   ```

   Should show:
   - `gspread`
   - `google-auth`
   - `google-auth-oauthlib`

2. **Test the Service** (optional)
   ```python
   from src.services.google_sheets_service import get_sheets_service
   
   service = get_sheets_service()
   print("✅ Google Sheets service initialized successfully!")
   ```

### 4. Usage

1. **Navigate to Analytics Dashboard**
   - Log in as teacher, curator, or admin
   - Go to Analytics page

2. **Export to Google Sheets**
   - Select a course
   - Click "Export to Google Sheets" button
   - Enter email address (will be shared with this email)
   - Optionally select a group filter
   - Click "Export to Google Sheets"
   - Wait for processing
   - Click "Open Google Sheets" to view

### 5. Troubleshooting

**Error: "Failed to authenticate with Google Sheets"**
- Check that credentials file exists and path is correct
- Verify JSON file is valid (not corrupted)
- Ensure APIs are enabled in Google Cloud Console

**Error: "Permission denied"**
- Make sure you're logged in as teacher/curator/admin
- Verify you have access to the selected course

**Spreadsheet created but not visible**
- Check that email address is correct
- Look in "Shared with me" in Google Drive
- Check spam folder for sharing notification

**Error: "Failed to create spreadsheet"**
- Check internet connection
- Verify Google Sheets API quota not exceeded
- Check service account has proper permissions

**Error: "The user's Drive storage quota has been exceeded"**
- Service account's 15GB Drive quota is full
- **Solution 1**: Files are automatically transferred to user's Drive (ownership transfer)
- **Solution 2**: Manually delete old files from service account's Drive:
  1. Go to https://drive.google.com
  2. Log in with service account email (if possible) OR
  3. Use Google Cloud Console → IAM → Service Accounts → View files
- **Solution 3**: Run cleanup script (see below)

**Cleanup Script** (if quota exceeded):
```python
from src.services.google_sheets_service import get_sheets_service

service = get_sheets_service()
deleted = service.cleanup_old_spreadsheets(days_old=7)
print(f"Deleted {deleted} old spreadsheets")
```

### 6. Security Notes

⚠️ **Important Security Practices:**

1. **Never commit credentials to Git**
   - Already added to `.gitignore`
   - File pattern: `*.json` (excludes package.json, etc.)

2. **Protect the credentials file**
   ```bash
   chmod 600 master-lms-475912-d0afe7611b8b.json
   ```

3. **Rotate keys periodically**
   - Delete old keys in Google Cloud Console
   - Generate new keys every 90 days

4. **Monitor usage**
   - Check API usage in Google Cloud Console
   - Set up billing alerts

### 7. Spreadsheet Structure

Each export creates a spreadsheet with 3 sheets:

**Sheet 1: Student Progress**
- Student details and progress metrics
- Color-coded by performance (green/yellow/red)
- Sortable and filterable

**Sheet 2: Course Overview**
- Course information
- Structure summary
- Engagement statistics

**Sheet 3: Groups Summary** (if applicable)
- Group performance metrics
- Teacher/curator information
- Average statistics

### 8. API Quota

Google Sheets API has quotas:
- **Read requests**: 300 per minute per project
- **Write requests**: 300 per minute per project

For normal usage, these limits are sufficient. If you need more:
- Go to Google Cloud Console → APIs & Services → Quotas
- Request quota increase

### 9. Service Account Email

Your service account email:
```
lms-analytics-service@master-lms-475912.iam.gserviceaccount.com
```

This email is used internally by the API. Users don't need to know it.

### 10. Support

If you encounter issues:
1. Check backend logs for detailed error messages
2. Verify Google Cloud Console configuration
3. Test with a simple course/group first
4. Check network connectivity

---

## Quick Reference

**Credentials File Location:**
```
/home/bebdyshev/Documents/GitHub/lms-master/backend/master-lms-475912-d0afe7611b8b.json
```

**Service Account Email:**
```
lms-analytics-service@master-lms-475912.iam.gserviceaccount.com
```

**API Endpoint:**
```
POST /analytics/export-to-google-sheets
```

**Required Permissions:**
- Role: teacher, curator, or admin
- Course access validated

**Export Button Location:**
- Analytics Dashboard → Top right corner
- "Export to Google Sheets" button

---

✅ Setup complete! You can now export analytics to Google Sheets.
