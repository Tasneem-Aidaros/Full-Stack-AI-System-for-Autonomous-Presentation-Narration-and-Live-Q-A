# AI Presenter

An AI system that takes a PowerPoint file and presents it by itself. It opens the real PowerPoint app, narrates each slide in a natural voice, shows live captions, and answers audience questions (spoken or typed) in the middle of the talk, then continues from exactly where it stopped.

A React web console lets you control everything live: play, pause, skip, change speed, and watch the slides with captions in one window, similar to a video player.

<!-- Add a screenshot or short demo GIF here, for example: ![Console](docs/screenshot.png) -->

---

## Features

- **Automatic narration.** Google Gemini writes a natural spoken script for the whole deck (using slide text and slide images), and a neural voice reads it slide by slide.
- **Live captions.** The sentence being spoken is shown over the slide in real time.
- **Live Q&A, two ways.** Say a wake phrase ("excuse me") and ask out loud, or type the question in the web console. The app shows what it heard so you can check the microphone understood you.
- **Smart interruption.** The presenter pauses mid-slide, answers, then resumes from the exact sentence it stopped at.
- **Instant controls.** Pause, resume, stop, "continue from where I stopped", skip about 10 seconds forward or back, next/previous slide, and speed from 0.5x to 2x. Controls act immediately, not after the current sentence ends.
- **Slides in the browser.** Slides are exported as images and shown in the web console with captions on top.
- **Low API usage.** Generated scripts are cached on disk, slide images are downscaled before being sent to Gemini, and Q&A only sends the most relevant slides instead of the whole deck.

---

## How it works

1. **Upload.** You upload a `.pptx`. The backend reads the slide text and exports each slide as a PNG through PowerPoint.
2. **Script generation.** Gemini receives all slide text and images in one request and returns a spoken script for every slide. Results are cached by content hash, so uploading the same deck again costs nothing.
3. **Presenting.** The backend opens PowerPoint, starts the slideshow, and speaks the script sentence by sentence while moving through slides.
4. **Interruption.** A background microphone thread listens for a wake phrase. When it hears one, narration pauses, the question is captured, Gemini answers using the most relevant slides, and the answer is spoken.
5. **Resume.** The presentation continues from the exact sentence where it was interrupted.
6. **Web console.** The React app polls the backend several times per second for captions, status, and chat history, and sends control commands (start, pause, seek, ask, and so on).

---

## Tech stack

| Area | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| AI | Google Gemini API (`google-genai` SDK) |
| Text-to-speech | `edge-tts` (voice playback with `pygame`) |
| Speech-to-text | `SpeechRecognition` (microphone input via PyAudio) |
| PowerPoint control | `python-pptx` (read text), `pywin32` / COM automation (control the app, export images) |
| Concurrency | Python `threading` |
| Frontend | React, Vite, JavaScript (JSX), plain CSS |
| Communication | REST endpoints with `fetch()` and short-interval polling |
| Config | `python-dotenv` (`.env` file) |
| Caching | JSON files on disk, no database |

---

## Requirements

- **Windows** (PowerPoint control uses COM automation, which is Windows only)
- **Microsoft PowerPoint** installed
- **Python 3.11** (other 3.x versions may work, 3.11 is what this was developed on)
- **Node.js** (LTS) and npm
- A **Google Gemini API key** from [Google AI Studio](https://aistudio.google.com/)
- A **microphone** (only needed for spoken questions)
- An **internet connection** (Gemini, edge-tts, and Google speech recognition are online services)

---

## Quick start (Windows, one click)

1. Install [Python 3.11](https://www.python.org/downloads/) (tick **Add Python to PATH**) and [Node.js LTS](https://nodejs.org/).
2. Double-click **`start.bat`** in the root of the project.

On the first run it creates the virtual environment, installs the backend and frontend dependencies, and asks you to paste your Gemini API key (it saves it to `backend/.env` for you). This takes a few minutes, once. After that, `start.bat` just launches the backend and frontend in two windows and opens **http://localhost:5173** in your browser. Close the two black server windows to stop the app.

Prefer to do it by hand? Use the manual steps below.

---

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

### 2. Backend setup

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script, run this first (affects only the current window):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

Install the dependencies:

```powershell
pip install -r requirements.txt
```

Create a file named `.env` inside `backend/`:

```env
GEMINI_API_KEY=your_api_key_here

# Optional. Defaults to gemini-flash-latest if not set.
# GEMINI_MODEL=gemini-flash-latest
```

> Never commit your `.env` file. It is already listed in `.gitignore`.

### 3. Frontend setup

```powershell
cd frontend
npm install
```

---

## Running the project

You need **two terminals** running at the same time.

**Terminal 1: backend**

```powershell
cd backend
venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

The API runs at `http://127.0.0.1:8000` (interactive docs at `http://127.0.0.1:8000/docs`).

**Terminal 2: frontend**

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

If your backend runs on a different address, change `API_BASE` at the top of `frontend/src/api.js`.

---

## Using it

1. Drag a `.pptx` file into the upload box and wait while it reads the slides, exports images, and prepares the script.
2. Press **Start**. PowerPoint opens and the AI begins presenting.
3. Use the control bar to pause, skip, jump between slides, or change speed.
4. To ask a question, either say **"excuse me"** (other wake phrases: "question", "can I ask", "hey presenter") and then speak your question, or type it in the Intercom box.
5. Press **Stop** to end. Press **Continue** to resume from the exact slide and sentence you stopped at, or choose to start over.

---

## API overview

| Endpoint | Purpose |
|---|---|
| `POST /upload` | Upload a `.pptx` (optional `?force_regenerate=true` skips the script cache) |
| `POST /start_presentation` | Start presenting (`?resume=true` continues from the last position) |
| `POST /stop_presentation` | Stop the presentation |
| `POST /pause`, `POST /resume` | Pause or resume playback |
| `POST /seek/back`, `POST /seek/forward` | Jump about 10 seconds (estimated) |
| `POST /slide/next`, `/slide/previous`, `/slide/{n}/goto` | Manual slide navigation |
| `POST /ask` | Ask a typed question |
| `GET /subtitle` | Current caption text and its mode (narration, acknowledging, question, answering) |
| `GET /presentation-status` | Current status, slide number, and paused state |
| `GET /chat-history` | All questions and answers so far |
| `GET /speech-speed`, `POST /speech-speed` | Read or set narration speed (0.5 to 2.0) |
| `GET /slide-images/Slide{n}.PNG` | Exported slide images |

---

## Project structure

```
.
├── backend/
│   ├── main.py                  # FastAPI app and all endpoints
│   ├── presentation_agent.py    # Core presentation loop: narration, pause, seek, Q&A
│   ├── ai_service.py            # Gemini calls, caching, image downscaling
│   ├── knowledge_base.py        # Finds the slides relevant to a question
│   ├── speech_manager.py        # Speech playback with fast cancellation
│   ├── tts_service.py           # Text-to-speech (edge-tts + pygame)
│   ├── stt_service.py           # Speech-to-text (microphone)
│   ├── microphone_manager.py    # Background wake-phrase listener
│   ├── powerpoint_controller.py # PowerPoint COM automation
│   ├── slide_exporter.py        # Exports slides as PNG images
│   ├── ppt_reader.py            # Reads slide text from the .pptx
│   ├── question_handler.py      # Answers questions outside a live presentation
│   └── list_models.py           # Lists Gemini models available to your key
└── frontend/
    ├── index.html
    ├── package.json
    └── src/
        ├── App.jsx              # State and polling
        ├── api.js               # All backend calls
        ├── index.css            # Design system
        └── components/          # Player, StatusBar, UploadPanel, IntercomPanel
```

Folders created automatically while running: `uploads/`, `slide_images/`, `gemini_cache/`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `404 NOT_FOUND ... model is no longer available` | Google retired that model for your key. Run `python list_models.py`, then set `GEMINI_MODEL` in `.env` to a model it lists. |
| `429 RESOURCE_EXHAUSTED` | You hit the Gemini free tier daily limit (20 requests per model per day at the time of writing). Wait for the reset, switch model, or enable billing. |
| `503 UNAVAILABLE` | Gemini is temporarily overloaded. The app retries a few times automatically. |
| PyAudio fails to install | Use a Python version that has a prebuilt PyAudio wheel for Windows, or install it with `pipwin install pyaudio`. |
| Microphone does not react | Check that Windows allows microphone access for your terminal, and that the correct default input device is selected. |
| Frontend cannot reach the backend | Make sure the backend is running on port 8000 and `API_BASE` in `frontend/src/api.js` matches. |
| PowerShell will not activate the venv | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` first. |

---

## Known limitations

- Windows only, and requires desktop PowerPoint.
- The server keeps one presentation session in memory, so it supports one user at a time and loses state when restarted.
- Question retrieval uses keyword matching, not semantic search, so heavily reworded questions can miss relevant slides.
- The "10 second" seek is an estimate based on word count, because narration is generated live and has no fixed timeline.
- The web console uses polling instead of WebSockets.
- The Gemini free tier is very limited, so repeated testing relies on the script cache.

---

## Future work

- Refresh and reconnect handling in the web console
- Slide thumbnail strip for visual navigation
- Presenter view and separate audience view
- Transcript export after a presentation
- Voice selection
- Timer and pacing indicator
- Semantic (embedding-based) retrieval for Q&A
- Support for PDFs and other documents, user accounts, a database, and online hosting for a NotebookLM-style web app

---

## Author

Tasneem Aidaros
