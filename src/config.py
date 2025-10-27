from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from typing import Generator
from src.schemas.models import Base, UserInDB, Course, Module, Lesson, Group, Enrollment, StudentProgress, Assignment, AssignmentSubmission, Message, LessonMaterial
from passlib.context import CryptContext

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

POSTGRES_URL = os.getenv("POSTGRES_URL")

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

# Database setup
engine = create_engine(POSTGRES_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

print("Connecting to:", POSTGRES_URL)

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize the database and create tables if they don't exist."""
    print("Initializing the database...")
    Base.metadata.create_all(bind=engine)
    create_initial_admin()

def create_initial_admin():
    """Create initial admin user if it doesn't exist."""
    db = SessionLocal()
    try:
        # Check if admin already exists
        admin = db.query(UserInDB).filter(UserInDB.email == "sayakurmanalin@gmail.com").first()
        if not admin:
            print("Creating initial admin user: Сая Курманалина")
            hashed_password = pwd_context.hash("admin123")  # Вы можете изменить пароль
            admin_user = UserInDB(
                email="sayakurmanalin@gmail.com",
                name="Сая Курманалина",
                hashed_password=hashed_password,
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print("✅ Initial admin created successfully!")
            print("Email: sayakurmanalin@gmail.com")
            print("Password: admin123")
        else:
            print("Admin user already exists.")
    except Exception as e:
        print(f"Error creating initial admin: {e}")
        db.rollback()
    finally:
        db.close()

def reset_db():
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating all tables...")
    Base.metadata.create_all(bind=engine)