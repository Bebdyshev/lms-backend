"""
Script to fix quiz_attempts where total_questions doesn't match the actual number of gaps + questions.

The issue: total_questions was set to questions.length (number of question objects),
but score was calculated including each gap in fill_blank questions.
This caused percentages like 511% when there were 12 gaps in 1 question.

This script recalculates total_questions based on the quiz content.
"""

import json
import re
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.schemas.models import QuizAttempt, Step
from src.config import POSTGRES_URL


def extract_gaps_count(text: str) -> int:
    """Count the number of gaps [[...]] in fill_blank/text_completion questions"""
    if not text:
        return 0
    gaps = re.findall(r'\[\[.*?\]\]', text)
    return len(gaps)


def calculate_total_for_quiz(quiz_content: dict) -> int:
    """
    Calculate the total number of answerable items in a quiz.
    For fill_blank/text_completion questions, each gap counts as one item.
    For other questions, each question counts as one item.
    image_content questions are skipped (they're just visual content).
    """
    questions = quiz_content.get('questions', [])
    total = 0
    
    for question in questions:
        q_type = question.get('question_type', '')
        
        # Skip image_content - it's not a question
        if q_type == 'image_content':
            continue
        
        if q_type in ('fill_blank', 'text_completion'):
            # Count gaps in the text
            text = question.get('content_text') or question.get('question_text') or ''
            gaps = extract_gaps_count(text)
            total += gaps if gaps > 0 else 1  # At least 1 if no gaps found
        else:
            # Regular question counts as 1
            total += 1
    
    return total


def fix_quiz_attempts(dry_run: bool = True):
    """
    Fix all quiz attempts where total_questions might be incorrect.
    
    Args:
        dry_run: If True, only print what would be changed without making changes.
    """
    engine = create_engine(POSTGRES_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get all quiz attempts
        attempts = session.query(QuizAttempt).all()
        print(f"Found {len(attempts)} quiz attempts to check")
        
        fixed_count = 0
        skipped_count = 0
        error_count = 0
        
        for attempt in attempts:
            try:
                # Get the quiz step content
                step = session.query(Step).filter(Step.id == attempt.step_id).first()
                
                if not step or not step.content_text:
                    print(f"  Skipping attempt {attempt.id}: No quiz content found for step {attempt.step_id}")
                    skipped_count += 1
                    continue
                
                # Parse quiz content
                try:
                    quiz_content = json.loads(step.content_text)
                except json.JSONDecodeError:
                    print(f"  Skipping attempt {attempt.id}: Invalid JSON in step {attempt.step_id}")
                    skipped_count += 1
                    continue
                
                # Calculate correct total
                correct_total = calculate_total_for_quiz(quiz_content)
                
                if correct_total == 0:
                    print(f"  Skipping attempt {attempt.id}: Quiz has no questions")
                    skipped_count += 1
                    continue
                
                # Check if needs fixing
                if attempt.total_questions != correct_total:
                    old_percentage = attempt.score_percentage
                    new_percentage = (attempt.correct_answers / correct_total) * 100 if correct_total > 0 else 0
                    
                    # Cap correct_answers if it exceeds total (shouldn't happen but just in case)
                    correct_answers = min(attempt.correct_answers, correct_total)
                    new_percentage = (correct_answers / correct_total) * 100
                    
                    print(f"  Attempt {attempt.id} (user {attempt.user_id}, step {attempt.step_id}):")
                    print(f"    total_questions: {attempt.total_questions} -> {correct_total}")
                    print(f"    correct_answers: {attempt.correct_answers} -> {correct_answers}")
                    print(f"    score_percentage: {old_percentage:.1f}% -> {new_percentage:.1f}%")
                    
                    if not dry_run:
                        attempt.total_questions = correct_total
                        attempt.correct_answers = correct_answers
                        attempt.score_percentage = round(new_percentage, 2)
                    
                    fixed_count += 1
                    
            except Exception as e:
                print(f"  Error processing attempt {attempt.id}: {e}")
                error_count += 1
        
        if not dry_run:
            session.commit()
            print(f"\n✅ Committed changes to database")
        
        print(f"\n=== Summary ===")
        print(f"Total attempts checked: {len(attempts)}")
        print(f"Fixed: {fixed_count}")
        print(f"Skipped: {skipped_count}")
        print(f"Errors: {error_count}")
        
        if dry_run and fixed_count > 0:
            print(f"\n⚠️  This was a DRY RUN. No changes were made.")
            print(f"    Run with --apply to actually fix the records.")
            
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix quiz attempts with incorrect total_questions")
    parser.add_argument("--apply", action="store_true", help="Actually apply the fixes (default is dry run)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Quiz Attempts Total Questions Fix Script")
    print("=" * 60)
    
    if args.apply:
        print("Mode: APPLY (changes will be saved to database)")
        confirm = input("Are you sure? Type 'yes' to continue: ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
    else:
        print("Mode: DRY RUN (no changes will be made)")
    
    print()
    fix_quiz_attempts(dry_run=not args.apply)
