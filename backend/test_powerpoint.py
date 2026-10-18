from powerpoint_controller import ppt
import time

ppt.open_presentation(
    r"E:\AI-Presentation-Assistant project\backend\uploads\Grad1_Presentation.pptx"
)

time.sleep(2)

ppt.start_slideshow()

print("Presentation started!")