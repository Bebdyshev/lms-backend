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
            
            CRITICAL - LaTeX Formatting Rules (MUST FOLLOW STRICTLY):
            - **EVERY** mathematical expression, number in mathematical context, variable, or formula MUST be wrapped in $...$
            - **NEVER** split a mathematical expression into multiple $...$ blocks - wrap the ENTIRE expression in ONE block
            - For regular text (words, labels) inside math mode, use BACKSLASH-text: $\\text{your text}$ with proper spacing
            - **CRITICAL**: The command is \\text{} with a BACKSLASH, NOT just text{}
            - **IMPORTANT**: When using \\text{}, ALWAYS add a space before the text: $15.5\\text{ inches}$ NOT $15.5\\text{inches}$
            - For non-mathematical numbers (years, dates, IDs), use $\\text{number}$: $\\text{2005}$, $\\text{2011}$
            - Variables and functions: $x$, $y$, $f(x)$, $g(t)$, etc.
            - All numbers in equations or formulas: $5$, $-3$, $0.5$, etc.
            - Single numbers with units or labels: $5\\text{ meters}$, $3\\text{ seconds}$, $15.5\\text{ inches}$
            - Constants: $\\pi$, $e$, $c$, etc.
            - Operations: $+$, $-$, $\\times$, $\\div$, $=$, etc. in mathematical context
            - Fractions: ALWAYS use $\\frac{numerator}{denominator}$ (e.g., $\\frac{1}{2}$, $\\frac{3x+1}{2y-5}$)
            - Exponents: $x^2$, $x^{10}$, $2^n$, $e^{-x}$
            - Subscripts: $x_1$, $x_{10}$, $a_n$, $x_{\\text{max}}$
            - Square roots: $\\sqrt{x}$, $\\sqrt{2}$, $\\sqrt[n]{x}$
            - Absolute values: $|x|$, $|-5|$
            - Inequalities: $x > 5$, $y \\leq 10$, $x \\neq 0$
            - Systems of equations: $\\begin{cases} equation1 \\\\ equation2 \\end{cases}$
            - Greek letters: $\\alpha$, $\\beta$, $\\gamma$, $\\pi$, $\\theta$, etc.
            - Special functions: $\\sin(x)$, $\\cos(x)$, $\\tan(x)$, $\\log(x)$, $\\ln(x)$
            - Summation: $\\sum_{i=1}^{n}$, $\\sum_{k=0}^{\\infty}$
            - Integration: $\\int_{a}^{b}$, $\\int_{-\\infty}^{\\infty}$
            - Limits: $\\lim_{x \\to 0}$, $\\lim_{n \\to \\infty}$
            - Derivatives: $\\frac{dy}{dx}$, $f'(x)$, $\\frac{d^2y}{dx^2}$
            - Sets: $\\{1, 2, 3\\}$, $\\mathbb{R}$, $\\mathbb{N}$
            
            Examples of CORRECT usage:
            - "The function $f(x) = 2x + 3$ has a slope of $2$"
            - "Solve for $x$ in the equation $x^2 + 5x + 6 = 0$"
            - "The value of $\\frac{3}{4}$ is greater than $\\frac{1}{2}$"
            - "System: $\\begin{cases} x + y = 5 \\\\ x - y = 1 \\end{cases}$"
            - "If $a = 3$ and $b = 4$, then $c = \\sqrt{a^2 + b^2} = 5$"
            - "The derivative of $f(x) = x^2$ is $f'(x) = 2x$"
            - "The distance is $5\\text{ meters}$" (note the space before meters)
            - "In $\\text{2005}$, the screen size was $15.5\\text{ inches}$"
            - "Between $\\text{2005}$ and $\\text{2011}$" (years as text)
            - "Let $x_{\\text{max}}$ be the maximum value"
            
            DO NOT write mathematical expressions without LaTeX:
            - ❌ "x^2 + 5x + 6 = 0" 
            - ✅ "$x^2 + 5x + 6 = 0$"
            - ❌ "f(x) = 2x + 3"
            - ✅ "$f(x) = 2x + 3$"
            - ❌ "5 meters"
            - ✅ "$5\\text{ meters}$"
            - ❌ "$15.5\\text{inches}$" (missing space)
            - ✅ "$15.5\\text{ inches}$" (correct with space)
            - ❌ "$0.5 ext{ inch}$" (WRONG - missing backslash before text)
            - ✅ "$0.5\\text{ inch}$" (CORRECT - with backslash)
            - ❌ "In 2005" (year without LaTeX)
            - ✅ "In $\\text{2005}$" (year as text)
            
            DO NOT split expressions into multiple math blocks:
            - ❌ "$60$ / $30$ = $2$" (WRONG - split into parts)
            - ✅ "$60/30 = 2$" (CORRECT - entire expression in one block)
            - ❌ "$2$ * $7$ = $14$" (WRONG - split into parts)
            - ✅ "$2 \\times 7 = 14$" (CORRECT - entire expression in one block)
            - ❌ "He needs $60$ grams" (OK for single number)
            - ✅ "He needs $60\\text{ grams}$" (BETTER with unit)
            
            **JSON OUTPUT FORMATTING**:
            - When generating JSON, you MUST escape backslashes in LaTeX commands
            - In JSON strings, use DOUBLE backslash: "question_text": "The answer is $15.5\\\\text{ inches}$"
            - A single backslash in JSON will be lost - always use double backslash for LaTeX commands
            - Example JSON output:
              {
                "question_text": "In $\\\\text{2005}$, the size was $15.5\\\\text{ inches}$",
                "options": ["$\\\\frac{1}{2}$", "$\\\\frac{3}{4}$", ...]
              }
            
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
            
            # Fix common LaTeX backslash issues in JSON
            # Replace single backslashes with double backslashes for LaTeX commands
            # We use a list of common commands to be safe, plus a regex for others
            
            import re
            
            # 1. Fix specific commands that might be interpreted as escape sequences (\t, \n, \f, \b, \r)
            # \times -> \\times, \text -> \\text, \frac -> \\frac, etc.
            latex_commands = [
                "times", "text", "tan", "theta", "tau",  # \t
                "frac", "forall", "phi",                 # \f
                "beta", "bar", "break", "begin", "mathbf", "mathbb", # \b
                "nu", "neq", "nabla",                    # \n
                "rho", "right",                          # \r
                "alpha", "sigma", "gamma", "delta", "epsilon", "lambda", "mu", "pi", "omega", # other greek
                "sqrt", "sum", "sin", "cos", "log", "ln", "lim", "int", "infty", "approx", "div", "pm", "mp", "cdot", "leq", "geq" # other ops
            ]
            
            for cmd in latex_commands:
                # Replace \cmd with \\cmd, but only if it's not already \\cmd
                # We look for single backslash followed by the command
                # Note: In Python regex string, \\ matches a literal backslash
                pattern = r'(?<!\\)\\' + cmd
                replacement = r'\\\\' + cmd
                text = re.sub(pattern, replacement, text)

            # 2. Fix other backslashes that are not valid JSON escapes
            # Valid JSON escapes: ", \, /, b, f, n, r, t, u
            # If we see \ followed by something else (like \s, \a, \c), it's likely a LaTeX command
            # Regex: Backslash not preceded by backslash, followed by character NOT in [ " \ / b f n r t u ]
            text = re.sub(r'(?<!\\)\\(?![\\"/bfnrtu])', r'\\\\', text)

            try:
                questions = json.loads(text)
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {e}")
                print(f"Problematic text snippet: {text[max(0, e.pos-50):min(len(text), e.pos+50)]}")
                raise Exception(f"Failed to parse Gemini response as JSON: {e}")
            
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
