"""Flashcards routes for managing favorite flashcards."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json

from src.schemas.models import (
    FavoriteFlashcard,
    FavoriteFlashcardSchema,
    FavoriteFlashcardCreateSchema,
    UserInDB,
)
from src.routes.auth import get_current_user_dependency
from src.config import get_db

router = APIRouter()


@router.post("/favorites", response_model=FavoriteFlashcardSchema, status_code=status.HTTP_201_CREATED)
async def add_favorite_flashcard(
    favorite: FavoriteFlashcardCreateSchema,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Add a flashcard to user's favorites.
    
    Args:
        favorite: Flashcard data to add to favorites
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Created favorite flashcard
        
    Raises:
        HTTPException: If flashcard already exists in favorites
    """
    # Check if already favorited
    existing = db.query(FavoriteFlashcard).filter(
        FavoriteFlashcard.user_id == current_user.id,
        FavoriteFlashcard.step_id == favorite.step_id,
        FavoriteFlashcard.flashcard_id == favorite.flashcard_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Flashcard already in favorites"
        )
    
    # Validate flashcard_data is valid JSON
    try:
        json.loads(favorite.flashcard_data)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid flashcard data format"
        )
    
    # Create favorite
    db_favorite = FavoriteFlashcard(
        user_id=current_user.id,
        step_id=favorite.step_id,
        flashcard_id=favorite.flashcard_id,
        lesson_id=favorite.lesson_id,
        course_id=favorite.course_id,
        flashcard_data=favorite.flashcard_data
    )
    
    db.add(db_favorite)
    db.commit()
    db.refresh(db_favorite)
    
    return db_favorite


@router.get("/favorites", response_model=List[FavoriteFlashcardSchema])
async def get_favorite_flashcards(
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get all favorite flashcards for current user.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        List of favorite flashcards
    """
    favorites = db.query(FavoriteFlashcard).filter(
        FavoriteFlashcard.user_id == current_user.id
    ).order_by(FavoriteFlashcard.created_at.desc()).all()
    
    return favorites


@router.get("/favorites/{favorite_id}", response_model=FavoriteFlashcardSchema)
async def get_favorite_flashcard(
    favorite_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Get a specific favorite flashcard.
    
    Args:
        favorite_id: ID of the favorite flashcard
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Favorite flashcard
        
    Raises:
        HTTPException: If flashcard not found
    """
    favorite = db.query(FavoriteFlashcard).filter(
        FavoriteFlashcard.id == favorite_id,
        FavoriteFlashcard.user_id == current_user.id
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite flashcard not found"
        )
    
    return favorite


@router.delete("/favorites/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite_flashcard(
    favorite_id: int,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Remove a flashcard from favorites.
    
    Args:
        favorite_id: ID of the favorite flashcard to remove
        current_user: Current authenticated user
        db: Database session
        
    Raises:
        HTTPException: If flashcard not found
    """
    favorite = db.query(FavoriteFlashcard).filter(
        FavoriteFlashcard.id == favorite_id,
        FavoriteFlashcard.user_id == current_user.id
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite flashcard not found"
        )
    
    db.delete(favorite)
    db.commit()
    
    return None


@router.delete("/favorites/by-card/{step_id}/{flashcard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite_by_card_id(
    step_id: int,
    flashcard_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Remove a flashcard from favorites by step_id and flashcard_id.
    This is useful when you want to unfavorite from the flashcard viewer.
    
    Args:
        step_id: ID of the step containing the flashcard
        flashcard_id: ID of the flashcard within the set
        current_user: Current authenticated user
        db: Database session
        
    Raises:
        HTTPException: If flashcard not found
    """
    favorite = db.query(FavoriteFlashcard).filter(
        FavoriteFlashcard.user_id == current_user.id,
        FavoriteFlashcard.step_id == step_id,
        FavoriteFlashcard.flashcard_id == flashcard_id
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite flashcard not found"
        )
    
    db.delete(favorite)
    db.commit()
    
    return None


@router.get("/favorites/check/{step_id}/{flashcard_id}")
async def check_is_favorite(
    step_id: int,
    flashcard_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Check if a flashcard is in user's favorites.
    
    Args:
        step_id: ID of the step containing the flashcard
        flashcard_id: ID of the flashcard within the set
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Dictionary with is_favorite boolean
    """
    favorite = db.query(FavoriteFlashcard).filter(
        FavoriteFlashcard.user_id == current_user.id,
        FavoriteFlashcard.step_id == step_id,
        FavoriteFlashcard.flashcard_id == flashcard_id
    ).first()
    
    return {"is_favorite": favorite is not None, "favorite_id": favorite.id if favorite else None}
