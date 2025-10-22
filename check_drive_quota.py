#!/usr/bin/env python3
"""
Check Google Drive storage usage and files
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

def check_drive():
    print("=" * 70)
    print("Google Drive Storage Check")
    print("=" * 70)
    
    credentials_path = '/home/bebdyshev/Documents/GitHub/lms-master/backend/master-lms-475912-d0afe7611b8b.json'
    
    print(f"\nAuthenticating...")
    scopes = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file'
    ]
    
    try:
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        drive_service = build('drive', 'v3', credentials=creds)
        print(f"✅ Connected to Google Drive API")
        print(f"   Service account: {creds.service_account_email}")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return
    
    # Get storage quota
    print(f"\n" + "=" * 70)
    print("STORAGE QUOTA")
    print("=" * 70)
    try:
        about = drive_service.about().get(fields='storageQuota,user').execute()
        quota = about.get('storageQuota', {})
        
        limit = int(quota.get('limit', 0))
        usage = int(quota.get('usage', 0))
        usage_in_drive = int(quota.get('usageInDrive', 0))
        usage_in_trash = int(quota.get('usageInDriveTrash', 0))
        
        print(f"Total Limit:      {limit / (1024**3):.2f} GB")
        print(f"Total Used:       {usage / (1024**3):.2f} GB ({usage / limit * 100:.1f}%)")
        print(f"Used in Drive:    {usage_in_drive / (1024**3):.2f} GB")
        print(f"Used in Trash:    {usage_in_trash / (1024**3):.2f} GB")
        print(f"Available:        {(limit - usage) / (1024**3):.2f} GB")
        
        if usage >= limit:
            print(f"\n⚠️  QUOTA EXCEEDED! Storage is full.")
        elif usage / limit > 0.9:
            print(f"\n⚠️  WARNING: Storage is {usage / limit * 100:.1f}% full")
        
    except Exception as e:
        print(f"❌ Could not get quota info: {e}")
    
    # List all files
    print(f"\n" + "=" * 70)
    print("FILES IN DRIVE")
    print("=" * 70)
    
    try:
        # Get all files (not in trash)
        results = drive_service.files().list(
            pageSize=100,
            fields="files(id, name, mimeType, size, createdTime, trashed)",
            q="trashed=false"
        ).execute()
        
        files = results.get('files', [])
        print(f"\nFound {len(files)} files (not in trash):")
        
        total_size = 0
        for i, file in enumerate(files, 1):
            size = int(file.get('size', 0))
            total_size += size
            size_mb = size / (1024**2)
            name = file.get('name', 'Unknown')
            mime = file.get('mimeType', 'Unknown')
            created = file.get('createdTime', 'Unknown')
            
            print(f"\n{i}. {name}")
            print(f"   Type: {mime}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"   Created: {created}")
            print(f"   ID: {file['id']}")
        
        print(f"\nTotal size of files: {total_size / (1024**2):.2f} MB")
        
    except Exception as e:
        print(f"❌ Could not list files: {e}")
    
    # List files in trash
    print(f"\n" + "=" * 70)
    print("FILES IN TRASH")
    print("=" * 70)
    
    try:
        results = drive_service.files().list(
            pageSize=100,
            fields="files(id, name, mimeType, size, createdTime)",
            q="trashed=true"
        ).execute()
        
        trash_files = results.get('files', [])
        print(f"\nFound {len(trash_files)} files in trash:")
        
        trash_size = 0
        for i, file in enumerate(trash_files, 1):
            size = int(file.get('size', 0))
            trash_size += size
            size_mb = size / (1024**2)
            name = file.get('name', 'Unknown')
            
            print(f"{i}. {name} - {size_mb:.2f} MB")
        
        print(f"\nTotal size in trash: {trash_size / (1024**2):.2f} MB")
        
        if trash_files:
            print(f"\n⚠️  Trash is not empty! Empty it to free up space.")
            print(f"   You can empty trash with: drive_service.files().emptyTrash().execute()")
        
    except Exception as e:
        print(f"❌ Could not list trash: {e}")
    
    print(f"\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    
    if usage >= limit:
        print("\n🔴 Your Drive is FULL. Options:")
        print("   1. Empty trash (if any files there)")
        print("   2. Delete old files")
        print("   3. Create a new Google Cloud project (fresh 15GB quota)")
        print("   4. Use Excel export instead of Google Sheets")
    
    print("\n")

if __name__ == "__main__":
    check_drive()
