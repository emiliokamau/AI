import os
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

try:
    # The SDK returns a collection; print each model name and the raw model object
    models = client.models.list()
    for m in (getattr(models, "models", None) or models):
        print("MODEL:", getattr(m, "name", str(m)))
        # print full object for extra info
        print(m)
        print("------")
except Exception as e:
    print("Error listing models:", e)