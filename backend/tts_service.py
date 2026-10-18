import asyncio
import edge_tts
import pygame
import tempfile
import os

VOICE = "en-US-JennyNeural"

_stop_requested = False


# Without a timeout, an unreachable speech service just hangs here and
# the presenter goes silent with no message at all.
GENERATION_TIMEOUT_SECONDS = 25
GENERATION_ATTEMPTS = 2


async def generate_speech(text, output_file, rate="+0%"):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate=rate
    )

    await asyncio.wait_for(
        communicate.save(output_file),
        timeout=GENERATION_TIMEOUT_SECONDS
    )


def _generate_with_retry(text, output_file, rate, is_current):
    """
    Returns True when the audio file was created, False if this
    utterance was superseded (stopped/seeked/...) while trying, and
    raises a readable error if every attempt failed.
    """

    last_error = None

    for attempt in range(GENERATION_ATTEMPTS):

        try:
            asyncio.run(generate_speech(text, output_file, rate))
            return True

        except asyncio.TimeoutError:
            last_error = RuntimeError(
                f"Voice generation timed out after {GENERATION_TIMEOUT_SECONDS}s. "
                "The speech service (Microsoft Edge TTS) could not be reached. "
                "Check your internet, VPN, or firewall."
            )

        except Exception as e:
            last_error = e

        print(f"Voice generation failed (attempt {attempt + 1} of {GENERATION_ATTEMPTS}): {last_error}")

        if is_current is not None and not is_current():
            return False

    raise last_error


def stop_speaking():

    global _stop_requested

    _stop_requested = True

    try:
        pygame.mixer.music.stop()
    except:
        pass


def speed_to_rate(speed):
    """
    Convert a friendly speed multiplier (0.5, 1.0, 1.5, 2.0, ...)
    into the percentage string edge-tts expects (e.g. "+50%").
    1.0 -> "+0%" (normal speed).
    """

    speed = max(0.5, min(2.0, float(speed)))

    percent = round((speed - 1.0) * 100)

    sign = "+" if percent >= 0 else ""

    return f"{sign}{percent}%"


def speak(text, rate="+0%", is_current=None):
    """
    is_current: optional callable. Checked right after generation
    finishes (the slow, uncancellable part — a network round trip to
    edge-tts) and again during playback. If it returns False, this
    utterance has been superseded (stopped, sought past, spoken over
    by a speed change, etc.) and playback is skipped/cut immediately
    instead of finishing regardless.
    """

    global _stop_requested

    _stop_requested = False

    # Create a unique temporary mp3 file
    temp = tempfile.NamedTemporaryFile(
        suffix=".mp3",
        delete=False
    )

    output_file = temp.name
    temp.close()

    try:

        if not _generate_with_retry(text, output_file, rate, is_current):
            return

        # Generation has no cancellation of its own (it's a network
        # call), so this is the first point we can actually check
        # whether we're still wanted. Skipping playback here is what
        # makes Stop/Seek/Speed changes feel instant even if they
        # arrived while audio was still being generated.
        if is_current is not None and not is_current():
            return

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():

            if _stop_requested:
                pygame.mixer.music.stop()
                break

            if is_current is not None and not is_current():
                pygame.mixer.music.stop()
                break

            pygame.time.Clock().tick(20)

        pygame.mixer.music.unload()

    finally:

        try:
            os.remove(output_file)
        except:
            pass
