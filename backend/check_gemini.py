"""
Quick connection test for Gemini, independent of the rest of the app.

Run it from the backend folder:

    venv\\Scripts\\python.exe check_gemini.py

It makes 2 requests (this counts toward your daily free-tier quota):
  1. a tiny request
  2. a longer request that streams its answer, like the real script generation

Reading the result:
  - Both OK                -> your connection and key are fine.
  - 1 fails, 2 not reached -> the connection to Google itself is the problem
                              (VPN, proxy, antivirus, firewall, bad network).
  - 1 OK, 2 fails         -> long requests get dropped; try another network.
"""

import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print(f"Model: {MODEL}\n")


def check(label, action):

    start = time.time()

    try:
        characters = action()
        print(f"[OK]   {label}: {time.time() - start:.1f}s, {characters} characters")
        return True

    except Exception as e:
        print(f"[FAIL] {label}: after {time.time() - start:.1f}s")
        print(f"       {e}")
        return False


def tiny():
    response = client.models.generate_content(
        model=MODEL,
        contents="Reply with the single word: ready"
    )
    return len(response.text or "")


def long_streamed():
    pieces = []

    for chunk in client.models.generate_content_stream(
        model=MODEL,
        contents=(
            "Write 12 short paragraphs, each 3 sentences long, explaining "
            "different ideas about how presentations are delivered."
        )
    ):
        text = getattr(chunk, "text", None)

        if text:
            pieces.append(text)

    return len("".join(pieces))


if check("Tiny request", tiny):
    check("Long streamed request", long_streamed)
else:
    print("\nSkipping the second test because the first one failed.")
