import speech_recognition as sr

recognizer = sr.Recognizer()


def listen(timeout=5, phrase_time_limit=15):

    try:

        with sr.Microphone() as source:

            print("\n🎤 Listening...")

            recognizer.adjust_for_ambient_noise(source, duration=1)

            try:
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit
                )

            except sr.WaitTimeoutError:
                print("⏰ No one spoke.")
                return None

    except Exception as e:

        # Covers microphone device conflicts (e.g. two callers trying
        # to open the mic at once) that used to raise unhandled
        # errors here and crash whatever thread called listen().
        print("Microphone error (recovering):", e)
        return None

    try:

        question = recognizer.recognize_google(audio)

        print(f"🗣 You said: {question}")

        return question

    except sr.UnknownValueError:

        print("❌ I couldn't understand.")

        return None

    except sr.RequestError:

        print("❌ Speech Recognition service unavailable.")

        return None

    except Exception as e:

        print(e)

        return None