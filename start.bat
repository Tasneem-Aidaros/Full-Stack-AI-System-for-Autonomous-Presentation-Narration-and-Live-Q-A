@echo off
setlocal
title AI Presenter Launcher
cd /d "%~dp0"

echo ==========================================
echo   AI Presenter - starting up
echo ==========================================
echo.

rem ---- Check that Python and Node.js are installed ----
where python >nul 2>nul
if errorlevel 1 goto no_python
where node >nul 2>nul
if errorlevel 1 goto no_node

rem ---- Backend: virtual environment (first run only) ----
if exist "backend\venv\Scripts\python.exe" goto venv_ready
echo [1/4] Creating Python virtual environment...
python -m venv "backend\venv"
if errorlevel 1 goto venv_failed
:venv_ready

rem ---- Backend: dependencies (first run only) ----
if exist "backend\venv\.deps_installed" goto deps_ready
echo [2/4] Installing backend dependencies. First run only, this can take a few minutes...
if exist "backend\requirements.txt" goto deps_from_file
"backend\venv\Scripts\python.exe" -m pip install fastapi uvicorn python-multipart python-dotenv google-genai pillow python-pptx pywin32 edge-tts pygame SpeechRecognition
goto deps_check
:deps_from_file
"backend\venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
:deps_check
if errorlevel 1 goto deps_failed
rem PyAudio is only needed for spoken questions, so do not stop if it fails
"backend\venv\Scripts\python.exe" -m pip install pyaudio
if errorlevel 1 echo [warning] PyAudio could not be installed. Typed questions will work, spoken questions will not.
>"backend\venv\.deps_installed" echo done
:deps_ready

rem ---- Backend: Gemini API key (first run only) ----
if exist "backend\.env" goto env_ready
echo [3/4] First-time setup: Gemini API key
echo Get a free key at https://aistudio.google.com/
set /p GEMINI_KEY=Paste your Gemini API key and press Enter: 
if "%GEMINI_KEY%"=="" goto no_key
>"backend\.env" echo GEMINI_API_KEY=%GEMINI_KEY%
:env_ready

rem ---- Frontend: dependencies (first run only) ----
if exist "frontend\node_modules" goto fe_ready
echo [4/4] Installing frontend dependencies. First run only...
pushd "frontend"
call npm install
set NPM_RESULT=%errorlevel%
popd
if not "%NPM_RESULT%"=="0" goto npm_failed
:fe_ready

rem ---- Launch both servers, each in its own window ----
echo.
echo Starting the backend and the frontend...
start "AI Presenter - Backend" /D "backend" cmd /k "venv\Scripts\python.exe -m uvicorn main:app --reload"
start "AI Presenter - Frontend" /D "frontend" cmd /k "npm run dev"

echo Waiting for the servers to come up...
timeout /t 8 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo AI Presenter is running at http://localhost:5173
echo To stop it, close the two black server windows.
timeout /t 6 >nul
exit /b 0

:no_python
echo Python was not found.
echo Install Python 3.11 from https://www.python.org/downloads/
echo Tick "Add Python to PATH" during setup, then run this file again.
pause
exit /b 1

:no_node
echo Node.js was not found.
echo Install the LTS version from https://nodejs.org/ then run this file again.
pause
exit /b 1

:venv_failed
echo Could not create the Python virtual environment.
pause
exit /b 1

:deps_failed
echo Installing the backend dependencies failed. Read the messages above for the reason.
pause
exit /b 1

:no_key
echo No API key entered. Run this file again when you have one.
pause
exit /b 1

:npm_failed
echo Installing the frontend dependencies failed. Read the messages above for the reason.
pause
exit /b 1
