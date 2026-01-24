"""Gamification routes for points, leaderboard, and teacher bonuses."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel

from src.schemas.models import (
    UserInDB,
    PointHistory,
    PointHistorySchema,
    Group,
    GroupStudent,
)
from src.routes.auth import get_current_user_dependency
from src.config import get_db

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class GamificationStatsResponse(BaseModel):
    activity_points: int
    daily_streak: int
    monthly_points: int
    rank_this_month: Optional[int] = None


class TeacherBonusRequest(BaseModel):
    student_id: int
    amount: int  # Max 10 points per week
    reason: Optional[str] = None


class LeaderboardEntry(BaseModel):
    user_id: int
    user_name: str
    avatar_url: Optional[str] = None
    points: int
    rank: int


class LeaderboardResponse(BaseModel):
    period: str  # 'monthly', 'all_time'
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_participants: int
    entries: List[LeaderboardEntry]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def award_points(db: Session, user_id: int, amount: int, reason: str, description: str = None):
    """Award points to a user and record in history."""
    # Update user's total points
    user = db.query(UserInDB).filter(UserInDB.id == user_id).first()
    if not user:
        return None
    
    user.activity_points = (user.activity_points or 0) + amount
    
    # Record in history
    history_entry = PointHistory(
        user_id=user_id,
        amount=amount,
        reason=reason,
        description=description
    )
    db.add(history_entry)
    db.commit()
    
    return history_entry


def get_monthly_points(db: Session, user_id: int, year: int = None, month: int = None) -> int:
    """Get total points for a user in a specific month."""
    if year is None:
        year = datetime.utcnow().year
    if month is None:
        month = datetime.utcnow().month
    
    result = db.query(func.coalesce(func.sum(PointHistory.amount), 0)).filter(
        PointHistory.user_id == user_id,
        extract('year', PointHistory.created_at) == year,
        extract('month', PointHistory.created_at) == month
    ).scalar()
    
    return int(result) if result else 0


def get_teacher_weekly_bonus_given(db: Session, teacher_id: int) -> int:
    """Get how many bonus points a teacher has given this week."""
    # Get start of current week (Monday)
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    
    result = db.query(func.coalesce(func.sum(PointHistory.amount), 0)).filter(
        PointHistory.reason == 'teacher_bonus',
        PointHistory.description.like(f'%teacher:{teacher_id}%'),
        PointHistory.created_at >= datetime.combine(start_of_week, datetime.min.time())
    ).scalar()
    
    return int(result) if result else 0


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status", response_model=GamificationStatsResponse)
async def get_gamification_status(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get current user's gamification stats."""
    monthly_points = get_monthly_points(db, current_user.id)
    
    # Calculate rank this month
    now = datetime.utcnow()
    subquery = db.query(
        PointHistory.user_id,
        func.sum(PointHistory.amount).label('total')
    ).filter(
        extract('year', PointHistory.created_at) == now.year,
        extract('month', PointHistory.created_at) == now.month
    ).group_by(PointHistory.user_id).subquery()
    
    # Count users with more points
    users_ahead = db.query(func.count()).select_from(subquery).filter(
        subquery.c.total > monthly_points
    ).scalar()
    
    rank = (users_ahead or 0) + 1
    
    return GamificationStatsResponse(
        activity_points=current_user.activity_points or 0,
        daily_streak=current_user.daily_streak or 0,
        monthly_points=monthly_points,
        rank_this_month=rank
    )


@router.post("/bonus")
async def give_teacher_bonus(
    request: TeacherBonusRequest,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Teacher gives bonus points to a student (max 10 per week)."""
    # Check if current user is a teacher
    if current_user.role not in ['teacher', 'admin', 'curator']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can give bonus points"
        )
    
    # Validate amount
    if request.amount < 1 or request.amount > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bonus amount must be between 1 and 10"
        )
    
    # Check weekly limit for this teacher
    weekly_given = get_teacher_weekly_bonus_given(db, current_user.id)
    if weekly_given + request.amount > 10:
        remaining = max(0, 10 - weekly_given)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Weekly bonus limit reached. You can give {remaining} more points this week."
        )
    
    # Verify student exists
    student = db.query(UserInDB).filter(UserInDB.id == request.student_id, UserInDB.role == 'student').first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Award the bonus
    description = f"teacher:{current_user.id}|{request.reason or 'Good activity'}"
    entry = award_points(db, request.student_id, request.amount, 'teacher_bonus', description)
    
    return {
        "success": True,
        "message": f"Awarded {request.amount} points to {student.name}",
        "new_total": student.activity_points
    }


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    period: str = Query("monthly", description="'monthly' or 'all_time'"),
    group_id: Optional[int] = Query(None, description="Filter by group ID"),
    limit: int = Query(50, le=100),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get leaderboard rankings."""
    now = datetime.utcnow()
    
    if period == "monthly":
        # Monthly leaderboard from PointHistory
        start_date = date(now.year, now.month, 1)
        if now.month == 12:
            end_date = date(now.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(now.year, now.month + 1, 1) - timedelta(days=1)
        
        # Base query for monthly points
        query = db.query(
            PointHistory.user_id,
            func.sum(PointHistory.amount).label('total_points')
        ).filter(
            extract('year', PointHistory.created_at) == now.year,
            extract('month', PointHistory.created_at) == now.month
        )
        
        # Filter by group if specified
        if group_id:
            student_ids = db.query(GroupStudent.student_id).filter(
                GroupStudent.group_id == group_id
            ).subquery()
            query = query.filter(PointHistory.user_id.in_(student_ids))
        
        results = query.group_by(PointHistory.user_id).order_by(
            func.sum(PointHistory.amount).desc()
        ).limit(limit).all()
        
        
    elif period == "weekly":
        # Weekly leaderboard (starts Monday)
        today = date.today()
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        
        # Base query for weekly points
        query = db.query(
            PointHistory.user_id,
            func.sum(PointHistory.amount).label('total_points')
        ).filter(
            PointHistory.created_at >= datetime.combine(start_date, datetime.min.time()),
            PointHistory.created_at <= datetime.combine(end_date, datetime.max.time())
        )
        
        # Filter by group if specified
        if group_id:
            student_ids = db.query(GroupStudent.student_id).filter(
                GroupStudent.group_id == group_id
            ).subquery()
            query = query.filter(PointHistory.user_id.in_(student_ids))
        
        results = query.group_by(PointHistory.user_id).order_by(
            func.sum(PointHistory.amount).desc()
        ).limit(limit).all()
        
    else:
        # All-time leaderboard from User.activity_points
        start_date = None
        end_date = None
        
        query = db.query(UserInDB).filter(UserInDB.role == 'student')
        
        if group_id:
            student_ids = db.query(GroupStudent.student_id).filter(
                GroupStudent.group_id == group_id
            ).subquery()
            query = query.filter(UserInDB.id.in_(student_ids))
        
        users = query.order_by(UserInDB.activity_points.desc()).limit(limit).all()
        results = [(u.id, u.activity_points or 0) for u in users]
    
    # Build response with user details
    entries = []
    user_ids = [r[0] for r in results]
    users_map = {u.id: u for u in db.query(UserInDB).filter(UserInDB.id.in_(user_ids)).all()}
    
    for rank, (user_id, points) in enumerate(results, start=1):
        user = users_map.get(user_id)
        if user:
            entries.append(LeaderboardEntry(
                user_id=user_id,
                user_name=user.name,
                avatar_url=user.avatar_url,
                points=int(points),
                rank=rank
            ))
            
    # Calculate total participants for the context
    # If filtered by group, count students in group
    # If all students, count all students
    total_participants = 0
    if group_id:
        total_participants = db.query(GroupStudent).filter(GroupStudent.group_id == group_id).count()
    else:
        total_participants = db.query(UserInDB).filter(UserInDB.role == 'student', UserInDB.is_active == True).count()
    
    return LeaderboardResponse(
        period=period,
        start_date=start_date,
        end_date=end_date,
        total_participants=total_participants,
        entries=entries
    )


@router.get("/history", response_model=List[PointHistorySchema])
async def get_point_history(
    limit: int = Query(50, le=100),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get current user's point history."""
    history = db.query(PointHistory).filter(
        PointHistory.user_id == current_user.id
    ).order_by(PointHistory.created_at.desc()).limit(limit).all()
    
    return history
