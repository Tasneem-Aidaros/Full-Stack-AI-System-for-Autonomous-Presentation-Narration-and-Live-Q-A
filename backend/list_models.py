import os
from dotenv import load_dotenv
from google import genai
 
load_dotenv()
 
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
 
print("Models available to this API key that support generate_content:\n")
 
for model in client.models.list():
 
    actions = getattr(model, "supported_actions", None) or []
 
    if "generateContent" in actions:
        print(model.name)