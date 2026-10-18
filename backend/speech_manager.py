import threading
import time
from tts_service import speak, stop_speaking


class SpeechManager:

    def __init__(self):

        self.thread = None
        self.busy = False
        self.lock = threading.Lock()

        # Bumped on every start() and stop(). A worker thread checks
        # "is my token still current?" right after it finishes
        # generating audio (the part that can't be interrupted
        # directly, since it's a network call) — if not, it skips
        # playback entirely instead of playing something nobody
        # wants anymore just because it was already in flight.
        self.token = 0

        # Why the most recent utterance could not be spoken (empty when
        # it worked). Surfaced through GET /presentation-status so the
        # web page can say "no sound: <reason>" instead of failing
        # silently.
        self.last_error = ""

    # -------------------------
    # Worker
    # -------------------------
    def _worker(self, text, rate, token):

        try:
            speak(text, rate=rate, is_current=lambda: token == self.token)

            if token == self.token:
                self.last_error = ""

        except Exception as e:

            message = f"{type(e).__name__}: {e}"

            print("Speech failed:", message)

            if token == self.token:
                self.last_error = message

        finally:

            with self.lock:
                # Only clear busy if nothing newer has already
                # superseded this utterance (start()/stop() bump the
                # token, which also implies "not busy" from their own
                # code path — don't let a late-finishing stale worker
                # incorrectly mark a NEWER utterance as no longer busy).
                if token == self.token:
                    self.busy = False

    # -------------------------
    # Start Speaking
    # -------------------------
    def start(self, text, rate="+0%"):

        with self.lock:

            if self.busy:
                return False

            self.busy = True
            self.token += 1
            my_token = self.token

        self.thread = threading.Thread(
            target=self._worker,
            args=(text, rate, my_token),
            daemon=True
        )

        self.thread.start()

        return True

    # -------------------------
    # Wait until finished — polls in short intervals instead of
    # blocking on an unbounded thread.join(), so a caller can pass
    # should_continue() and bail out within ~50ms of a control signal
    # (stop/pause/seek/etc) instead of only after the whole sentence
    # naturally finishes.
    # -------------------------
    def wait(self, poll_interval=0.05, should_continue=None):

        while self.busy:

            if should_continue is not None and not should_continue():
                return False

            time.sleep(poll_interval)

        return True

    # -------------------------
    # Stop Speaking
    # -------------------------
    def stop(self):

        with self.lock:
            # Bump the token FIRST. Any worker still generating audio
            # for the previous token will see it's stale the moment
            # generation finishes and skip playback — this is what
            # makes Stop feel instant even if it arrives mid-generation,
            # not just mid-playback.
            self.token += 1
            self.busy = False

        stop_speaking()

        if self.thread and self.thread.is_alive():
            # Short timeout: the thread is harmless now even if it
            # lingers a little (it'll see the stale token and exit on
            # its own), so we don't need to actually wait on it long.
            self.thread.join(timeout=0.3)
