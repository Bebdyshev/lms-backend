import google.generativeai as genai
import json
import os
from typing import List, Dict, Any, Optional
import mimetypes

# Configure Gemini
# In a real app, this should be in environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

class GeminiParser:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    async def parse_file(self, file_path: str, mime_type: str = None, correct_answers: str = None) -> List[Dict[str, Any]]:
        """
        Parse a file (PDF or Image) using Gemini to extract quiz questions.
        Returns a list of dictionaries compatible with the QuizQuestion model.
        
        Args:
            file_path: Path to the file to parse
            mime_type: MIME type of the file
            correct_answers: Optional string with manual correct answers (e.g., "1.A 2.B 3.C" or "A,B,C,D")
        """
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(file_path)
            
        if not mime_type:
            raise ValueError("Could not determine mime type of the file")

        # Upload the file to Gemini
        # Note: For larger files or production, we might want to manage file lifecycle better
        # (e.g., deleting them after processing).
        # For now, we assume the file is locally available at file_path.
        
        try:
            # Upload file with retry logic
            max_retries = 3
            retry_delay = 1  # Start with 1 second
            
            uploaded_file = None
            for attempt in range(max_retries):
                try:
                    uploaded_file = genai.upload_file(file_path, mime_type=mime_type)
                    print(f"File uploaded successfully on attempt {attempt + 1}")
                    break
                except Exception as upload_error:
                    if attempt < max_retries - 1:
                        print(f"Upload attempt {attempt + 1} failed: {upload_error}. Retrying in {retry_delay}s...")
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise Exception(f"Failed to upload file after {max_retries} attempts: {upload_error}")
            
            if not uploaded_file:
                raise Exception("File upload failed")
            
            # Build the prompt
            prompt = """
            Analyze this document and extract all quiz questions from it.
            Return the result as a JSON array of objects.
            
            Each object should have the following fields:
            - question_text: The text of the question.
            - question_type: Determine the question type based on the question format:
              * "single_choice" - Multiple choice with one correct answer (A, B, C, D options)
              * "multiple_choice" - Multiple choice with multiple correct answers
              * "short_answer" - Short text answer expected
              * "media_question" - Question that includes an image/diagram
              * "media_open_question" - Open-ended question with media attachment
            - options: An array of 4 strings representing the answer choices (for single_choice/multiple_choice only).
            - correct_answer: The index (0-3) of the correct answer for MCQ, or empty string for open questions.
            - explanation: A brief explanation of why the answer is correct (if available or inferable).
            - content_text: If the question refers to a reading passage, include the passage text here.
            - is_sat_question: Set to true.
            
            IMPORTANT - LaTeX Formatting Rules:
            - ALL mathematical expressions MUST be wrapped in $...$ (inline) or $$...$$ (display)
            - Fractions: use $\\frac{numerator}{denominator}$ (e.g., $\\frac{1}{2}$)
            - Exponents: use $x^2$, $x^{10}$
            - Subscripts: use $x_1$, $x_{10}$
            - Square roots: use $\\sqrt{x}$ or $\\sqrt[n]{x}$
            - Systems of equations: use $\\begin{cases} equation1 \\\\ equation2 \\end{cases}$
            - Greek letters: use $\\alpha$, $\\beta$, $\\pi$, etc.
            - Summation: use $\\sum_{i=1}^{n}$
            - Integration: use $\\int_{a}^{b}$
            - Examples:
              * "The value of $\\frac{3}{4}$ is greater than $\\frac{1}{2}$"
              * "Solve for $x$: $x^2 + 5x + 6 = 0$"
              * "System: $\\begin{cases} x + y = 5 \\\\ x - y = 1 \\end{cases}$"
            
            Format the output as a valid JSON string. Do not include markdown formatting like ```json ... ```.
            If an image is required to answer a question, add a field "needs_image": true.
            """
            
            # Add correct answers instruction if provided
            if correct_answers and correct_answers.strip():
                prompt += f"""
            
            CORRECT ANSWERS PROVIDED:
            {correct_answers}
            
            Use these correct answers when setting the "correct_answer" field for each question.
            Parse the format intelligently (e.g., "1.A 2.B" or "A,B,C,D").
            """
            
            # Generate content with retry logic
            response = None
            retry_delay = 1
            for attempt in range(max_retries):
                try:
                    response = self.model.generate_content([prompt, uploaded_file])
                    print(f"Content generated successfully on attempt {attempt + 1}")
                    break
                except Exception as gen_error:
                    if attempt < max_retries - 1:
                        print(f"Generation attempt {attempt + 1} failed: {gen_error}. Retrying in {retry_delay}s...")
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise Exception(f"Failed to generate content after {max_retries} attempts: {gen_error}")
            
            if not response or not response.text:
                raise Exception("No response from Gemini API")
            
            # Clean up the response text to ensure it's valid JSON
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            questions = json.loads(text)
            
            # Post-process to ensure it matches our internal structure
            processed_questions = []
            for i, q in enumerate(questions):
                question_type = q.get("question_type", "single_choice")
                
                # Only process options for multiple choice questions
                options = None
                correct_answer = q.get("correct_answer", 0)
                
                if question_type in ["single_choice", "multiple_choice", "media_question"]:
                    # Ensure options are in the right format for our frontend
                    options = []
                    raw_options = q.get("options", [])
                    letters = ['A', 'B', 'C', 'D']
                    
                    for j, opt_text in enumerate(raw_options):
                        if j < 4:
                            options.append({
                                "id": f"gen_{i}_{j}",
                                "text": str(opt_text),
                                "is_correct": j == q.get("correct_answer", 0),
                                "letter": letters[j]
                            })
                    
                    # Fill in missing options if fewer than 4
                    while len(options) < 4:
                        j = len(options)
                        options.append({
                            "id": f"gen_{i}_{j}",
                            "text": "",
                            "is_correct": False,
                            "letter": letters[j]
                        })
                else:
                    # For open-ended questions, correct_answer is a string
                    correct_answer = q.get("correct_answer", "")

                processed_questions.append({
                    "id": f"gemini_{i}_{os.urandom(4).hex()}",
                    "question_text": q.get("question_text", "Question"),
                    "question_type": question_type,
                    "options": options,
                    "correct_answer": correct_answer,
                    "points": 1,
                    "explanation": q.get("explanation", ""),
                    "is_sat_question": True,
                    "content_text": q.get("content_text", ""),
                    "needs_image": q.get("needs_image", False)
                })
                
            return processed_questions
            
        except Exception as e:
            print(f"Error parsing file with Gemini: {e}")
            raise e

parser_service = GeminiParser()
