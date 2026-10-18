import threading
import time

from stt_service import listen


class MicrophoneManager:

    def __init__(self):

        self.running = False
        self.callback = None
        self.paused = False

    def start(self, callback):

        self.callback = callback
        self.running = True
        self.paused = False

        threading.Thread(
            target=self.listen_loop,
            daemon=True
        ).start()

    def stop(self):

        self.running = False

    # -------------------------------------------------
    # Pause / resume wake-word listening without tearing
    # down the thread. Used while a question is actively
    # being captured/answered, so this loop isn't fighting
    # that code for the microphone (and doesn't mistake our
    # own spoken answer for a new wake word).
    # -------------------------------------------------
    def pause(self):

        self.paused = True

    def resume(self):

        self.paused = False

    def listen_loop(self):

        while self.running:

            if self.paused:

                time.sleep(0.2)
                continue

            try:

                text = listen()

                if text is None:
                    continue

                text = text.lower()

                wake_words = [
                    "excuse me",
                    "question",
                    "can i ask",
                    "hey presenter"
                ]

                if any(word in text for word in wake_words):

                    print("🎤 Audience wants to ask a question.")

                    self.callback()

            except Exception as e:

                # Never let an unexpected error (e.g. a microphone
                # device conflict) silently kill this thread — that
                # would permanently disable wake-word detection for
                # the rest of the presentation with no way to recover.
                print("Microphone listener error (recovering):", e)
                time.sleep(0.5)