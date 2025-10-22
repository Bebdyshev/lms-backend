#!/usr/bin/env python3
"""
Manual cleanup script for service account's Google Drive
Run this to free up space when quota is exceeded
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.google_sheets_service import get_sheets_service

def main():
    print("=" * 60)
    print("Google Drive Cleanup Script")
    print("=" * 60)
    print("\nThis script will delete old spreadsheets from service account's Drive")
    print("to free up storage space.\n")
    
    try:
        service = get_sheets_service()
        print("✅ Connected to Google Sheets API\n")
        
        # First, let's see what we have
        print("Fetching list of spreadsheets...")
        all_sheets = service.client.openall()
        print(f"Found {len(all_sheets)} total spreadsheets\n")
        
        # Show analytics spreadsheets
        analytics_sheets = [s for s in all_sheets if s.title.startswith("Analytics -")]
        print(f"Analytics spreadsheets: {len(analytics_sheets)}")
        
        if analytics_sheets:
            print("\nAnalytics spreadsheets to delete:")
            for i, sheet in enumerate(analytics_sheets[:20], 1):  # Show first 20
                print(f"  {i}. {sheet.title}")
            
            if len(analytics_sheets) > 20:
                print(f"  ... and {len(analytics_sheets) - 20} more")
        
        print("\n" + "=" * 60)
        response = input(f"\nDelete {len(analytics_sheets)} analytics spreadsheets? (yes/no): ")
        
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return
        
        print("\nDeleting spreadsheets...")
        deleted_count = 0
        
        for sheet in analytics_sheets:
            try:
                service.client.del_spreadsheet(sheet.id)
                deleted_count += 1
                print(f"  ✓ Deleted: {sheet.title}")
            except Exception as e:
                print(f"  ✗ Failed to delete {sheet.title}: {e}")
        
        print("\n" + "=" * 60)
        print(f"✅ Cleanup complete!")
        print(f"Deleted {deleted_count} out of {len(analytics_sheets)} spreadsheets")
        print(f"You should now have space to create new exports")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("1. Service account credentials file exists")
        print("2. Google Sheets API is enabled")
        print("3. You have internet connection")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
