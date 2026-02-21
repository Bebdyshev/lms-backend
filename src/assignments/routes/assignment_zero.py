from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime
import os
import uuid

from src.config import get_db
from src.schemas.models import (
    UserInDB, AssignmentZeroSubmission, 
    AssignmentZeroSubmissionSchema, AssignmentZeroSubmitSchema,
    AssignmentZeroSaveProgressSchema, Group, GroupStudent
)
from src.routes.auth import get_current_user_dependency

router = APIRouter()

# Upload directory for Assignment Zero screenshots
UPLOAD_DIR = "uploads/assignment_zero"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# =============================================================================
# ASSIGNMENT ZERO ENDPOINTS
# =============================================================================

@router.get("/status")
async def get_assignment_zero_status(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Check if student needs to complete Assignment Zero"""
    # Only students need to complete Assignment Zero
    if current_user.role != "student":
        return {
            "needs_completion": False,
            "completed": True,
            "message": "Assignment Zero is only for students",
            "user_groups": []
        }
    
    # Check for draft submission
    draft = db.query(AssignmentZeroSubmission).filter(
        AssignmentZeroSubmission.user_id == current_user.id,
        AssignmentZeroSubmission.is_draft == True
    ).first()
    
    # Get user's groups with names
    user_group_students = db.query(GroupStudent).filter(
        GroupStudent.student_id == current_user.id
    ).all()
    
    user_groups = []
    for gs in user_group_students:
        group = db.query(Group).filter(Group.id == gs.group_id).first()
        if group:
            user_groups.append({
                "id": group.id,
                "name": group.name
            })
    
    return {
        "needs_completion": not current_user.assignment_zero_completed,
        "completed": current_user.assignment_zero_completed,
        "completed_at": current_user.assignment_zero_completed_at,
        "has_draft": draft is not None,
        "last_saved_step": draft.last_saved_step if draft else None,
        "user_groups": user_groups
    }

@router.get("/my-submission", response_model=AssignmentZeroSubmissionSchema)
async def get_my_assignment_zero_submission(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get current user's Assignment Zero submission (including draft)"""
    submission = db.query(AssignmentZeroSubmission).filter(
        AssignmentZeroSubmission.user_id == current_user.id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Assignment Zero submission not found")
    
    return AssignmentZeroSubmissionSchema.model_validate(submission)

@router.post("/save-progress", response_model=AssignmentZeroSubmissionSchema)
async def save_assignment_zero_progress(
    data: AssignmentZeroSaveProgressSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Save progress on Assignment Zero (auto-save)"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can save Assignment Zero progress")
    
    # Check if already fully submitted (not draft)
    existing = db.query(AssignmentZeroSubmission).filter(
        AssignmentZeroSubmission.user_id == current_user.id
    ).first()
    
    if existing and not existing.is_draft:
        raise HTTPException(status_code=400, detail="Assignment Zero already submitted")
    
    # Update or create draft
    if existing:
        # Update existing draft with non-None values
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(existing, field, value)
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return AssignmentZeroSubmissionSchema.model_validate(existing)
    else:
        # Create new draft submission with default required values
        draft = AssignmentZeroSubmission(
            user_id=current_user.id,
            full_name=data.full_name or current_user.name or "",
            phone_number=data.phone_number or "",
            parent_phone_number=data.parent_phone_number or "",
            telegram_id=data.telegram_id or "",
            email=data.email or current_user.email or "",
            college_board_email=data.college_board_email or "",
            college_board_password=data.college_board_password or "",
            birthday_date=data.birthday_date or datetime.now().date(),
            city=data.city or "",
            school_type=data.school_type or "",
            group_name=data.group_name or "",
            sat_target_date=data.sat_target_date or "",
            has_passed_sat_before=data.has_passed_sat_before or False,
            previous_sat_score=data.previous_sat_score,
            recent_practice_test_score=data.recent_practice_test_score or "",
            bluebook_practice_test_5_score=data.bluebook_practice_test_5_score or "",
            screenshot_url=data.screenshot_url,
            # SAT Assessment fields
            grammar_punctuation=data.grammar_punctuation,
            grammar_noun_clauses=data.grammar_noun_clauses,
            grammar_relative_clauses=data.grammar_relative_clauses,
            grammar_verb_forms=data.grammar_verb_forms,
            grammar_comparisons=data.grammar_comparisons,
            grammar_transitions=data.grammar_transitions,
            grammar_synthesis=data.grammar_synthesis,
            reading_word_in_context=data.reading_word_in_context,
            reading_text_structure=data.reading_text_structure,
            reading_cross_text=data.reading_cross_text,
            reading_central_ideas=data.reading_central_ideas,
            reading_inferences=data.reading_inferences,
            passages_literary=data.passages_literary,
            passages_social_science=data.passages_social_science,
            passages_humanities=data.passages_humanities,
            passages_science=data.passages_science,
            passages_poetry=data.passages_poetry,
            math_topics=data.math_topics,
            # IELTS fields
            ielts_target_date=data.ielts_target_date,
            has_passed_ielts_before=data.has_passed_ielts_before or False,
            previous_ielts_score=data.previous_ielts_score,
            ielts_target_score=data.ielts_target_score,
            ielts_listening_main_idea=data.ielts_listening_main_idea,
            ielts_listening_details=data.ielts_listening_details,
            ielts_listening_opinion=data.ielts_listening_opinion,
            ielts_listening_accents=data.ielts_listening_accents,
            ielts_reading_skimming=data.ielts_reading_skimming,
            ielts_reading_scanning=data.ielts_reading_scanning,
            ielts_reading_vocabulary=data.ielts_reading_vocabulary,
            ielts_reading_inference=data.ielts_reading_inference,
            ielts_reading_matching=data.ielts_reading_matching,
            ielts_writing_task1_graphs=data.ielts_writing_task1_graphs,
            ielts_writing_task1_process=data.ielts_writing_task1_process,
            ielts_writing_task2_structure=data.ielts_writing_task2_structure,
            ielts_writing_task2_arguments=data.ielts_writing_task2_arguments,
            ielts_writing_grammar=data.ielts_writing_grammar,
            ielts_writing_vocabulary=data.ielts_writing_vocabulary,
            ielts_speaking_fluency=data.ielts_speaking_fluency,
            ielts_speaking_vocabulary=data.ielts_speaking_vocabulary,
            ielts_speaking_grammar=data.ielts_speaking_grammar,
            ielts_speaking_pronunciation=data.ielts_speaking_pronunciation,
            ielts_speaking_part2=data.ielts_speaking_part2,
            ielts_speaking_part3=data.ielts_speaking_part3,
            ielts_weak_topics=data.ielts_weak_topics,
            additional_comments=data.additional_comments,
            # Draft status
            is_draft=True,
            last_saved_step=data.last_saved_step or 1
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return AssignmentZeroSubmissionSchema.model_validate(draft)

@router.post("/submit", response_model=AssignmentZeroSubmissionSchema)
async def submit_assignment_zero(
    data: AssignmentZeroSubmitSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Submit Assignment Zero questionnaire"""
    # Only students can submit
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit Assignment Zero")
    
    # Check if already submitted (not draft)
    existing = db.query(AssignmentZeroSubmission).filter(
        AssignmentZeroSubmission.user_id == current_user.id
    ).first()
    
    if existing and not existing.is_draft:
        raise HTTPException(status_code=400, detail="Assignment Zero already submitted")
    
    if existing:
        # Update existing draft to final submission
        existing.full_name = data.full_name
        existing.phone_number = data.phone_number
        existing.parent_phone_number = data.parent_phone_number
        existing.telegram_id = data.telegram_id
        existing.email = data.email
        existing.college_board_email = data.college_board_email
        existing.college_board_password = data.college_board_password
        existing.birthday_date = data.birthday_date
        existing.city = data.city
        existing.school_type = data.school_type
        existing.group_name = data.group_name
        existing.sat_target_date = data.sat_target_date
        existing.has_passed_sat_before = data.has_passed_sat_before
        existing.previous_sat_score = data.previous_sat_score
        existing.recent_practice_test_score = data.recent_practice_test_score
        existing.bluebook_practice_test_5_score = data.bluebook_practice_test_5_score
        existing.screenshot_url = data.screenshot_url
        # SAT Assessment fields
        existing.grammar_punctuation = data.grammar_punctuation
        existing.grammar_noun_clauses = data.grammar_noun_clauses
        existing.grammar_relative_clauses = data.grammar_relative_clauses
        existing.grammar_verb_forms = data.grammar_verb_forms
        existing.grammar_comparisons = data.grammar_comparisons
        existing.grammar_transitions = data.grammar_transitions
        existing.grammar_synthesis = data.grammar_synthesis
        existing.reading_word_in_context = data.reading_word_in_context
        existing.reading_text_structure = data.reading_text_structure
        existing.reading_cross_text = data.reading_cross_text
        existing.reading_central_ideas = data.reading_central_ideas
        existing.reading_inferences = data.reading_inferences
        existing.passages_literary = data.passages_literary
        existing.passages_social_science = data.passages_social_science
        existing.passages_humanities = data.passages_humanities
        existing.passages_science = data.passages_science
        existing.passages_poetry = data.passages_poetry
        existing.math_topics = data.math_topics
        # IELTS fields
        existing.ielts_target_date = data.ielts_target_date
        existing.has_passed_ielts_before = data.has_passed_ielts_before
        existing.previous_ielts_score = data.previous_ielts_score
        existing.ielts_target_score = data.ielts_target_score
        existing.ielts_listening_main_idea = data.ielts_listening_main_idea
        existing.ielts_listening_details = data.ielts_listening_details
        existing.ielts_listening_opinion = data.ielts_listening_opinion
        existing.ielts_listening_accents = data.ielts_listening_accents
        existing.ielts_reading_skimming = data.ielts_reading_skimming
        existing.ielts_reading_scanning = data.ielts_reading_scanning
        existing.ielts_reading_vocabulary = data.ielts_reading_vocabulary
        existing.ielts_reading_inference = data.ielts_reading_inference
        existing.ielts_reading_matching = data.ielts_reading_matching
        existing.ielts_writing_task1_graphs = data.ielts_writing_task1_graphs
        existing.ielts_writing_task1_process = data.ielts_writing_task1_process
        existing.ielts_writing_task2_structure = data.ielts_writing_task2_structure
        existing.ielts_writing_task2_arguments = data.ielts_writing_task2_arguments
        existing.ielts_writing_grammar = data.ielts_writing_grammar
        existing.ielts_writing_vocabulary = data.ielts_writing_vocabulary
        existing.ielts_speaking_fluency = data.ielts_speaking_fluency
        existing.ielts_speaking_vocabulary = data.ielts_speaking_vocabulary
        existing.ielts_speaking_grammar = data.ielts_speaking_grammar
        existing.ielts_speaking_pronunciation = data.ielts_speaking_pronunciation
        existing.ielts_speaking_part2 = data.ielts_speaking_part2
        existing.ielts_speaking_part3 = data.ielts_speaking_part3
        existing.ielts_weak_topics = data.ielts_weak_topics
        existing.additional_comments = data.additional_comments
        # Mark as submitted
        existing.is_draft = False
        existing.updated_at = datetime.utcnow()
        
        submission = existing
    else:
        # Create new submission
        submission = AssignmentZeroSubmission(
            user_id=current_user.id,
            full_name=data.full_name,
            phone_number=data.phone_number,
            parent_phone_number=data.parent_phone_number,
            telegram_id=data.telegram_id,
            email=data.email,
            college_board_email=data.college_board_email,
            college_board_password=data.college_board_password,
            birthday_date=data.birthday_date,
            city=data.city,
            school_type=data.school_type,
            group_name=data.group_name,
            sat_target_date=data.sat_target_date,
            has_passed_sat_before=data.has_passed_sat_before,
            previous_sat_score=data.previous_sat_score,
            recent_practice_test_score=data.recent_practice_test_score,
            bluebook_practice_test_5_score=data.bluebook_practice_test_5_score,
            screenshot_url=data.screenshot_url,
            # SAT Assessment fields
            grammar_punctuation=data.grammar_punctuation,
            grammar_noun_clauses=data.grammar_noun_clauses,
            grammar_relative_clauses=data.grammar_relative_clauses,
            grammar_verb_forms=data.grammar_verb_forms,
            grammar_comparisons=data.grammar_comparisons,
            grammar_transitions=data.grammar_transitions,
            grammar_synthesis=data.grammar_synthesis,
            reading_word_in_context=data.reading_word_in_context,
            reading_text_structure=data.reading_text_structure,
            reading_cross_text=data.reading_cross_text,
            reading_central_ideas=data.reading_central_ideas,
            reading_inferences=data.reading_inferences,
            passages_literary=data.passages_literary,
            passages_social_science=data.passages_social_science,
            passages_humanities=data.passages_humanities,
            passages_science=data.passages_science,
            passages_poetry=data.passages_poetry,
            math_topics=data.math_topics,
            # IELTS fields
            ielts_target_date=data.ielts_target_date,
            has_passed_ielts_before=data.has_passed_ielts_before,
            previous_ielts_score=data.previous_ielts_score,
            ielts_target_score=data.ielts_target_score,
            ielts_listening_main_idea=data.ielts_listening_main_idea,
            ielts_listening_details=data.ielts_listening_details,
            ielts_listening_opinion=data.ielts_listening_opinion,
            ielts_listening_accents=data.ielts_listening_accents,
            ielts_reading_skimming=data.ielts_reading_skimming,
            ielts_reading_scanning=data.ielts_reading_scanning,
            ielts_reading_vocabulary=data.ielts_reading_vocabulary,
            ielts_reading_inference=data.ielts_reading_inference,
            ielts_reading_matching=data.ielts_reading_matching,
            ielts_writing_task1_graphs=data.ielts_writing_task1_graphs,
            ielts_writing_task1_process=data.ielts_writing_task1_process,
            ielts_writing_task2_structure=data.ielts_writing_task2_structure,
            ielts_writing_task2_arguments=data.ielts_writing_task2_arguments,
            ielts_writing_grammar=data.ielts_writing_grammar,
            ielts_writing_vocabulary=data.ielts_writing_vocabulary,
            ielts_speaking_fluency=data.ielts_speaking_fluency,
            ielts_speaking_vocabulary=data.ielts_speaking_vocabulary,
            ielts_speaking_grammar=data.ielts_speaking_grammar,
            ielts_speaking_pronunciation=data.ielts_speaking_pronunciation,
            ielts_speaking_part2=data.ielts_speaking_part2,
            ielts_speaking_part3=data.ielts_speaking_part3,
            ielts_weak_topics=data.ielts_weak_topics,
            additional_comments=data.additional_comments,
            # Mark as submitted
            is_draft=False
        )
        db.add(submission)
    
    # Update user's assignment_zero_completed status
    current_user.assignment_zero_completed = True
    current_user.assignment_zero_completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(submission)
    
    return AssignmentZeroSubmissionSchema.model_validate(submission)

@router.post("/upload-screenshot")
async def upload_screenshot(
    file: UploadFile = File(...),
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Upload screenshot for Assignment Zero"""
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can upload screenshots")
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only image files are allowed (JPEG, PNG, GIF, WEBP)")
    
    # Validate file size (max 10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 10MB")
    
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ".png"
    unique_filename = f"{current_user.id}_{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Return the URL
    file_url = f"/uploads/assignment_zero/{unique_filename}"
    
    return {"url": file_url, "filename": unique_filename}

# =============================================================================
# ADMIN/TEACHER ENDPOINTS
# =============================================================================

@router.get("/submissions", response_model=list[AssignmentZeroSubmissionSchema])
async def get_all_submissions(
    group_name: str | None = None,
    skip: int = 0,
    limit: int = 100,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get all Assignment Zero submissions (admin/teacher only)"""
    if current_user.role not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = db.query(AssignmentZeroSubmission)
    
    if group_name:
        query = query.filter(AssignmentZeroSubmission.group_name == group_name)
    
    submissions = query.offset(skip).limit(limit).all()
    
    return [AssignmentZeroSubmissionSchema.model_validate(s) for s in submissions]

@router.get("/submissions/{user_id}", response_model=AssignmentZeroSubmissionSchema)
async def get_submission_by_user(
    user_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """Get Assignment Zero submission for a specific user (admin/teacher only)"""
    if current_user.role not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    submission = db.query(AssignmentZeroSubmission).filter(
        AssignmentZeroSubmission.user_id == user_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    return AssignmentZeroSubmissionSchema.model_validate(submission)
