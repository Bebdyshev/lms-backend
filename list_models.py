import google.generativeai as genai
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAyI41ZooGEwEZXELrRn-vuq8mkC7mYdX0")
genai.configure(api_key=GEMINI_API_KEY)

print("Listing models...")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
