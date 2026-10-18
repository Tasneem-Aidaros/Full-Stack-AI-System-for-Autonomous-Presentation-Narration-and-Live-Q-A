from ppt_reader import read_presentation

slides = read_presentation("uploads/Grad1_Presentation.pptx")

for slide in slides:
    print(slide)