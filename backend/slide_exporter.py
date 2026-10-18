import os
import threading

import pythoncom
import win32com.client

# How long to wait for PowerPoint before giving up. If PowerPoint is
# stuck on a dialog box (Protected View, "save changes?", sign-in
# prompt, ...), COM calls block forever, so without this the upload
# would hang with no message at all.
EXPORT_TIMEOUT_SECONDS = 90


def _export_worker(ppt_path, output_folder, result):

    # COM must be initialised in every thread that uses it.
    pythoncom.CoInitialize()

    powerpoint = None
    presentation = None
    started_by_us = False

    try:

        print("Slide export: connecting to PowerPoint...")

        try:
            # Reuse PowerPoint if the user already has it open.
            powerpoint = win32com.client.GetActiveObject("PowerPoint.Application")
        except Exception:
            powerpoint = win32com.client.Dispatch("PowerPoint.Application")
            started_by_us = True

        print("Slide export: opening the file...")

        # Read-only and without a window: nothing to save, so closing
        # can never trigger a "save changes?" prompt, and no extra
        # window pops up.
        presentation = powerpoint.Presentations.Open(
            os.path.abspath(ppt_path),
            ReadOnly=True,
            Untitled=False,
            WithWindow=False
        )

        print("Slide export: exporting slides as images...")

        presentation.Export(os.path.abspath(output_folder), "PNG")

        result["ok"] = True

    except Exception as e:

        result["error"] = e

    finally:

        try:
            if presentation is not None:
                presentation.Close()
        except Exception:
            pass

        # Only quit PowerPoint if WE started it. If the user already
        # had it open, quitting would close their windows and can
        # prompt to save their other presentations.
        try:
            if powerpoint is not None and started_by_us:
                powerpoint.Quit()
        except Exception:
            pass

        pythoncom.CoUninitialize()


def export_slides(ppt_path):

    output_folder = "slide_images"
    os.makedirs(output_folder, exist_ok=True)

    result = {}

    worker = threading.Thread(
        target=_export_worker,
        args=(ppt_path, output_folder, result),
        daemon=True
    )

    worker.start()
    worker.join(EXPORT_TIMEOUT_SECONDS)

    if worker.is_alive():
        raise TimeoutError(
            f"PowerPoint did not respond within {EXPORT_TIMEOUT_SECONDS} seconds. "
            "Look for a dialog box in PowerPoint (Protected View, save prompt, "
            "sign-in) and close it, or close all PowerPoint windows and try again."
        )

    if "error" in result:
        raise result["error"]

    print("Slides exported successfully!")

    return output_folder
