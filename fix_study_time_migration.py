#!/usr/bin/env python3
"""
Fix NULL values in total_study_time_minutes field
"""
import sys
import os
from datetime import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import SessionLocal
from sqlalchemy import text

def fix_study_time_null_values():
    """Fix NULL values in total_study_time_minutes field"""
    try:
        db = SessionLocal()
        
        # Check for NULL values
        result = db.execute(text("SELECT COUNT(*) FROM users WHERE total_study_time_minutes IS NULL"))
        null_count = result.scalar()
        
        if null_count > 0:
            print(f"Found {null_count} users with NULL total_study_time_minutes")
            
            # Update NULL values to 0
            db.execute(text("UPDATE users SET total_study_time_minutes = 0 WHERE total_study_time_minutes IS NULL"))
            db.commit()
            
            print(f"✅ Updated {null_count} users with NULL total_study_time_minutes to 0")
        else:
            print("✅ No NULL values found in total_study_time_minutes")
        
        # Verify the fix
        result = db.execute(text("SELECT COUNT(*) FROM users WHERE total_study_time_minutes IS NULL"))
        remaining_null = result.scalar()
        
        if remaining_null == 0:
            print("✅ All NULL values have been fixed!")
        else:
            print(f"⚠️  Still have {remaining_null} NULL values")
            
        return True
        
    except Exception as e:
        print(f"❌ Error fixing NULL values: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("🔧 Fixing NULL values in total_study_time_minutes...")
    success = fix_study_time_null_values()
    if success:
        print("🎉 Fix completed successfully!")
    else:
        print("💥 Fix failed!")
        sys.exit(1)
