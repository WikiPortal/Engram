"""
Engram — Gemini API Key Test
Run from backend/ folder: python test_gemini.py
"""
import sys
import os
sys.path.append(".")

# Load .env manually
from dotenv import load_dotenv
load_dotenv()

def test_gemini():
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        print("❌ GEMINI_API_KEY not set in .env")
        print("   Get your free key at: https://aistudio.google.com")
        return False

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")
        response = model.generate_content("Reply with exactly: Engram is alive.")
        print(f"  ✅ Gemini API  — working")
        print(f"  Response: {response.text.strip()}")
        return True
    except Exception as e:
        print(f"  ❌ Gemini API  — FAILED ({e})")
        return False

if __name__ == "__main__":
    print("\n🧠 Engram — Gemini API Test\n")
    ok = test_gemini()
    print()
    if ok:
        print("✅ Gemini working. Ready for Step 4.\n")
    else:
        print("❌ Fix your API key in backend/.env\n")
        sys.exit(1)
