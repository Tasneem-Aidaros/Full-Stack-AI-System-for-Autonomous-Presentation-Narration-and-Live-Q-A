import win32com.client
import pythoncom
import time
import os


class PowerPointController:

    def __init__(self):
        self.app = None
        self.presentation = None
        self.slide_show = None

    def open_presentation(self, file_path):

        pythoncom.CoInitialize()

        self.app = win32com.client.Dispatch("PowerPoint.Application")
        self.app.Visible = True

        absolute_path = os.path.abspath(file_path)
        print("Opening:", absolute_path)

        self.presentation = self.app.Presentations.Open(absolute_path)

        print("Presentation opened!")

    def start_slideshow(self):

        self.slide_show = self.presentation.SlideShowSettings.Run()

        time.sleep(1)

        print("Slide show started!")

    def next_slide(self):

        self.slide_show.View.Next()

    def previous_slide(self):

        self.slide_show.View.Previous()

    def goto_slide(self, slide_number):

        self.slide_show.View.GotoSlide(slide_number)

    def current_slide(self):

        return self.slide_show.View.CurrentShowPosition

    def end_show(self):

        if self.slide_show:
            self.slide_show.View.Exit()

    def close(self):

        if self.presentation:
            self.presentation.Close()

        if self.app:
            self.app.Quit()

        # Uninitialize COM
        pythoncom.CoUninitialize()


ppt = PowerPointController()