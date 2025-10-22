#!/usr/bin/env python3
"""
Test script to verify Google APIs are working
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.oauth2.service_account import Credentials
import gspread

def test_connection():
    print("=" * 60)
    print("Google API Connection Test")
    print("=" * 60)
    
    credentials_path = '/home/bebdyshev/Documents/GitHub/lms-master/backend/master-lms-475912-d0afe7611b8b.json'
    
    print(f"\n1. Checking credentials file...")
    if not os.path.exists(credentials_path):
        print(f"❌ Credentials file not found: {credentials_path}")
        return False
    print(f"✅ Credentials file exists")
    
    print(f"\n2. Authenticating with Google...")
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        print(f"✅ Authentication successful")
        print(f"   Service account: {creds.service_account_email}")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False
    
    print(f"\n3. Connecting to Google Sheets API...")
    try:
        client = gspread.authorize(creds)
        print(f"✅ Connected to Google Sheets API")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    
    print(f"\n4. Listing existing spreadsheets...")
    try:
        sheets = client.openall()
        print(f"✅ Found {len(sheets)} spreadsheets")
        if sheets:
            print(f"   First 5:")
            for sheet in sheets[:5]:
                print(f"   - {sheet.title}")
    except Exception as e:
        print(f"❌ Failed to list spreadsheets: {e}")
        return False
    
    print(f"\n5. Testing spreadsheet creation...")
    test_title = f"TEST - Delete Me - {os.urandom(4).hex()}"
    try:
        print(f"   Creating: {test_title}")
        test_sheet = client.create(test_title)
        print(f"✅ Successfully created test spreadsheet!")
        print(f"   URL: {test_sheet.url}")
        
        # Try to delete it
        print(f"\n6. Cleaning up test spreadsheet...")
        client.del_spreadsheet(test_sheet.id)
        print(f"✅ Successfully deleted test spreadsheet")
        
    except Exception as e:
        print(f"❌ Failed to create spreadsheet: {e}")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Error details: {str(e)}")
        
        # Check if it's a quota error
        if "quota" in str(e).lower() or "403" in str(e):
            print(f"\n⚠️  This appears to be a quota or permission error!")
            print(f"   Possible causes:")
            print(f"   1. Google Drive API not enabled")
            print(f"   2. Service account quota exceeded")
            print(f"   3. Insufficient permissions")
            print(f"\n   Solutions:")
            print(f"   1. Enable Google Drive API in Cloud Console")
            print(f"   2. Check service account has 'Editor' or 'Owner' role")
            print(f"   3. Try creating a new service account")
        
        return False
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("Google Sheets integration is working correctly")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)
