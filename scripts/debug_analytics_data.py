from sqlalchemy import create_engine, text
import os
import sys

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import POSTGRES_URL as DATABASE_URL

def debug_data():
    try:
        engine = create_engine(DATABASE_URL)
        connection = engine.connect()
        
        print("=== DATABASE DEBUG REPORT ===")
        
        # 1. Check Content Types
        print("\n1. Step Content Types:")
        result = connection.execute(text("SELECT content_type, COUNT(*) FROM steps GROUP BY content_type")).fetchall()
        for row in result:
            print(f"   - {row[0]}: {row[1]}")
            
        # 2. Check Students
        print("\n2. Students (Active/Inactive):")
        result = connection.execute(text("SELECT role, is_active, COUNT(*) FROM users GROUP BY role, is_active")).fetchall()
        for row in result:
            print(f"   - Role: {row[0]}, Active: {row[1]}, Count: {row[2]}")
            
        # 3. Check Progress
        print("\n3. Step Progress Count:")
        count = connection.execute(text("SELECT COUNT(*) FROM step_progress")).scalar()
        print(f"   Total StepProgress records: {count}")
        
        print("   StepProgress by Course (via Step->Lesson->Module):")
        query = text("""
            SELECT m.course_id, COUNT(sp.id)
            FROM step_progress sp
            JOIN steps s ON sp.step_id = s.id
            JOIN lessons l ON s.lesson_id = l.id
            JOIN modules m ON l.module_id = m.id
            GROUP BY m.course_id
            LIMIT 10
        """)
        result = connection.execute(query).fetchall()
        for row in result:
             print(f"   - Course {row[0]}: {row[1]} progress records")

        # 4. Check Quiz Attempts
        print("\n4. Quiz Attempts:")
        result = connection.execute(text("SELECT COUNT(*) FROM quiz_attempts")).scalar()
        print(f"   Total QuizAttempt records: {result}")
        if result > 0:
             print("   Sample answers JSONs:")
             samples = connection.execute(text("SELECT answers FROM quiz_attempts WHERE answers IS NOT NULL LIMIT 3")).fetchall()
             for s in samples:
                 print(f"   - {str(s[0])[:100]}...")

        # 5. Check Enrollments
        print("\n5. Enrollments:")
        result = connection.execute(text("SELECT is_active, COUNT(*) FROM enrollments GROUP BY is_active")).fetchall()
        for row in result:
            print(f"   - Active: {row[0]}, Count: {row[1]}")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        if 'connection' in locals():
            connection.close()

if __name__ == "__main__":
    debug_data()
