from ai_service import answer_question as ai_answer
from tts_service import speak


def answer_question(
    question,
    current_slide,
    presentation,
    history,
    speak_answer=True
):

    answer = ai_answer(
        question=question,
        current_slide=current_slide,
        presentation=presentation,
        history=history
    )

    if speak_answer:
        speak(answer)

    return answer