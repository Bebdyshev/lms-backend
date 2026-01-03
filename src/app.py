from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, PlainTextResponse
from datetime import datetime
from src.config import init_db
from src.routes.auth import router as auth_router
from src.routes.admin import router as admin_router
from src.routes.dashboard import router as dashboard_router
from src.routes.users import router as users_router
from src.routes.courses import router as courses_router
from src.routes.assignments import router as assignments_router
from src.routes.messages import router as messages_router
from src.routes.progress import router as progress_router
from src.routes.media import router as media_router
from src.routes.events import router as events_router
from src.routes.analytics import router as analytics_router
from src.routes.flashcards import router as flashcards_router
from src.routes.leaderboard import router as leaderboard_router
from dotenv import load_dotenv
import logging
import os
from src.routes.socket_messages import create_socket_app

load_dotenv()

# Set max upload size to 100MB
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB in bytes

app = FastAPI(
    title="LMS Platform API",
    description="Learning Management System API",
    version="1.25.0"
)

# Initialize database
init_db()

# Set global logging level to WARNING to reduce noise
logging.basicConfig(level=logging.WARNING)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080", 
        "http://localhost:5173",
        "http://localhost:5174",
        "https://lms.mastereducation.kz",
        "https://lmsapi.mastereducation.kz",
        "https://lms-master.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to check file size
from starlette.requests import Request
from starlette.responses import Response

@app.middleware("http")
async def check_file_size(request: Request, call_next):
    if request.method in ["POST", "PUT", "PATCH"]:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB"}
            )
    response = await call_next(request)
    return response

# Static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(courses_router, prefix="/courses", tags=["Courses"])
app.include_router(assignments_router, prefix="/assignments", tags=["Assignments"])
app.include_router(messages_router, prefix="/messages", tags=["Messages"])
app.include_router(progress_router, prefix="/progress", tags=["Progress"])
app.include_router(media_router, prefix="/media", tags=["Media"])
app.include_router(events_router, prefix="/events", tags=["Events"])
app.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
app.include_router(flashcards_router, prefix="/flashcards", tags=["Flashcards"])
app.include_router(leaderboard_router, prefix="/leaderboard", tags=["Leaderboard"])

# Root endpoint with ASCII art
@app.get("/")
def root():
    ascii_art = """⠀⠀⠀⠀⠀⠀⠀⠀⣀⣤⣴⣶⣾⣿⣿⣿⣿⣷⣶⣦⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⣠⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣄⠀⠀⠀⠀⠀
⠀⠀⠀⣠⣾⣿⣿⣿⣿⣿⣿⠿⣿⣿⡿⢿⣿⣿⠿⣿⣿⣿⣿⣿⣿⣷⣄⠀⠀⠀
⠀⠀⣴⣿⣿⣿⣿⣿⡟⠻⣿⣆⠸⡿⠁⡈⢿⠏⢰⣿⡟⢻⣿⣿⣿⣿⣿⣦⠀⠀
⠀⣼⣿⣿⣿⣿⣿⣿⣿⣆⠙⢿⡄⠁⣼⣧⠈⣠⣿⠋⣠⣿⣿⣿⣿⣿⣿⣿⣧⠀
⢰⣿⣿⣿⣿⣿⣯⡀⠠⣤⣁⣄⣿⣶⣿⣿⣷⣾⣁⣈⣡⡄⢀⣽⣿⣿⣿⣿⣿⡆
⣾⣿⣿⣿⣿⠛⠛⠛⠦⠙⢿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠋⠠⠟⠛⠛⣿⣿⣿⣿⣷
⣿⣿⣿⣿⣿⣿⣿⠿⠶⠶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠶⠷⢾⣿⣿⣿⣿⣿⣿⣿
⢿⣿⣿⣿⣿⣤⣤⣶⠂⣠⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣄⠰⣦⣤⣤⣿⣿⣿⣿⣿
⠸⣿⣿⣿⣿⣿⣟⠁⠘⣉⡉⢉⡿⢿⣿⣿⠿⣿⠉⢉⡙⠂⡈⣻⣿⣿⣿⣿⣿⠇
⠀⢻⣿⣿⣿⣿⣿⣿⣿⠋⣠⣿⠃⡄⢻⡏⢀⠘⣷⣄⠙⣿⣿⣿⣿⣿⣿⣿⡟⠀
⠀⠀⠹⣿⣿⣿⣿⣿⣧⣼⣿⠇⣰⣷⡀⢀⣿⣆⠹⣿⣧⣼⣿⣿⣿⣿⣿⠟⠀⠀
⠀⠀⠀⠙⢿⣿⣿⣿⣿⣿⣿⣶⣿⣿⣷⣾⣿⣿⣶⣿⣿⣿⣿⣿⣿⡿⠋⠀⠀⠀
⠀⠀⠀⠀⠀⠙⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠋⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠻⠿⢿⣿⣿⣿⣿⡿⠿⠟⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀"""
    
    return PlainTextResponse(
        content=ascii_art,
        status_code=200
    )

# Health check endpoint
@app.get("/health")
def health_check():
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.44.0",
            "update": 44,
            "features": {
                "progress_tracking": "enabled",
                "analytics_system": "enhanced",
                "pdf_reports": "enabled",
                "progress_snapshots": "enabled",
                "step_timing": "enabled",
                "export_all_students": "fixed",
                "enhanced_quiz_types": "enabled",
                "long_text_questions": "enabled",
                "media_questions": "enabled",
                "flashcard_steps": "enabled",
                "question_media_upload": "enabled",
                "curator_permissions": "fixed",
                "analytics_access_control": "improved",
                "course_overview_student_discovery": "fixed",
                "groups_analytics_fixed": "enabled",
                "course_groups_view": "enabled",
                "group_students_analytics_fixed": "enabled",
                "excel_export_with_charts": "enabled",
                "unsaved_changes_warnings": "implemented",
                "onboarding_tracking": "enabled"
            }
        }
    )
#-----------------------------------------------------------------------------
socket_app = create_socket_app(app)

# Запуск RabbitMQ Consumer
try:
    from src.services.rabbitmq_consumer import start_rabbitmq_consumer_thread
    rabbitmq_enabled = os.getenv('RABBITMQ_URL')
    
    if rabbitmq_enabled:
        consumer = start_rabbitmq_consumer_thread()
        logging.info("✅ RabbitMQ consumer initialized")
    else:
        logging.warning("⚠️  RabbitMQ URL not configured, skipping consumer initialization")
except Exception as e:
    logging.error(f"❌ Failed to initialize RabbitMQ consumer: {e}")
    logging.warning("⚠️  Continuing without RabbitMQ consumer")

# Error handlers
@app.exception_handler(404)
def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "status_code": 404
        }
    )

@app.exception_handler(403)
def forbidden_handler(request, exc):
    return JSONResponse(
        status_code=403,
        content={
            "error": "Forbidden",
            "message": "You don't have permission to access this resource",
            "status_code": 403
        }
    )

@app.exception_handler(401)
def unauthorized_handler(request, exc):
    return JSONResponse(
        status_code=401,
        content={
            "error": "Unauthorized",
            "message": "Authentication required",
            "status_code": 401
        }
    )