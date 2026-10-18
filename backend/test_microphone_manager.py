from microphone_manager import MicrophoneManager
import time

mic = None


def interrupted():
    print("Presentation interrupted!")
    mic.stop()


mic = MicrophoneManager()

mic.start(interrupted)

print("Say: Excuse me")

while mic.running:
    time.sleep(1)

print("Microphone stopped.")