"""
Finds out WHY there is no sound, by testing each part separately.

Run it from the backend folder:

    venv\\Scripts\\python.exe check_audio.py

  Test 1: can Python open your speakers and play a beep?   (no internet)
  Test 2: can it download a spoken sentence from Microsoft? (needs internet)
  Test 3: can it play that sentence?

The first test that fails tells you where the problem is.
"""

import asyncio
import math
import os
import struct
import sys
import tempfile
import time
import wave

VOICE = "en-US-JennyNeural"


def heading(text):
    print(f"\n=== {text} ===")


def ask_heard(what):
    answer = input(f"Did you hear {what}? (y/n): ").strip().lower()
    return answer.startswith("y")


def play_file(pygame, path):
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        time.sleep(0.1)

    pygame.mixer.music.unload()


# ---------------------------------------------------------------
# Test 1: sound device + a plain beep (no internet involved)
# ---------------------------------------------------------------
heading("Test 1: speakers")

try:
    import pygame

    pygame.mixer.init()
    print(f"[OK] Opened the sound device: {pygame.mixer.get_init()}")

except Exception as e:
    print(f"[FAIL] Could not open a sound device: {e}")
    print("Fix: check that speakers or headphones are connected and selected as the")
    print("Windows default output device, then run this again.")
    sys.exit(1)

beep_path = os.path.join(tempfile.gettempdir(), "presenter_beep.wav")
rate = 22050

with wave.open(beep_path, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(rate)
    wav.writeframes(b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(rate)
    ))

print("Playing a 1 second beep...")
play_file(pygame, beep_path)

if not ask_heard("the beep"):
    print("\n[FAIL] Python played a sound but you did not hear it.")
    print("This is a Windows sound setting, not the app:")
    print(" - Raise the volume and check the speaker icon is not muted.")
    print(" - Right-click the speaker icon > Open Volume mixer, and make sure")
    print("   'python.exe' is not muted or turned down.")
    print(" - Check the right output device is selected (headphones, Bluetooth, HDMI).")
    print("Then run this test again.")
    sys.exit(1)

print("[OK] Speakers work.")

# ---------------------------------------------------------------
# Test 2: download a spoken sentence (needs internet)
# ---------------------------------------------------------------
heading("Test 2: voice service (Microsoft Edge TTS)")

try:
    import edge_tts
except Exception as e:
    print(f"[FAIL] edge-tts is not installed: {e}")
    print("Fix: venv\\Scripts\\python.exe -m pip install edge-tts")
    sys.exit(1)

voice_path = os.path.join(tempfile.gettempdir(), "presenter_voice.mp3")


async def generate():
    communicate = edge_tts.Communicate(
        text="Hello, this is a test of the presenter voice.",
        voice=VOICE
    )
    await asyncio.wait_for(communicate.save(voice_path), timeout=30)


start = time.time()

try:
    asyncio.run(generate())

except asyncio.TimeoutError:
    print("[FAIL] Timed out after 30 seconds. Your computer cannot reach the")
    print("Microsoft speech service. Turn off any VPN, check your firewall or")
    print("antivirus, or try another network (like a phone hotspot).")
    sys.exit(1)

except Exception as e:
    print(f"[FAIL] The voice service returned an error: {e}")
    print("If it mentions 403 or 'Invalid response status', update the library:")
    print("   venv\\Scripts\\python.exe -m pip install -U edge-tts")
    print("Otherwise it is usually a network, VPN, or firewall problem.")
    sys.exit(1)

size_kb = os.path.getsize(voice_path) / 1024
print(f"[OK] Downloaded the voice in {time.time() - start:.1f}s ({size_kb:.0f} KB).")

if size_kb < 1:
    print("[FAIL] The file is empty, so there is nothing to play.")
    sys.exit(1)

# ---------------------------------------------------------------
# Test 3: play the downloaded voice
# ---------------------------------------------------------------
heading("Test 3: playing the voice")

print("Playing the sentence...")
play_file(pygame, voice_path)

if ask_heard("a woman's voice saying a test sentence"):
    print("\n[OK] Everything works. If the app is still silent, send me the last")
    print("lines of the Backend window while a presentation is running.")
else:
    print("\n[FAIL] The voice downloaded fine but you did not hear it, even though")
    print("the beep worked. Send me this output and I will look into it.")

for path in (beep_path, voice_path):
    try:
        os.remove(path)
    except OSError:
        pass
