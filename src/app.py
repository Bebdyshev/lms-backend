from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, PlainTextResponse
from datetime import datetime
from src.config import init_db
from src.routes.auth import router as auth_router
from src.routes.admin import router as admin_router
from src.routes.admin_progress import router as admin_progress_router
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
from src.routes.assignment_zero import router as assignment_zero_router
from src.routes.questions import router as questions_router
from src.routes.gamification import router as gamification_router
from src.routes.ai_tools import router as ai_tools_router
from src.routes.head_teacher import router as head_teacher_router
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
    version="1.26.0"
)

# Initialize database
init_db()

# Set logging level to INFO to see email and reminder logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Gzip middleware for compressing large responses (e.g. quizzes)
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

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
app.include_router(admin_progress_router, prefix="/admin", tags=["Admin Progress"])
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
app.include_router(assignment_zero_router, prefix="/assignment-zero", tags=["Assignment Zero"])
app.include_router(questions_router, tags=["Questions"])
app.include_router(gamification_router, prefix="/gamification", tags=["Gamification"])
app.include_router(ai_tools_router, prefix="/ai-tools", tags=["AI Tools"])
app.include_router(head_teacher_router, prefix="/head-teacher", tags=["Head Teacher"])

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
            "version": "1.48.0",
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

# Запуск планировщика напоминаний о уроках
try:
    from src.services.lesson_reminder_scheduler import start_lesson_reminder_scheduler
    resend_api_key = os.getenv('RESEND_API_KEY')
    
    if resend_api_key:
        start_lesson_reminder_scheduler()
        logging.info("✅ Lesson reminder scheduler initialized")
    else:
        logging.warning("⚠️  RESEND_API_KEY not configured, skipping lesson reminder scheduler")
except Exception as e:
    logging.error(f"❌ Failed to initialize lesson reminder scheduler: {e}")
    logging.warning("⚠️  Continuing without lesson reminder scheduler")

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