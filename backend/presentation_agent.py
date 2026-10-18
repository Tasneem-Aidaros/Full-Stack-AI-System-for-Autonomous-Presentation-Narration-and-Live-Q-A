import time
import random

print("========== PRESENTATION_AGENT LOADED ==========")
print(__file__)

from ai_service import generate_presentation_scripts
from ai_service import answer_question as ai_answer_question
from powerpoint_controller import ppt
from knowledge_base import knowledge
from microphone_manager import MicrophoneManager
from speech_manager import SpeechManager
from stt_service import listen
from tts_service import speed_to_rate

# Used to estimate how many sentences correspond to ~10 seconds when
# seeking, since narration isn't a pre-recorded file with a known
# timeline — it's generated live, sentence by sentence. This is an
# approximation (average spoken English, adjusted by playback speed),
# not frame-accurate seeking.
WORDS_PER_SECOND_AT_1X = 2.3
SEEK_SECONDS = 10


class PresentationAgent:

    def __init__(self):

        self.slide_scripts = {}
        self.slides = []
        self.chat_history = []

        self.running = False
        self.interrupted = False
        self.current_slide = 0

        # Playback pause (distinct from a full Stop — pausing keeps
        # PowerPoint open and the session alive, just holds position).
        self.paused = False

        # Position within the current slide's sentence list, kept up
        # to date continuously so Pause, Stop, and "Continue" (a full
        # restart that resumes instead of starting over) all know
        # exactly where to pick back up.
        self.sentence_index = 0

        # Signed seconds to jump when a seek is requested (+10 or
        # -10). Consumed by _speak_script between sentences.
        self.seek_delta_seconds = 0

        # Set True whenever set_speed() is called while something is
        # playing, so the current sentence gets cut and re-spoken at
        # the new rate immediately instead of only affecting the
        # NEXT sentence.
        self.speed_changed = False

        # Set to a slide number by jump_to_slide()/next_slide()/
        # previous_slide() for manual navigation. Consumed by the
        # main loop in start(), which abandons whatever's currently
        # playing and jumps PowerPoint + narration there directly.
        self.pending_slide_jump = None

        # Playback speed, as a friendly multiplier (0.5x - 2.0x).
        # Converted to edge-tts's rate string via speed_to_rate().
        self.speech_rate = 1.0

        # The sentence currently being spoken, for a frontend to poll
        # via GET /subtitle and display as a live caption.
        self.current_subtitle = ""

        # Tells the frontend HOW to label current_subtitle: plain
        # slide narration, vs. the presenter acknowledging a question,
        # vs. showing back what was heard/typed (so the person can
        # catch a mishearing), vs. speaking the answer.
        # One of: narration, acknowledging, question, answering.
        self.subtitle_mode = "narration"

        # Coarse-grained status for a frontend to poll via
        # GET /presentation-status, since /start_presentation returns
        # immediately without waiting to see if it actually succeeds.
        # One of: idle, generating_script, opening_powerpoint,
        # presenting, finished, stopped, error.
        self.status = "idle"
        self.status_message = ""

        self.microphone = MicrophoneManager()
        self.speech = SpeechManager()

        # Holds a typed question waiting to be answered. Only one at
        # a time — submitting a new typed question before the current
        # one has been handled replaces it, rather than queuing an
        # unbounded backlog.
        self.pending_typed_question = None

    # ---------------------------------
    # Typed questions (the "write" option)
    # ---------------------------------
    def submit_typed_question(self, question):
        """
        Lets a typed question interrupt the live presentation the
        same way a spoken "excuse me" would — narration pauses,
        the question gets answered through the same speech pipeline,
        and narration resumes from where it left off. Called from
        the API thread, NOT the presentation loop thread, so this
        only sets flags; the main loop in start() picks it up between
        sentences, same as a spoken interrupt does.
        """

        self.pending_typed_question = question
        self.interrupted = True

    # ---------------------------------
    # Status
    # ---------------------------------
    def get_status(self):

        return {
            "status": self.status,
            "message": self.status_message,
            "current_slide": self.current_slide,
            "total_slides": len(self.slides),
            "paused": self.paused,
            "audio_error": self.speech.last_error,
        }

    # ---------------------------------
    # Playback controls: pause / resume / seek
    # (all just set flags — _speak_script, running in the
    # presentation thread, is what actually acts on them)
    # ---------------------------------
    def pause_playback(self):

        self.paused = True

    def resume_playback(self):

        self.paused = False

    def seek(self, seconds):

        self.seek_delta_seconds = seconds

    def _estimate_seconds(self, sentence):
        """
        Rough spoken-duration estimate for one sentence, from its word
        count and the current playback speed. Not measured from real
        audio — edge-tts audio is generated on demand, so there's no
        duration to know ahead of time. Good enough to make "back/
        forward 10 seconds" land on a sensible nearby sentence.
        """

        words = max(1, len(sentence.split()))

        return words / (WORDS_PER_SECOND_AT_1X * self.speech_rate)

    def _resolve_seek(self, sentences, current_index, seconds):
        """
        Walks forward or backward through `sentences` from
        current_index, accumulating estimated durations, until it's
        covered roughly `seconds` worth of speech (or hits the start/
        end of the slide, whichever comes first — seeking does not
        cross slide boundaries).
        """

        remaining = abs(seconds)
        step = 1 if seconds > 0 else -1
        index = current_index

        while remaining > 0:

            next_index = index + step

            if next_index < 0 or next_index >= len(sentences):
                break

            index = next_index
            remaining -= self._estimate_seconds(sentences[index])

        return index

    # ---------------------------------
    # Speed control
    # ---------------------------------
    def set_speed(self, multiplier):

        multiplier = max(0.5, min(2.0, float(multiplier)))

        self.speech_rate = multiplier

        # If something is currently playing, cut it and re-speak the
        # same sentence at the new rate right away, instead of only
        # applying the new speed starting from the NEXT sentence.
        if self.running:
            self.speed_changed = True

        return self.speech_rate

    # ---------------------------------
    # Manual slide navigation
    # ---------------------------------
    def jump_to_slide(self, slide_number):

        if not self.slides:
            return

        slide_number = max(1, min(len(self.slides), int(slide_number)))

        if slide_number == self.current_slide:
            # Already there (e.g. "next" from the last slide, or
            # "previous" from the first) — nothing to do, and setting
            # the jump flag anyway would just restart this same
            # slide's narration from its first sentence.
            return

        self.pending_slide_jump = slide_number

    def next_slide(self):

        self.jump_to_slide(self.current_slide + 1)

    def previous_slide(self):

        self.jump_to_slide(self.current_slide - 1)

    # ---------------------------------
    # Explain-on-demand helpers
    # (used by main.py's /explain route)
    # ---------------------------------
    def set_current_slide(self, slide_number):

        self.current_slide = slide_number

    def get_script(self, slide_number):

        return self.slide_scripts.get(slide_number)

    def save_script(self, slide_number, script):

        self.slide_scripts[slide_number] = script

    # ---------------------------------
    # Speak a single utterance (acknowledgment / answer) — NOT slide
    # narration. Same instant Pause/Stop/Speed response as
    # _speak_script, but for one block of text rather than a list of
    # sentences. A Pause here re-speaks the SAME utterance from its
    # start on Resume (not mid-utterance — Q&A answers aren't split
    # into sentences the way slide scripts are), but Stop/Speed still
    # take effect within ~50ms either way.
    # ---------------------------------
    def _speak_now(self, text):

        # Seeking has no defined meaning for a single Q&A utterance
        # (there's no sentence list to seek within) — discard any
        # pending seek now rather than letting it silently apply to
        # slide narration later, which would be a confusing surprise.
        self.seek_delta_seconds = 0

        while True:

            if not self.running:
                return

            if self.paused:

                while self.paused and self.running:
                    time.sleep(0.1)

                if not self.running:
                    return

            self.seek_delta_seconds = 0

            rate = speed_to_rate(self.speech_rate)
            self.speech.start(text, rate=rate)

            def should_continue():
                return self.running and not self.paused and not self.speed_changed

            finished_naturally = self.speech.wait(should_continue=should_continue)

            if not finished_naturally:
                self.speech.stop()
                self.speed_changed = False
                continue

            return

    # ---------------------------------
    # Real Question Handler
    # ---------------------------------
    def handle_question(self):

        print("\n==============================")
        print("QUESTION MODE")
        print("==============================")

        # Pause the always-on wake-word listener so it isn't racing
        # this capture for the microphone (that race is what produced
        # duplicate/garbled transcripts before), and so it doesn't
        # mistake our own spoken answer for a new wake word.
        self.microphone.pause()

        self.subtitle_mode = "acknowledging"

        try:

            if self.pending_typed_question is not None:

                # Typed path: the question is already known, no need
                # to speak an acknowledgment or listen on the mic.
                question = self.pending_typed_question
                self.pending_typed_question = None

                print(f"Typed question received: {question}")

            else:

                # Spoken path: acknowledge immediately so the audience
                # knows they were heard, instead of dead air while we
                # listen for their actual question and wait on Gemini.
                acknowledgment = random.choice([
                    "Yes, go ahead.",
                    "Sure, what's your question?",
                    "Yes?"
                ])

                self.current_subtitle = acknowledgment
                self._speak_now(acknowledgment)

                if not self.running:
                    return False

                question = listen(timeout=6, phrase_time_limit=15)

                if not question:

                    print("No question detected. Resuming presentation...")
                    self.current_subtitle = ""
                    self.subtitle_mode = "narration"

                    return True

            # Show exactly what was heard/typed BEFORE sending it to
            # Gemini, so it's visible on GET /subtitle long enough
            # (through the whole answer-generation round trip) for
            # the person to catch a mishearing before the AI answers
            # the wrong thing.
            self.subtitle_mode = "question"
            self.current_subtitle = question

            current_text = ""

            if self.slides and 1 <= self.current_slide <= len(self.slides):
                current_text = self.slides[self.current_slide - 1]["text"]

            # Only send the slides actually relevant to this question,
            # instead of the entire deck, mirroring what /ask does.
            # Smaller prompt = fewer tokens (less quota) AND a faster
            # round trip — this isn't a quota/speed tradeoff, it's a
            # win on both at once.
            relevant_slides = knowledge.search(question)

            if relevant_slides:
                presentation_text = "\n".join(
                    f"Slide {slide['number']}\n{slide['text']}"
                    for slide in relevant_slides
                )
            else:
                presentation_text = "\n".join(
                    f"Slide {slide['slide']}\n{slide['text']}"
                    for slide in self.slides
                )

            try:

                answer = ai_answer_question(
                    question=question,
                    current_slide=current_text,
                    presentation=presentation_text,
                    history=self.chat_history
                )

                self.chat_history.append({
                    "user": question,
                    "assistant": answer
                })

                # Speak through the same SpeechManager the slide
                # narration uses, instead of a separate direct TTS
                # call, so there's only ever one thread touching
                # playback at a time.
                self.subtitle_mode = "answering"
                self.current_subtitle = answer
                self._speak_now(answer)

            except Exception as e:

                print("Failed to answer question.")
                print(e)

        finally:

            self.current_subtitle = ""
            self.subtitle_mode = "narration"
            self.microphone.resume()

        return True

    # ---------------------------------
    # Speak a slide's script one sentence at a time
    # ---------------------------------
    def _speak_script(self, sentences, start_index=0):
        """
        Speaks a list of sentences one at a time (instead of one big
        paragraph), updating self.current_subtitle before each one so
        a frontend polling GET /subtitle sees a live caption.

        Uses SpeechManager.wait()'s polling mode (should_continue),
        so control signals — Stop, Pause, Seek, a speed change, or a
        manual slide jump — cut the CURRENT sentence's audio within
        about 50ms, rather than only being noticed after that
        sentence finishes naturally.

        self.sentence_index is kept up to date on every iteration —
        not just at return — so Pause, Stop, and "Continue" always
        know exactly where playback actually is, even mid-sentence.

        Returns:
            None if it played through to the end, was stopped, or was
            abandoned for a manual slide jump (check
            self.pending_slide_jump to tell those apart).
            The sentence index to resume from, if cut short by an
            audience interruption (true resume, not a restart).
        """

        i = start_index

        while i < len(sentences):

            self.sentence_index = i

            if not self.running or self.pending_slide_jump is not None:
                self.current_subtitle = ""
                return None

            if self.paused:

                self.current_subtitle = "⏸ Paused"

                while self.paused and self.running and self.pending_slide_jump is None:
                    time.sleep(0.1)

                if not self.running or self.pending_slide_jump is not None:
                    self.current_subtitle = ""
                    return None

                # Resumed — re-speak the same sentence we paused on,
                # don't skip ahead.
                continue

            if self.seek_delta_seconds != 0:

                i = self._resolve_seek(sentences, i, self.seek_delta_seconds)
                self.seek_delta_seconds = 0
                self.sentence_index = i
                continue

            if self.speed_changed:
                self.speed_changed = False
                continue  # re-speak the same sentence, at the new rate

            if self.interrupted:
                return i

            sentence = sentences[i]

            self.current_subtitle = sentence

            rate = speed_to_rate(self.speech_rate)
            self.speech.start(sentence, rate=rate)

            def should_continue():
                return (
                    self.running
                    and not self.paused
                    and self.seek_delta_seconds == 0
                    and not self.speed_changed
                    and not self.interrupted
                    and self.pending_slide_jump is None
                )

            finished_naturally = self.speech.wait(should_continue=should_continue)

            if not finished_naturally:
                # One of the control signals above fired mid-sentence.
                # Cut the audio right now instead of letting it finish
                # — this is what makes Stop/Seek/Speed/Jump feel
                # instant. The top of the loop will notice which
                # signal fired on the next iteration and act on it.
                self.speech.stop()
                continue

            if self.speech.last_error:

                # The voice failed for this sentence (the reason is in
                # the Backend window and in GET /presentation-status).
                # Keep the caption on screen for about as long as it
                # would have taken to say, instead of racing through
                # every slide silently.
                deadline = time.time() + self._estimate_seconds(sentence)

                while time.time() < deadline and should_continue():
                    time.sleep(0.05)

                if not should_continue():
                    continue

            i += 1

        self.current_subtitle = ""
        self.sentence_index = 0

        return None

    # ---------------------------------
    # Start Presentation
    # ---------------------------------
    def start(self, presentation_path, slides, resume=False):
        """
        Runs a whole presentation. Wraps _run so an unexpected exception
        can never leave the agent stuck as "running" with PowerPoint open
        and the microphone listening.
        """

        # Prevent starting twice
        if self.running:
            return "Presentation is already running."

        try:
            return self._run(presentation_path, slides, resume)

        except Exception as e:

            print("Presentation crashed:", e)

            self.status = "error"
            self.status_message = str(e)

            return "Presentation failed."

        finally:

            if self.running:
                self.running = False
                self.current_subtitle = ""

                self.microphone.stop()
                self.speech.stop()

                try:
                    ppt.end_show()
                except Exception:
                    pass

                try:
                    ppt.close()
                except Exception:
                    pass

    def _run(self, presentation_path, slides, resume):

        self.running = True
        self.interrupted = False
        self.paused = False
        self.seek_delta_seconds = 0
        self.slides = slides
        self.current_subtitle = ""
        self.subtitle_mode = "narration"
        self.status = "starting"
        self.status_message = ""

        if resume and self.current_slide > 0:
            # "Continue" — keep the slide/sentence position and chat
            # history from before the last Stop, don't reset them.
            print(f"Resuming from slide {self.current_slide}, sentence {self.sentence_index}")
        else:
            self.chat_history = []
            self.current_slide = 0
            self.sentence_index = 0

        # Start microphone
        self.microphone.start(self.interrupt)

        # -------------------------------------------------
        # Generate the script ONLY if we don't already have
        # one (e.g. main.py already generated it on upload).
        # -------------------------------------------------
        if not self.slide_scripts:

            print("\nPreparing presentation...")
            print("Generating presentation script...")

            self.status = "generating_script"

            try:

                self.slide_scripts = generate_presentation_scripts(slides)

                print("Presentation script generated successfully!")

            except Exception as e:

                print("Failed to generate presentation.")
                print(e)

                self.running = False
                self.status = "error"
                self.status_message = str(e)
                self.microphone.stop()

                return "Failed to generate presentation."

        # Build knowledge base up front so questions can be
        # answered as soon as the presentation starts, not
        # only after it ends.
        try:
            knowledge.build(slides, self.slide_scripts)
            print("Knowledge Base Ready!")
        except Exception as e:
            print("Failed to build knowledge base.")
            print(e)

        # Open PowerPoint
        self.status = "opening_powerpoint"

        ppt.open_presentation(presentation_path)
        ppt.start_slideshow()

        start_slide_index = 0

        if resume and self.current_slide > 1:

            try:
                ppt.goto_slide(self.current_slide)
            except Exception as e:
                print("Could not jump to saved slide, starting from slide 1:", e)
                self.current_slide = 1
                self.sentence_index = 0

            start_slide_index = self.current_slide - 1

        self.status = "presenting"

        # -------------------------
        # Presentation Loop
        # (a while loop, not a for loop, because manual slide
        # navigation needs to be able to jump to an arbitrary index —
        # not just step to index+1)
        # -------------------------
        index = start_slide_index
        first_iteration = True

        while index < len(slides):

            print("\n================================")
            print(f"LOOP START -> Slide {index + 1}")
            print("================================")

            if not self.running:
                print("Presentation stopped.")
                break

            slide_number = index + 1
            self.current_slide = slide_number

            print(f"Presenting Slide {slide_number}")

            script = self.slide_scripts.get(
                slide_number,
                ["Unable to generate this slide."]
            )

            print(f"Slide {slide_number} Ready.")

            # -------------------------
            # Speak (sentence by sentence, with subtitles)
            # -------------------------
            print("Starting speech...")

            # Only the very first slide of this run picks up mid-way
            # through (when resuming) — every slide after that,
            # including ones we manually jump to, starts at sentence 0.
            if first_iteration and resume:
                resume_index = self.sentence_index
            else:
                resume_index = 0

            first_iteration = False

            while True:

                resume_index = self._speak_script(script, start_index=resume_index)

                if not self.running:
                    break

                if self.pending_slide_jump is not None:
                    # Manual navigation abandoned this slide — handled
                    # after this inner loop, below.
                    break

                if resume_index is None:
                    # Played through to the end of this slide's script.
                    break

                # We got here because an audience question interrupted
                # mid-slide. Handle it, then loop back and continue
                # from the exact sentence we stopped at.
                print("🎤 Audience interrupted.")

                self.interrupted = False

                print("Waiting for audience question...")

                continue_presenting = self.handle_question()

                if not continue_presenting:
                    self.running = False
                    break

                print("Resuming current slide...")

            print("Speech finished.")

            if not self.running:
                break

            # -------------------------
            # Manual slide jump (Next / Previous / go-to-slide)
            # -------------------------
            if self.pending_slide_jump is not None:

                target = self.pending_slide_jump
                self.pending_slide_jump = None

                print(f"Manual navigation -> slide {target}")

                try:
                    ppt.goto_slide(target)
                except Exception as e:
                    print("PowerPoint Error on manual navigation:", e)
                    self.status = "error"
                    self.status_message = str(e)
                    break

                self.sentence_index = 0
                index = target - 1

                continue

            # -------------------------
            # Next Slide (automatic)
            # -------------------------
            if slide_number < len(slides):

                print("Moving to next slide...")

                try:

                    ppt.next_slide()

                    print("Moved successfully.")

                except Exception as e:

                    print("PowerPoint Error:", e)

                    self.status = "error"
                    self.status_message = str(e)

                    break

            index += 1

        print("\nPresentation loop finished.")

        # -------------------------
        # Cleanup
        # -------------------------
        self.running = False

        # Only mark "finished" if nothing already flagged this run as
        # having stopped early or errored — those should stick so the
        # frontend can tell the difference between "done" and "broke".
        if self.status not in ("error", "stopped"):
            self.status = "finished"

        self.current_subtitle = ""

        self.microphone.stop()

        self.speech.stop()

        try:
            ppt.end_show()
        except Exception:
            pass

        try:
            ppt.close()
        except Exception:
            pass

        return "Presentation Finished"

    # ---------------------------------
    # Stop Presentation
    # ---------------------------------
    def stop(self):

        print("Stopping presentation...")

        self.running = False
        self.interrupted = False
        self.current_subtitle = ""
        self.subtitle_mode = "narration"
        self.status = "stopped"
        self.status_message = ""

        self.microphone.stop()
        self.speech.stop()

        try:
            ppt.end_show()
        except Exception:
            pass

        try:
            ppt.close()
        except Exception:
            pass

    # ---------------------------------
    # Called by MicrophoneManager
    # ---------------------------------
    def interrupt(self):

        print("🎤 Audience interruption detected!")

        # Pause the background listener HERE, synchronously, because
        # this method runs inside the background mic thread's own
        # call stack (it's called directly from listen_loop). If we
        # waited for the main thread's handle_question() to pause it
        # instead, the background loop would race ahead and reopen
        # the microphone before handle_question() gets a chance to —
        # two threads holding the mic open at once is what was
        # crashing (and permanently killing) the listener thread.
        self.microphone.pause()

        self.interrupted = True


agent = PresentationAgent()
