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
from dotenv import load_dotenv
import logging
from src.routes.socket_messages import create_socket_app

load_dotenv()

app = FastAPI(
    title="LMS Platform API",
    description="Learning Management System API",
    version="1.24.0"
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
            "version": "1.24.0",
        }
    )

# -----------------------------------------------------------------------------
# Socket.IO setup (WebSocket messaging)
# -----------------------------------------------------------------------------
socket_app = create_socket_app(app)

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