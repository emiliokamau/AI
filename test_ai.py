import os
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")  # change after you list models

try:
    response = client.models.generate_content(
        model=MODEL,
        contents="Explain how AI works in one sentence."
    )
    # the SDK response shape can vary; try to access text safely
    print("SUCCESS! Response:")
    print(getattr(response, "text", response))
except Exception as e:
    print("An error occurred:", e)
    print("Tip: run list_models.py to see available models and set GEMINI_MODEL accordingly.")