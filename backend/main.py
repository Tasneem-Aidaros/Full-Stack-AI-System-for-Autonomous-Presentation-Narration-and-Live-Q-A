from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ppt_reader import read_presentation
from ai_service import explain_slide, generate_presentation_scripts
from question_handler import answer_question
from presentation_agent import agent
from knowledge_base import knowledge
from slide_exporter import export_slides
import shutil
import os
import threading
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Only the local Vite dev server may call this API from a browser.
# Override with FRONTEND_ORIGINS in backend/.env (comma separated) if the
# frontend is served from somewhere else. No cookies/sessions are used,
# so credentials stay off.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve exported slide PNGs directly so the frontend can show the
# current slide in-browser (e.g. GET /slide-images/Slide3.PNG),
# instead of relying on the native PowerPoint window.
os.makedirs("slide_images", exist_ok=True)
app.mount("/slide-images", StaticFiles(directory="slide_images"), name="slide-images")

# -----------------------------
# Global Variables
# -----------------------------
current_presentation = None
slides_cache = []
current_slide = 1
chat_history = []


# -----------------------------
# Turn raw AI errors into messages a person can act on
# -----------------------------
def explain_ai_error(error):

    text = str(error)
    lowered = text.lower()

    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return (
            "Gemini quota reached (the free tier has a small daily limit). "
            "Wait for the daily reset, set GEMINI_MODEL to another model in "
            "backend/.env, or enable billing."
        )

    if "API_KEY_INVALID" in text or "API key" in text or "PERMISSION_DENIED" in text:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env."

    if "404" in text or "NOT_FOUND" in text:
        return (
            "That Gemini model is not available for your API key. Run "
            "list_models.py and set GEMINI_MODEL in backend/.env."
        )

    if "disconnected" in lowered or "connection reset" in lowered:
        return (
            "The connection to Gemini was dropped. This is usually your network: "
            "try turning off any VPN, trying another network (like a phone "
            "hotspot), then upload again. Run check_gemini.py to test the connection."
        )

    if "write operation timed out" in lowered:
        return (
            "Sending the slides to Gemini timed out (slow or unstable upload). "
            "Try again, or add SEND_SLIDE_IMAGES=false to backend/.env to send "
            "slide text only (much smaller request)."
        )

    if "timed out" in lowered or "timeout" in lowered:
        return "Gemini did not answer in time. Check your internet connection and try again."

    if "503" in text or "UNAVAILABLE" in text:
        return "Gemini is overloaded right now. Try again in a minute."

    return f"Script generation failed: {text[:300]}"


# -----------------------------
# Home
# -----------------------------
@app.get("/")
def home():
    return {"message": "Hello AI Presenter!"}


# -----------------------------
# Upload Presentation
# -----------------------------
@app.post("/upload")
async def upload_presentation(file: UploadFile = File(...), force_regenerate: bool = False):
    global current_presentation
    global slides_cache
    global current_slide
    global chat_history

    os.makedirs("uploads", exist_ok=True)

    file_path = os.path.join("uploads", file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    print(f"\nUpload received: {file.filename}")

    # Export slide images BEFORE reading/generating scripts, so
    # ai_service has images to attach when it looks for
    # slide_images/Slide{n}.PNG. If this step fails or times out
    # (e.g. PowerPoint is stuck on a dialog), carry on text-only
    # instead of failing the whole upload.
    print("Step 1/3: exporting slide images with PowerPoint...")

    try:
        export_slides(file_path)
    except Exception as e:
        print("Slide image export failed (continuing text-only):", e)

    print("Step 2/3: reading slide text...")

    try:
        new_slides = read_presentation(file_path)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read this file as a .pptx presentation: {e}"
        )

    print("Step 3/3: preparing the narration script...")

    try:
        new_scripts = generate_presentation_scripts(
            new_slides,
            force_regenerate=force_regenerate
        )
    except Exception as e:
        print("Script generation failed:", e)
        raise HTTPException(status_code=502, detail=explain_ai_error(e))

    # Only replace the current deck once EVERYTHING succeeded, so a
    # failed upload can't leave new slides paired with old scripts.
    current_presentation = file_path
    slides_cache = new_slides
    agent.slide_scripts = new_scripts

    # Build the knowledge base right away so /ask can use
    # targeted search before the live presentation even starts.
    knowledge.build(slides_cache, agent.slide_scripts)

    print("Upload finished.\n")

    current_slide = 1
    chat_history = []

    return {
        "message": "Presentation uploaded successfully!",
        "filename": file.filename,
        "slides": len(slides_cache)
    }


# -----------------------------
# Get All Slides
# -----------------------------
@app.get("/presentation")
def get_presentation():

    if not slides_cache:
        raise HTTPException(status_code=400, detail="No presentation uploaded.")

    return slides_cache


# -----------------------------
# Explain One Slide
# -----------------------------
@app.get("/explain/{slide_number}")
def explain(slide_number: int):

    if not slides_cache:
        raise HTTPException(status_code=400, detail="No presentation uploaded.")

    if slide_number < 1 or slide_number > len(slides_cache):
        raise HTTPException(status_code=404, detail="Slide not found.")

    slides = slides_cache

    # Tell the AI which slide we're on
    agent.set_current_slide(slide_number)

    # Check if we already generated this script
    saved_script = agent.get_script(slide_number)

    if saved_script:

        explanation = saved_script

    else:

        slide = slides[slide_number - 1]

        image_path = f"slide_images/Slide{slide_number}.PNG"

        explanation = explain_slide(
            slide["text"],
            image_path
        )

        # Save it for future use
        agent.save_script(
            slide_number,
            explanation
        )

    slide = slides[slide_number - 1]

    return {
        "slide": slide_number,
        "title": slide["text"].split("\n")[0],
        "explanation": explanation
    }


# -----------------------------
# Set Current Slide
# -----------------------------
class SlideRequest(BaseModel):
    slide: int


@app.post("/current-slide")
def set_current_slide(request: SlideRequest):

    global current_slide

    if not slides_cache:
        raise HTTPException(status_code=400, detail="No presentation uploaded.")

    if request.slide < 1 or request.slide > len(slides_cache):
        raise HTTPException(status_code=400, detail="Invalid slide number.")

    current_slide = request.slide

    return {
        "message": "Current slide updated.",
        "current_slide": current_slide
    }


# -----------------------------
# Ask AI Questions
# (works whether the audience types or speaks — spoken questions
# arrive via the mic/wake-word flow inside presentation_agent.py;
# this endpoint is the "write" option, callable any time)
# -----------------------------
class QuestionRequest(BaseModel):
    question: str


@app.post("/ask")
def ask(request: QuestionRequest):

    global chat_history

    if not slides_cache:
        raise HTTPException(status_code=400, detail="No presentation uploaded.")

    if agent.running:

        # A presentation is live: route this through the same
        # interrupt mechanism a spoken "excuse me" uses, instead of
        # answering directly here. That way it pauses narration,
        # answers through the agent's own speech pipeline (avoiding
        # two independent TTS calls fighting over the audio device),
        # and resumes narration afterward — exactly like a spoken
        # question does. The actual answer arrives asynchronously;
        # the frontend should poll GET /subtitle (live caption) and
        # GET /chat-history (final answer) for the result.
        agent.submit_typed_question(request.question)

        return {
            "message": "Question submitted. The presenter will answer shortly.",
            "mode": "live"
        }

    # No live presentation running — nothing to interrupt, so just
    # answer directly and speak it immediately (original behavior).
    current_text = slides_cache[current_slide - 1]["text"]

    # Use the knowledge base to pull just the slides relevant
    # to this question instead of dumping the entire deck into
    # every prompt. Falls back to the full deck if the
    # knowledge base hasn't been built yet for some reason.
    relevant_slides = knowledge.search(request.question)

    if relevant_slides:
        presentation_text = "\n".join(
            f"Slide {slide['number']}\n{slide['text']}"
            for slide in relevant_slides
        )
    else:
        presentation_text = "\n".join(
            f"Slide {slide['slide']}\n{slide['text']}"
            for slide in slides_cache
        )

    answer = answer_question(
        question=request.question,
        current_slide=current_text,
        presentation=presentation_text,
        history=chat_history,
        speak_answer=True
    )

    chat_history.append({
        "user": request.question,
        "assistant": answer
    })

    return {
        "answer": answer,
        "mode": "standalone"
    }


# -----------------------------
# Chat History
# (covers both typed and spoken audience questions — spoken ones
# get appended to agent.chat_history inside handle_question())
# -----------------------------
@app.get("/chat-history")
def get_chat_history():

    if agent.running:
        return agent.chat_history

    return chat_history


# -----------------------------
# Start Presentation
# -----------------------------
@app.post("/start_presentation")
def start_presentation(resume: bool = False):

    if not slides_cache:
        raise HTTPException(status_code=400, detail="No presentation uploaded.")

    if agent.running:
        raise HTTPException(status_code=409, detail="Presentation is already running.")

    threading.Thread(
        target=agent.start,
        args=(current_presentation, slides_cache),
        kwargs={"resume": resume},
        daemon=True
    ).start()

    return {
        "message": "Presentation resumed." if resume else "Presentation started."
    }


# -----------------------------
# Presentation Status
# -----------------------------
@app.get("/presentation-status")
def get_presentation_status():

    return agent.get_status()


# -----------------------------
# Stop Presentation
# -----------------------------
@app.post("/stop_presentation")
def stop_presentation():

    agent.stop()

    return {
        "message": "Presentation stopped."
    }


# -----------------------------
# Pause / Resume (within a live session)
# -----------------------------
@app.post("/pause")
def pause_presentation():

    if not agent.running:
        raise HTTPException(status_code=409, detail="Nothing is currently presenting.")

    agent.pause_playback()

    return {"message": "Paused.", "paused": True}


@app.post("/resume")
def resume_presentation():

    if not agent.running:
        raise HTTPException(status_code=409, detail="Nothing is currently presenting.")

    agent.resume_playback()

    return {"message": "Resumed.", "paused": False}


# -----------------------------
# Seek (~10s, estimated — see presentation_agent.py for why this
# can't be frame-accurate: narration has no pre-recorded timeline)
# -----------------------------
@app.post("/seek/back")
def seek_back():

    if not agent.running:
        raise HTTPException(status_code=409, detail="Nothing is currently presenting.")

    agent.seek(-10)

    return {"message": "Seeking back ~10s."}


@app.post("/seek/forward")
def seek_forward():

    if not agent.running:
        raise HTTPException(status_code=409, detail="Nothing is currently presenting.")

    agent.seek(10)

    return {"message": "Seeking forward ~10s."}


# -----------------------------
# Manual slide navigation
# (interrupts whatever's currently playing immediately, same as
# pause/seek — see _speak_script in presentation_agent.py)
# -----------------------------
@app.post("/slide/next")
def slide_next():

    if not agent.running:
        raise HTTPException(status_code=409, detail="Nothing is currently presenting.")

    agent.next_slide()

    return {"message": "Moving to next slide."}


@app.post("/slide/previous")
def slide_previous():

    if not agent.running:
        raise HTTPException(status_code=409, detail="Nothing is currently presenting.")

    agent.previous_slide()

    return {"message": "Moving to previous slide."}


@app.post("/slide/{slide_number}/goto")
def slide_goto(slide_number: int):

    if not agent.running:
        raise HTTPException(status_code=409, detail="Nothing is currently presenting.")

    if not slides_cache or slide_number < 1 or slide_number > len(slides_cache):
        raise HTTPException(status_code=404, detail="Slide not found.")

    agent.jump_to_slide(slide_number)

    return {"message": f"Jumping to slide {slide_number}."}


# -----------------------------
# Live Subtitle
# -----------------------------
@app.get("/subtitle")
def get_subtitle():

    return {
        "slide": agent.current_slide,
        "text": agent.current_subtitle,
        "mode": agent.subtitle_mode
    }


# -----------------------------
# Speech Speed
# -----------------------------
class SpeedRequest(BaseModel):
    speed: float


@app.post("/speech-speed")
def set_speech_speed(request: SpeedRequest):

    new_speed = agent.set_speed(request.speed)

    return {
        "message": "Speech speed updated.",
        "speed": new_speed
    }


@app.get("/speech-speed")
def get_speech_speed():

    return {
        "speed": agent.speech_rate
    }
