import os
import re
import json
import time
import hashlib
import io
from dotenv import load_dotenv
from google import genai
from PIL import Image

load_dotenv()

# Without a timeout, a stalled network request waits forever and the
# upload just sits there with no message. 180s is generous for a deck
# with images, and turns a silent hang into a clear error instead.
GEMINI_TIMEOUT_MS = 180000

genai_types = None

try:
    from google.genai import types as genai_types

    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        http_options=genai_types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )
except Exception as e:
    print("Could not set a Gemini request timeout, using defaults:", e)
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Google has been aggressively deprecating specific Gemini model versions
# (2.5-flash and 2.5-flash-lite are both already gone for newer API keys
# as of mid-2026). Using the "-latest" alias instead of a pinned version
# means Google keeps this pointed at whatever their current stable Flash
# model is, so this stops breaking every time they retire a version.
# Override with GEMINI_MODEL in .env if you want to pin a specific model
# (check exactly what your key can use by running list_models.py first).
MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Kept intentionally short: this code path also runs during live
# audience Q&A, where a 75-second worst-case retry chain (the old
# 5/10/20/40s backoff) means an awkward silent pause for a room full
# of people. 3s/6s trades some resilience for staying responsive.
MAX_RETRIES = 3
INITIAL_WAIT = 3

# Images are the single biggest quota cost per request (far more tokens
# than text). Downscaling before sending cuts that cost a lot with no
# real loss in the model's ability to read slide diagrams/charts.
MAX_IMAGE_DIM = 768

# Set SEND_SLIDE_IMAGES=false in backend/.env to send slide TEXT only.
# Useful on a slow upload connection: all slide images travel in one
# request, and a stalled upload shows up as "write operation timed out".
USE_IMAGES = os.getenv("SEND_SLIDE_IMAGES", "true").strip().lower() not in ("0", "false", "no", "off")

# Sizes (in bytes) of the images attached to the current request, only
# used for the log line printed before calling Gemini.
_image_bytes_sent = []

# On-disk cache so re-uploading the same deck (very common while testing)
# never re-spends quota regenerating scripts/explanations it already has.
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gemini_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


# =====================================================
# Load + downscale an image before sending to Gemini
# =====================================================
def _load_image(path):

    image = Image.open(path)
    image.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))

    if genai_types is None:
        # Could not import the SDK's types, let the SDK encode it.
        return image

    # Send JPEG instead of PNG. Slides are flat colours and text, so JPEG
    # at this size is far smaller than PNG, and all the slide images
    # travel in ONE request. A huge request body is what made uploads
    # fail with "The write operation timed out" on slower connections.
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=75, optimize=True)

    data = buffer.getvalue()
    _image_bytes_sent.append(len(data))

    return genai_types.Part.from_bytes(
        data=data,
        mime_type="image/jpeg"
    )


# =====================================================
# Cache helpers (disk-backed, keyed by content hash)
# =====================================================
def _hash_slides(slides):

    hasher = hashlib.md5()

    hasher.update(b"images" if USE_IMAGES else b"text-only")

    for slide in slides:

        hasher.update(slide["text"].encode("utf-8"))

        image_path = slide.get("image")

        if image_path and os.path.exists(image_path):
            hasher.update(str(os.path.getsize(image_path)).encode())

    return hasher.hexdigest()


def _hash_text(text, image_path=None):

    hasher = hashlib.md5()

    hasher.update(text.encode("utf-8"))

    if image_path and os.path.exists(image_path):
        hasher.update(str(os.path.getsize(image_path)).encode())

    return hasher.hexdigest()


def _cache_path(namespace, key):

    folder = os.path.join(CACHE_DIR, namespace)
    os.makedirs(folder, exist_ok=True)

    return os.path.join(folder, f"{key}.json")


def _cache_get(namespace, key):

    path = _cache_path(namespace, key)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_set(namespace, key, value):

    path = _cache_path(namespace, key)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Cache write failed (non-fatal):", e)


# =====================================================
# Generic Gemini Request
# =====================================================
def _generate(contents, stream=False):
    """
    stream=True receives the answer in pieces as Gemini writes it,
    instead of waiting for one big response at the end. Use it for long
    outputs (like a whole deck's script): a connection that sits silent
    for a long time is much more likely to be dropped by a router,
    VPN, proxy, or antivirus than one that keeps receiving data.
    """

    wait = INITIAL_WAIT

    for attempt in range(MAX_RETRIES):

        try:

            if stream:

                pieces = []

                for chunk in client.models.generate_content_stream(
                    model=MODEL,
                    contents=contents
                ):
                    text = getattr(chunk, "text", None)

                    if text:
                        pieces.append(text)

                return "".join(pieces)

            response = client.models.generate_content(
                model=MODEL,
                contents=contents
            )

            return response.text

        except Exception as e:

            error = str(e)

            print(f"\nGemini Error ({attempt + 1}/{MAX_RETRIES})")
            print(error)

            lowered_error = error.lower()

            if (
                "429" in error
                or "RESOURCE_EXHAUSTED" in error
                or "503" in error
                or "UNAVAILABLE" in error
                # Dropped connections are usually momentary, so try again.
                or "disconnected" in lowered_error
                or "connection reset" in lowered_error
                or "connection aborted" in lowered_error
                or "remoteprotocolerror" in lowered_error
            ):

                print(f"Waiting {wait} seconds before retrying...\n")

                time.sleep(wait)

                wait *= 2

                continue

            raise

    raise Exception("Gemini failed after multiple retries.")


# =====================================================
# Extract JSON safely
# =====================================================
def _extract_json(text):

    text = text.replace("```json", "")
    text = text.replace("```", "")
    text = text.strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise Exception("Gemini did not return valid JSON.")

    return json.loads(match.group())


# =====================================================
# Convert paragraph -> sentence list
# =====================================================
def _split_sentences(script):

    sentences = []

    script = script.replace("\n", " ")

    for sentence in re.split(r'(?<=[.!?])\s+', script):

        sentence = sentence.strip()

        if sentence:
            sentences.append(sentence)

    if not sentences:
        sentences.append(script)

    return sentences


# =====================================================
# Explain a SINGLE slide (on-demand, used by /explain)
# =====================================================
def explain_slide(text, image_path=None):

    cache_key = _hash_text(text, image_path)
    cached = _cache_get("explain_slide", cache_key)

    if cached is not None:
        print("Using cached slide explanation (no Gemini call).")
        return cached["explanation"]

    prompt = """
You are an experienced university presenter.

Explain the following slide as if speaking naturally to professors.

Rules:

- Return plain spoken text only. No JSON. No markdown.
- Never read bullet points word-for-word.
- Explain the ideas naturally, in your own words.
- Explain images, diagrams and charts when useful.
- Keep it between 20 and 45 seconds when spoken aloud.
- Sound like a real presenter, not a narrator reading text.
"""

    contents = [prompt, f"Slide Text:\n\n{text}"]

    if image_path and os.path.exists(image_path) and USE_IMAGES:
        contents.append(_load_image(image_path))

    response = _generate(contents)

    explanation = response.strip()

    _cache_set("explain_slide", cache_key, {"explanation": explanation})

    return explanation


# =====================================================
# Generate ALL scripts
# =====================================================
def generate_presentation_scripts(slides, force_regenerate=False):

    cache_key = _hash_slides(slides)

    if not force_regenerate:

        cached = _cache_get("presentation_scripts", cache_key)

        if cached is not None:
            print("Using cached presentation scripts (no Gemini call).")
            return {int(k): v for k, v in cached.items()}

    else:

        print("force_regenerate=True — skipping cache, calling Gemini fresh.")

    contents = []
    _image_bytes_sent.clear()

    prompt = """
You are an experienced university presenter.

Your task is to understand the ENTIRE presentation first,
then generate the presentation script for EVERY slide.

Rules:

- Return ONLY valid JSON.
- Never wrap the JSON in markdown.
- Never explain the JSON.
- Never read bullet points word-for-word.
- Explain the ideas naturally.
- Explain images, diagrams and charts when useful.
- Make smooth transitions between slides.
- Avoid repeating information.
- Keep each slide between 20 and 45 seconds.
- Sound like a real presenter speaking to professors.
- The first slide should introduce the presentation.
- The last slide should conclude naturally.

Return EXACTLY:

{
  "slides":[
      {
          "slide":1,
          "script":"..."
      }
  ]
}
"""

    contents.append(prompt)

    for slide in slides:

        contents.append(
            f"""
Slide {slide['slide']}

Text:

{slide['text']}
"""
        )

        image_path = slide.get("image")

        if image_path and os.path.exists(image_path) and USE_IMAGES:
            contents.append(_load_image(image_path))

    if _image_bytes_sent:
        payload = f"{len(_image_bytes_sent)} images, {sum(_image_bytes_sent) / 1048576:.1f} MB"
    else:
        payload = "text only"

    print(f"Calling Gemini ({MODEL}) for {len(slides)} slides ({payload}). A new deck can take a minute or two...")
    response = _generate(contents, stream=True)

    data = _extract_json(response)

    scripts = {}

    for item in data.get("slides", []):

        scripts[item["slide"]] = _split_sentences(
            item["script"]
        )

    # Guarantee every slide has a script
    for slide in slides:

        if slide["slide"] not in scripts:

            scripts[slide["slide"]] = [
                "Let's continue with this slide."
            ]

    _cache_set("presentation_scripts", cache_key, scripts)

    return scripts


# =====================================================
# Audience Questions
# =====================================================
def answer_question(question, current_slide, presentation, history):

    conversation = ""

    for item in history:

        conversation += f"""
Audience:
{item['user']}

Presenter:
{item['assistant']}
"""

    prompt = f"""
You are presenting your graduation project to professors.

Current Slide:

{current_slide}

Entire Presentation:

{presentation}

Conversation:

{conversation}

Audience Question:

{question}

Rules:

- Answer naturally.
- Never say "According to the presentation".
- Never mention AI.
- Never mention slides.
- Use the current slide first.
- Use the rest of the presentation if needed.
- You may use outside knowledge if necessary.
- Be confident.
- Be conversational.
- Give examples when useful.
- Keep the answer concise unless more detail is requested.
"""

    return _generate(prompt)