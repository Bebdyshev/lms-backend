"""
Migration script to completely transform Travel AI Planner to LMS Platform
- Drops old travel-related tables
- Creates LMS tables
- Creates default admin user
- Creates sample data for testing
"""

from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.orm import sessionmaker
from src.schemas.models import Base, UserInDB, Group, Course, Module, Lesson, Enrollment
from src.utils.auth_utils import hash_password
from src.config import POSTGRES_URL
import os
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    """Run the complete migration from Travel AI to LMS"""
    print("🚀 Starting Complete LMS Platform Migration...")
    
    # Create engine and session
    engine = create_engine(POSTGRES_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("📊 Checking current database state...")
        
        # Get current tables
        metadata = MetaData()
        metadata.reflect(bind=engine)
        current_tables = list(metadata.tables.keys())
        print(f"Current tables: {current_tables}")
        
        # Drop ALL old tables to start fresh
        print("🗑️  Dropping ALL existing tables for clean LMS setup...")
        
        # Disable foreign key constraints temporarily
        db.execute(text("SET session_replication_role = replica;"))
        
        for table_name in current_tables:
            print(f"  - Dropping table: {table_name}")
            db.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
        
        # Re-enable foreign key constraints
        db.execute(text("SET session_replication_role = DEFAULT;"))
        
        db.commit()
        print("  ✅ All old tables dropped successfully")
        
        print("🏗️  Creating new LMS database structure...")
        
        # Create all LMS tables
        Base.metadata.create_all(bind=engine)
        print("  ✅ All LMS tables created successfully")
        
        print("👤 Creating default admin user...")
        
        # Create default admin
        admin_email = os.getenv("ADMIN_EMAIL", "admin@lms.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_name = os.getenv("ADMIN_NAME", "System Administrator")
        
        admin_user = UserInDB(
            email=admin_email,
            name=admin_name,
            hashed_password=hash_password(admin_password),
            role="admin",
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print(f"  ✅ Admin user created:")
        print(f"     Email: {admin_email}")
        print(f"     Password: {admin_password}")
        print(f"     Role: admin")
        print(f"  ⚠️  Please change the default password after first login!")
        
        # Create sample data for testing
        create_sample_data = os.getenv("CREATE_SAMPLE_DATA", "true").lower() == "true"
        
        if create_sample_data:
            print("📚 Creating comprehensive sample data...")
            create_comprehensive_sample_data(db, admin_user.id)
        
        print("✅ Migration completed successfully!")
        print("\n🎯 LMS Platform is ready!")
        print("\n📝 Next steps:")
        print("1. Start the application: uvicorn src.app:app --reload")
        print("2. Open API docs: http://localhost:8000/docs")
        print("3. Login with admin credentials")
        print("4. Test the sample data or create your own content")
        print("\n🚀 Available endpoints:")
        print("   - Admin Panel: /admin/*")
        print("   - Courses: /courses/*")
        print("   - Assignments: /assignments/*")
        print("   - Messages: /messages/*")
        print("   - Progress: /progress/*")
        print("   - Dashboard: /dashboard/*")
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def create_comprehensive_sample_data(db, admin_id):
    """Create comprehensive sample LMS data for testing all features"""
    
    try:
        print("  📝 Creating sample users...")
        
        # Create sample teacher
        teacher = UserInDB(
            email="teacher@lms.com",
            name="Анна Петрова",
            hashed_password=hash_password("teacher123"),
            role="teacher",
            is_active=True
        )
        db.add(teacher)
        db.flush()
        
        # Create sample curator
        curator = UserInDB(
            email="curator@lms.com",
            name="Сергей Кураторов",
            hashed_password=hash_password("curator123"),
            role="curator",
            is_active=True
        )
        db.add(curator)
        db.flush()
        
        # Create sample group
        print("  👥 Creating sample group...")
        sample_group = Group(
            name="Группа 10А",
            description="Основная группа для демонстрации",
            teacher_id=teacher.id
        )
        db.add(sample_group)
        db.flush()
        
        # Update curator's group
        curator.group_id = sample_group.id
        
        # Create sample students
        print("  🎓 Creating sample students...")
        students = []
        for i in range(5):
            student = UserInDB(
                email=f"student{i+1}@lms.com",
                name=f"Студент {i+1}",
                hashed_password=hash_password("student123"),
                role="student",
                student_id=f"STU{2024}{i+1:03d}",
                group_id=sample_group.id,
                is_active=True
            )
            db.add(student)
            students.append(student)
        
        db.flush()
        
        # Create sample courses
        print("  📚 Creating sample courses...")
        
        # Course 1: Programming
        course1 = Course(
            title="Основы программирования",
            description="Изучение основ программирования на Python",
            teacher_id=teacher.id,
            cover_image_url="https://via.placeholder.com/400x250/4F46E5/FFFFFF?text=Programming",
            estimated_duration_minutes=1800,  # 30 hours
            is_active=True
        )
        db.add(course1)
        db.flush()
        
        # Course 2: Mathematics
        course2 = Course(
            title="Высшая математика",
            description="Курс по высшей математике для IT специальностей",
            teacher_id=teacher.id,
            cover_image_url="https://via.placeholder.com/400x250/059669/FFFFFF?text=Mathematics",
            estimated_duration_minutes=2400,  # 40 hours
            is_active=True
        )
        db.add(course2)
        db.flush()
        
        print("  📖 Creating modules and lessons...")
        
        # Create modules and lessons for Course 1
        module1 = Module(
            course_id=course1.id,
            title="Введение в Python",
            description="Основы языка Python",
            order_index=1
        )
        db.add(module1)
        db.flush()
        
        # Lessons for Module 1
        lessons = [
            {
                "title": "Что такое Python?",
                "description": "Введение в язык программирования Python",
                "content_type": "video",
                "video_url": "https://www.youtube.com/watch?v=example1",
                "duration_minutes": 30
            },
            {
                "title": "Установка Python",
                "description": "Как установить Python на ваш компьютер",
                "content_type": "video",
                "video_url": "https://www.youtube.com/watch?v=example2",
                "duration_minutes": 20
            },
            {
                "title": "Первая программа",
                "description": "Написание вашей первой программы на Python",
                "content_type": "text",
                "content_text": "# Ваша первая программа\nprint('Привет, мир!')\n\nЭта программа выводит текст на экран.",
                "duration_minutes": 15
            }
        ]
        
        created_lessons = []
        for i, lesson_data in enumerate(lessons):
            lesson = Lesson(
                module_id=module1.id,
                title=lesson_data["title"],
                description=lesson_data["description"],
                content_type=lesson_data["content_type"],
                video_url=lesson_data.get("video_url"),
                content_text=lesson_data.get("content_text"),
                duration_minutes=lesson_data["duration_minutes"],
                order_index=i + 1
            )
            db.add(lesson)
            created_lessons.append(lesson)
        
        db.flush()
        
        print("  📝 Creating sample assignments...")
        
        # Create sample assignments
        from src.schemas.models import Assignment
        import json
        
        # Assignment 1: Single Choice
        assignment1 = Assignment(
            lesson_id=created_lessons[0].id,
            title="Проверка знаний: Что такое Python?",
            description="Тест на понимание основ Python",
            assignment_type="single_choice",
            content=json.dumps({
                "question": "Что такое Python?",
                "options": [
                    "Язык программирования",
                    "Змея",
                    "Операционная система",
                    "База данных"
                ]
            }),
            correct_answers=json.dumps({"correct_answer": 0}),
            max_score=10
        )
        db.add(assignment1)
        
        # Assignment 2: Multiple Choice
        assignment2 = Assignment(
            lesson_id=created_lessons[1].id,
            title="Преимущества Python",
            description="Выберите все преимущества языка Python",
            assignment_type="multiple_choice",
            content=json.dumps({
                "question": "Какие из следующих утверждений верны для Python?",
                "options": [
                    "Простой синтаксис",
                    "Большое количество библиотек",
                    "Только для веб-разработки",
                    "Кроссплатформенность",
                    "Очень быстрый как C++"
                ]
            }),
            correct_answers=json.dumps({"correct_answers": [0, 1, 3]}),
            max_score=15
        )
        db.add(assignment2)
        
        # Assignment 3: Fill in the blanks
        assignment3 = Assignment(
            lesson_id=created_lessons[2].id,
            title="Дополните код",
            description="Заполните пропуски в коде Python",
            assignment_type="fill_in_blanks",
            content=json.dumps({
                "text_with_blanks": "_____(\"Привет, мир!\") - эта функция выводит текст на _____",
                "blank_count": 2
            }),
            correct_answers=json.dumps({"correct_answers": ["print", "экран"]}),
            max_score=20
        )
        db.add(assignment3)
        
        db.flush()
        
        print("  🎓 Enrolling students in courses...")
        
        # Enroll all students in both courses
        for student in students:
            enrollment1 = Enrollment(
                user_id=student.id,
                course_id=course1.id,
                is_active=True
            )
            enrollment2 = Enrollment(
                user_id=student.id,
                course_id=course2.id,
                is_active=True
            )
            db.add(enrollment1)
            db.add(enrollment2)
        
        print("  📊 Creating sample progress...")
        
        # Create some progress for students
        from src.schemas.models import StudentProgress
        from datetime import datetime, timedelta
        
        # First student has made good progress
        student1 = students[0]
        for i, lesson in enumerate(created_lessons):
            progress = StudentProgress(
                user_id=student1.id,
                course_id=course1.id,
                lesson_id=lesson.id,
                status="completed" if i < 2 else "in_progress",
                completion_percentage=100 if i < 2 else 50,
                time_spent_minutes=lesson.duration_minutes + 5,
                last_accessed=datetime.utcnow() - timedelta(days=i),
                completed_at=datetime.utcnow() - timedelta(days=i) if i < 2 else None
            )
            db.add(progress)
            
            # Update student's total study time
            student1.total_study_time_minutes += lesson.duration_minutes + 5
        
        print("  💬 Creating sample messages...")
        
        # Create sample messages
        from src.schemas.models import Message
        
        # Student asks teacher a question
        message1 = Message(
            from_user_id=student1.id,
            to_user_id=teacher.id,
            content="Здравствуйте! У меня вопрос по первому уроку. Можете объяснить подробнее про установку Python?",
            is_read=False
        )
        db.add(message1)
        
        # Teacher responds
        message2 = Message(
            from_user_id=teacher.id,
            to_user_id=student1.id,
            content="Привет! Конечно, помогу. Рекомендую скачать Python с официального сайта python.org. Если возникнут проблемы - пишите!",
            is_read=False
        )
        db.add(message2)
        
        db.commit()
        
        print("  ✅ Sample data created successfully!")
        print("\n📋 Created sample data:")
        print(f"     👤 Users: 1 admin, 1 teacher, 1 curator, 5 students")
        print(f"     👥 Groups: 1 group")
        print(f"     📚 Courses: 2 courses")
        print(f"     📖 Modules: 1 module with 3 lessons")
        print(f"     📝 Assignments: 3 different types")
        print(f"     📊 Progress: Sample progress for student 1")
        print(f"     💬 Messages: 2 sample messages")
        print("\n🔑 Sample login credentials:")
        print(f"     Admin: admin@lms.com / admin123")
        print(f"     Teacher: teacher@lms.com / teacher123")
        print(f"     Curator: curator@lms.com / curator123")
        print(f"     Students: student1@lms.com / student123 (до student5@lms.com)")
        
    except Exception as e:
        print(f"  ❌ Failed to create sample data: {str(e)}")
        db.rollback()
        raise

if __name__ == "__main__":
    print("🎓 LMS Platform Complete Migration Tool")
    print("This will completely replace your database with a fresh LMS setup")
    print("⚠️  WARNING: This will DELETE ALL existing data!")
    
    confirm = input("\nDo you want to proceed? Type 'YES' to continue: ").strip()
    
    if confirm == "YES":
        run_migration()
    else:
        print("Migration cancelled.")
        print("To proceed, run the script again and type 'YES' when prompted.")
