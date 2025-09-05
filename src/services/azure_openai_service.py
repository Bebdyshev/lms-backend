import base64
import io
from typing import Dict, List, Optional
import logging
import traceback
from openai import AzureOpenAI
from PIL import Image
import os
from src.config import AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_NAME
from pydantic import BaseModel

class SatOption(BaseModel):
    letter: str
    text: str

class SatAnalysisResult(BaseModel):
    question_text: str
    content_text: str
    options: list[SatOption]
    correct_answer: str
    explanation: str
    question_type: str

class AzureOpenAIService:
    def __init__(self):
        self.logger = logging.getLogger("azure_openai_service")
        self.client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version="2024-10-21"
        )
        self.deployment_name = AZURE_OPENAI_DEPLOYMENT_NAME

    def encode_image_to_base64(self, image_path: str) -> str:
        """Encode image to base64 string"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def encode_pil_image_to_base64(self, image: Image.Image) -> str:
        """Encode PIL Image to base64 string"""
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    async def analyze_sat_image(self, image_path: str) -> Dict:
        """
        Analyze SAT question image using Azure OpenAI Vision API
        Returns structured SAT question data
        """
        try:
            # Encode image to base64
            base64_image = self.encode_image_to_base64(image_path)
            
            # Prepare the prompt for SAT question analysis
            prompt = """
            Analyze this SAT question image and extract the following information in JSON format:
            
            {
                "question_text": "The main question text",
                "content_text": "The full content/passage/text that the question is based on",
                "options": [
                    {"letter": "A", "text": "Option A text"},
                    {"letter": "B", "text": "Option B text"},
                    {"letter": "C", "text": "Option C text"},
                    {"letter": "D", "text": "Option D text"}
                ],
                "correct_answer": "A",
                "explanation": "Brief explanation of why this answer is correct",
                "question_type": "single_choice"
            }
            
            Important:
            - Extract the exact question text
            - Extract the full content/passage/text that the question is based on (if present)
            - Identify all multiple choice options (A, B, C, D)
            - Determine the correct answer based on the image content
            - Provide a brief explanation for the correct answer
            - If you cannot determine the correct answer, mark it as "A" and note this in explanation
            - Return only valid JSON, no additional text
            """
            
            # Prefer structured outputs with parsed Pydantic model when supported
            try:
                completion = self.client.beta.chat.completions.parse(
                    model=self.deployment_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    response_format=SatAnalysisResult,
                    temperature=0.1,
                )
                parsed = completion.choices[0].message.parsed
                # Log parsed structure for debugging
                try:
                    self.logger.debug("Structured SAT parse succeeded: %s", parsed.model_dump())
                except Exception:
                    pass
                # Convert parsed model into our expected dict
                return {
                    "question_text": parsed.question_text,
                    "content_text": parsed.content_text,
                    "options": [o.model_dump() for o in parsed.options],
                    "correct_answer": parsed.correct_answer,
                    "explanation": parsed.explanation,
                    "question_type": parsed.question_type,
                    "success": True,
                    "raw_response": getattr(getattr(completion.choices[0].message, "content", None), "__str__", lambda: "")(),
                }
            except Exception:
                # Fallback to plain completion and regex JSON extraction
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=1000,
                    temperature=0.1,
                )
                content = response.choices[0].message.content
                # Log raw content before parsing
                try:
                    self.logger.debug("SAT completion raw content: %s", content)
                except Exception:
                    pass
            
            # Try to extract JSON from the response
            import json
            import re
            
            # Look for JSON in the response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                result = json.loads(json_str)
                
                # Validate and structure the result
                return {
                    "question_text": result.get("question_text", ""),
                    "content_text": result.get("content_text", ""),
                    "options": result.get("options", []),
                    "correct_answer": result.get("correct_answer", "A"),
                    "explanation": result.get("explanation", ""),
                    "question_type": result.get("question_type", "single_choice"),
                    "success": True,
                    "raw_response": content,
                }
            else:
                # Fallback: try to extract information manually
                return {
                    "question_text": "Could not extract question text from image",
                    "content_text": "Could not extract content text from image",
                    "options": [
                        {"letter": "A", "text": "Option A"},
                        {"letter": "B", "text": "Option B"},
                        {"letter": "C", "text": "Option C"},
                        {"letter": "D", "text": "Option D"}
                    ],
                    "correct_answer": "A",
                    "explanation": "Could not determine correct answer from image",
                    "question_type": "single_choice",
                    "success": False,
                    "raw_response": content
                }
                
        except Exception as e:
            # Log stack trace to help diagnose
            try:
                self.logger.error("SAT analysis error: %s\n%s", str(e), traceback.format_exc())
            except Exception:
                pass
            return {
                "question_text": "Error analyzing image",
                "content_text": "Error analyzing image content",
                "options": [
                    {"letter": "A", "text": "Option A"},
                    {"letter": "B", "text": "Option B"},
                    {"letter": "C", "text": "Option C"},
                    {"letter": "D", "text": "Option D"}
                ],
                "correct_answer": "A",
                "explanation": f"Error: {str(e)}",
                "question_type": "single_choice",
                "success": False,
                "error": str(e),
                "raw_response": None
            }

    async def analyze_sat_image_from_bytes(self, image_bytes: bytes) -> Dict:
        """
        Analyze SAT question image from bytes using Azure OpenAI Vision API
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Encode to base64
            base64_image = self.encode_pil_image_to_base64(image)
            
            # Use the same analysis logic
            prompt = """
            Analyze this SAT question image and extract the following information in JSON format:
            
            {
                "question_text": "The main question text",
                "content_text": "The full content/passage/text that the question is based on",
                "options": [
                    {"letter": "A", "text": "Option A text"},
                    {"letter": "B", "text": "Option B text"},
                    {"letter": "C", "text": "Option C text"},
                    {"letter": "D", "text": "Option D text"}
                ],
                "correct_answer": "A",
                "explanation": "Brief explanation of why this answer is correct",
                "question_type": "single_choice"
            }
            
            Important:
            - Extract the exact question text
            - Extract the full content/passage/text that the question is based on (if present)
            - Identify all multiple choice options (A, B, C, D)
            - Determine the correct answer based on the image content
            - Provide a brief explanation for the correct answer
            - If you cannot determine the correct answer, mark it as "A" and note this in explanation
            - Return only valid JSON, no additional text
            """
            
            try:
                completion = self.client.beta.chat.completions.parse(
                    model=self.deployment_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    response_format=SatAnalysisResult,
                    temperature=0.1,
                )
                parsed = completion.choices[0].message.parsed
                return {
                    "question_text": parsed.question_text,
                    "content_text": parsed.content_text,
                    "options": [o.model_dump() for o in parsed.options],
                    "correct_answer": parsed.correct_answer,
                    "explanation": parsed.explanation,
                    "question_type": parsed.question_type,
                    "success": True,
                    "raw_response": getattr(getattr(completion.choices[0].message, "content", None), "__str__", lambda: "")(),
                }
            except Exception:
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=1000,
                    temperature=0.1,
                )
                content = response.choices[0].message.content
                try:
                    self.logger.debug("SAT completion raw content (bytes input): %s", content)
                except Exception:
                    pass
            
            import json
            import re
            
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                result = json.loads(json_str)
                
                return {
                    "question_text": result.get("question_text", ""),
                    "content_text": result.get("content_text", ""),
                    "options": result.get("options", []),
                    "correct_answer": result.get("correct_answer", "A"),
                    "explanation": result.get("explanation", ""),
                    "question_type": result.get("question_type", "single_choice"),
                    "success": True,
                    "raw_response": content,
                }
            else:
                return {
                    "question_text": "Could not extract question text from image",
                    "content_text": "Could not extract content text from image",
                    "options": [
                        {"letter": "A", "text": "Option A"},
                        {"letter": "B", "text": "Option B"},
                        {"letter": "C", "text": "Option C"},
                        {"letter": "D", "text": "Option D"}
                    ],
                    "correct_answer": "A",
                    "explanation": "Could not determine correct answer from image",
                    "question_type": "single_choice",
                    "success": False,
                    "raw_response": content
                }
                
        except Exception as e:
            return {
                "question_text": "Error analyzing image",
                "content_text": "Error analyzing image content",
                "options": [
                    {"letter": "A", "text": "Option A"},
                    {"letter": "B", "text": "Option B"},
                    {"letter": "C", "text": "Option C"},
                    {"letter": "D", "text": "Option D"}
                ],
                "correct_answer": "A",
                "explanation": f"Error: {str(e)}",
                "question_type": "single_choice",
                "success": False,
                "error": str(e),
                "raw_response": None
            }
