"""AI Tools routes - Dictionary lookup with Gemini."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import google.generativeai as genai
import json
import os

from src.schemas.models import UserInDB
from src.routes.auth import get_current_user_dependency
from src.config import get_db

router = APIRouter()

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# =============================================================================
# SCHEMAS
# =============================================================================

class LookupRequest(BaseModel):
    text: str  # The word or phrase to look up
    context_sentence: Optional[str] = None  # Optional surrounding context


class LookupResponse(BaseModel):
    word: str
    phonetic: Optional[str] = None
    part_of_speech: Optional[str] = None
    definition_en: str
    translation_ru: str
    synonyms: List[str] = []
    usage_example: Optional[str] = None
    etymology: Optional[str] = None


# =============================================================================
# GEMINI LOOKUP SERVICE
# =============================================================================

class GeminiLookupService:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash')
    
    async def lookup_word(self, text: str, context: Optional[str] = None) -> dict:
        """Look up a word/phrase using Gemini to generate dictionary-like response."""
        
        context_hint = ""
        if context:
            context_hint = f'\nThe word appears in this context: "{context}"'
        
        prompt = f"""You are a dictionary service. Analyze the following word or phrase and return a JSON object with dictionary information.

Word/Phrase: "{text}"{context_hint}

Return a JSON object with these fields:
- word: the word being defined (string)
- phonetic: IPA pronunciation (string, e.g., "/ˌedʒuˈkeɪʃən/")
- part_of_speech: noun, verb, adjective, etc. (string)
- definition_en: clear English definition (string)
- translation_ru: Russian translation (string)
- synonyms: list of 3-5 English synonyms (array of strings)
- usage_example: an example sentence using the word (string)
- etymology: brief origin of the word (string, optional)

Return ONLY valid JSON, no markdown formatting.
"""
        
        try:
            response = self.model.generate_content(prompt)
            
            if not response or not response.text:
                raise Exception("No response from Gemini")
            
            # Clean response
            text_response = response.text.strip()
            if text_response.startswith("```json"):
                text_response = text_response[7:]
            if text_response.startswith("```"):
                text_response = text_response[3:]
            if text_response.endswith("```"):
                text_response = text_response[:-3]
            text_response = text_response.strip()
            
            result = json.loads(text_response)
            return result
            
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            # Return a basic fallback
            return {
                "word": text,
                "definition_en": "Definition not available",
                "translation_ru": "Перевод недоступен",
                "synonyms": []
            }
        except Exception as e:
            print(f"Gemini lookup error: {e}")
            raise


lookup_service = GeminiLookupService()


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/lookup", response_model=LookupResponse)
async def lookup_word(
    request: LookupRequest,
    current_user: UserInDB = Depends(get_current_user_dependency),
    db: Session = Depends(get_db)
):
    """
    Look up a word or phrase using AI.
    Returns definition, translation, synonyms, and usage examples.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service not configured"
        )
    
    if not request.text or len(request.text.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text to look up is required"
        )
    
    # Limit text length
    if len(request.text) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text too long (max 100 characters)"
        )
    
    try:
        result = await lookup_service.lookup_word(
            text=request.text.strip(),
            context=request.context_sentence
        )
        
        return LookupResponse(
            word=result.get("word", request.text),
            phonetic=result.get("phonetic"),
            part_of_speech=result.get("part_of_speech"),
            definition_en=result.get("definition_en", ""),
            translation_ru=result.get("translation_ru", ""),
            synonyms=result.get("synonyms", []),
            usage_example=result.get("usage_example"),
            etymology=result.get("etymology")
        )
        
    except Exception as e:
        print(f"Lookup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to look up word"
        )
