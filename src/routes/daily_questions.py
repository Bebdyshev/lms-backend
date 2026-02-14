from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime, date, timezone
import httpx
import os
import logging

from ..config import get_db
from ..schemas.models import UserInDB, DailyQuestionCompletion
from .auth import get_current_user_dependency

router = APIRouter()
logger = logging.getLogger(__name__)

# External API config
MASTER_ED_API_URL = "https://api.mastereducation.kz/api/lms/students/question-recommendations"
MASTER_ED_API_KEY = os.getenv("MASTER_ED_API_KEY", "LMS_MasterEd_2025_SecureKey_XyZ789")
MASTER_ED_BASE_URL = "https://api.mastereducation.kz/api"

# Log configuration on module load
logger.info(f"Daily questions API configured:")
logger.info(f"  URL: {MASTER_ED_API_URL}")
logger.info(f"  API Key: {'***' + MASTER_ED_API_KEY[-10:] if MASTER_ED_API_KEY else 'NOT SET'}")
logger.info(f"  Base URL: {MASTER_ED_BASE_URL}")


# =============================================================================
# SCHEMAS
# =============================================================================

class DailyQuestionItem(BaseModel):
    questionId: int
    text: str
    imageUrl: Optional[str] = None
    primaryTag: str
    secondaryTags: Optional[Any] = None
    difficulty: str


class RecommendationSection(BaseModel):
    questions: List[DailyQuestionItem]
    reasoning: str


class DailyQuestionsResponse(BaseModel):
    email: str
    studentName: str
    mathTestId: Optional[int] = None
    verbalTestId: Optional[int] = None
    mathRecommendations: Optional[RecommendationSection] = None
    verbalRecommendations: Optional[RecommendationSection] = None


class DailyQuestionsStatusResponse(BaseModel):
    completed_today: bool
    completed_at: Optional[str] = None


class CompleteDailyQuestionsRequest(BaseModel):
    questions_data: Optional[dict] = None  # Optional: store which questions were answered


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status")
async def get_daily_questions_status(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Check if the student has completed daily questions today."""
    if current_user.role != "student":
        return {"completed_today": True, "message": "Daily questions are only for students"}

    today = date.today()
    completion = db.query(DailyQuestionCompletion).filter(
        DailyQuestionCompletion.user_id == current_user.id,
        DailyQuestionCompletion.completed_date == today
    ).first()

    return {
        "completed_today": completion is not None,
        "completed_at": completion.created_at.isoformat() if completion else None
    }


@router.get("/recommendations")
async def get_daily_question_recommendations(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Fetch personalized question recommendations for the student from external API."""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access daily questions")

    logger.info(f"Fetching recommendations for {current_user.email}")
    
    # Retry logic with increased timeout
    max_retries = 2
    timeout = 30.0  # Increased from 15 to 30 seconds
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                logger.info(f"Making request to {MASTER_ED_API_URL} (attempt {attempt + 1}/{max_retries})")
                response = await client.post(
                    MASTER_ED_API_URL,
                    json={"email": current_user.email},
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": MASTER_ED_API_KEY
                    }
                )
                logger.info(f"Response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"External API error: {response.status_code} - {response.text}")
                
                # Handle specific error cases
                if response.status_code == 404:
                    error_detail = response.json().get("error", "Student not found")
                    raise HTTPException(
                        status_code=404,
                        detail=f"No recommendations available: {error_detail}. Please complete your assessment tests first."
                    )
                
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to fetch recommendations from external service: {response.text}"
                )

            data = response.json()

            # Debug logging for specific user
            if current_user.email == "nurassylzhunussov@gmail.com":
                logger.info(f"DEBUG - Raw API response for {current_user.email}:")
                logger.info(f"Math questions: {data.get('mathRecommendations', {}).get('questions', [])}")
                logger.info(f"Verbal questions: {data.get('verbalRecommendations', {}).get('questions', [])}")

            # Prepend base URL to image URLs and clean up None values
            if data.get("mathRecommendations") and data["mathRecommendations"].get("questions"):
                for q in data["mathRecommendations"]["questions"]:
                    if q.get("imageUrl") and q["imageUrl"] != "None":
                        q["imageUrl"] = f"{MASTER_ED_BASE_URL}{q['imageUrl']}"
                    else:
                        q["imageUrl"] = None  # Convert string "None" to actual None

            if data.get("verbalRecommendations") and data["verbalRecommendations"].get("questions"):
                for q in data["verbalRecommendations"]["questions"]:
                    if q.get("imageUrl") and q["imageUrl"] != "None":
                        q["imageUrl"] = f"{MASTER_ED_BASE_URL}{q['imageUrl']}"
                    else:
                        q["imageUrl"] = None  # Convert string "None" to actual None

            # More debug logging after URL prepending
            if current_user.email == "nurassylzhunussov@gmail.com":
                logger.info(f"DEBUG - After URL processing for {current_user.email}:")
                if data.get("mathRecommendations"):
                    for idx, q in enumerate(data["mathRecommendations"]["questions"]):
                        logger.info(f"Math Q{idx+1}: text='{q.get('text')}', imageUrl='{q.get('imageUrl')}'")
                if data.get("verbalRecommendations"):
                    for idx, q in enumerate(data["verbalRecommendations"]["questions"]):
                        logger.info(f"Verbal Q{idx+1}: text='{q.get('text')}', imageUrl='{q.get('imageUrl')}'")

            # Success - return data
            logger.info(f"Successfully fetched recommendations for {current_user.email}")
            return data

        except httpx.ReadTimeout:
            logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries} for {current_user.email}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying...")
                continue
            else:
                logger.error(f"All {max_retries} attempts failed due to timeout")
                raise HTTPException(
                    status_code=504,
                    detail="The recommendations service is taking too long to respond. Please try again later."
                )

        except httpx.RequestError as e:
            logger.error(f"Request error fetching recommendations: {type(e).__name__}: {str(e)}")
            logger.error(f"Full error details: {repr(e)}")
            raise HTTPException(
                status_code=502,
                detail=f"Could not connect to recommendations service: {str(e)}"
            )

    # This should never be reached due to the loop logic, but for safety:
    raise HTTPException(
        status_code=500,
        detail="Internal error: retry loop exited unexpectedly"
    )


@router.post("/complete")
async def complete_daily_questions(
    request: CompleteDailyQuestionsRequest,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Mark daily questions as completed for today."""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can complete daily questions")

    today = date.today()

    # Check if already completed today
    existing = db.query(DailyQuestionCompletion).filter(
        DailyQuestionCompletion.user_id == current_user.id,
        DailyQuestionCompletion.completed_date == today
    ).first()

    if existing:
        return {"message": "Daily questions already completed today", "completed_today": True}

    completion = DailyQuestionCompletion(
        user_id=current_user.id,
        completed_date=today,
        questions_data=request.questions_data,
        created_at=datetime.now(timezone.utc)
    )
    db.add(completion)
    db.commit()

    return {"message": "Daily questions completed!", "completed_today": True}
