from ppt_reader import read_presentation
from ai_service import explain_slide

slides = read_presentation("uploads/Grad1_Presentation.pptx")

first_slide = slides[0]

print("Slide:", first_slide["slide"])
print()

explanation = explain_slide(first_slide["text"])

print(explanation)