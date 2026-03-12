# actions/whatsapp_call.py
# LEO — WhatsApp Desktop Voice / Video Call
# Uses pyautogui UI automation to navigate WhatsApp Desktop and initiate calls.

import time
import subprocess
import platform

try:
    import pyautogui
    pyautogui.PAUSE = 0.3
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False


def _focus_whatsapp() -> bool:
    """Bring WhatsApp Desktop to the foreground."""
    if platform.system() != "Windows":
        return False
    try:
        # Try to bring WhatsApp window to front via PowerShell
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$wshell = New-Object -ComObject wscript.shell; "
             "$procs = Get-Process | Where-Object {$_.MainWindowTitle -like '*WhatsApp*'}; "
             "if ($procs) { $wshell.AppActivate($procs[0].Id) }"],
            capture_output=True, timeout=5
        )
        time.sleep(1)
        return True
    except Exception as e:
        print(f"[WhatsApp] ⚠️ Could not focus WhatsApp: {e}")
        return False


def _search_contact(name: str) -> bool:
    """Search for a contact in WhatsApp Desktop."""
    if not _HAS_PYAUTOGUI:
        return False
    try:
        # Open search with Ctrl+F
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)

        # Clear any existing search text
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)

        # Type the contact name
        pyautogui.write(name, interval=0.05)
        time.sleep(2)  # Wait for search results to appear

        # Press Enter to select the first result
        pyautogui.press("enter")
        time.sleep(1)

        return True
    except Exception as e:
        print(f"[WhatsApp] ⚠️ Could not search contact: {e}")
        return False


def _click_call_button(video: bool = False) -> bool:
    """Click the voice or video call button in the chat header."""
    if not _HAS_PYAUTOGUI:
        return False
    try:
        screen_w, screen_h = pyautogui.size()

        # In WhatsApp Desktop, the call buttons are in the top-right area
        # of the chat window. Voice call icon is typically at:
        # ~85% from left, ~6% from top
        # Video call icon is slightly to the left of voice call

        if video:
            # Video call button - slightly to the left
            click_x = int(screen_w * 0.82)
        else:
            # Voice call button - rightmost icon area
            click_x = int(screen_w * 0.85)

        click_y = int(screen_h * 0.06)

        pyautogui.click(click_x, click_y)
        time.sleep(1)

        # WhatsApp shows a confirmation dialog — click the call button
        # The green call button in the popup is roughly center-screen
        pyautogui.click(screen_w // 2, int(screen_h * 0.55))
        time.sleep(1)

        return True
    except Exception as e:
        print(f"[WhatsApp] ⚠️ Could not click call button: {e}")
        return False


# ── Public entry point ─────────────────────────────────────────

def whatsapp_call(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    WhatsApp call controller entry point (called by main.py).

    parameters:
        action  : call | video_call
        contact : Contact name to call
    """
    if not _HAS_PYAUTOGUI:
        return "pyautogui is not installed. Run: pip install pyautogui"

    params  = parameters or {}
    action  = params.get("action", "call").strip().lower()
    contact = params.get("contact", "").strip()

    if not contact:
        return "No contact name specified. Who should I call?"

    print(f"[WhatsApp] 📞 Action: {action}  Contact: {contact}")

    # Step 1: Focus WhatsApp Desktop
    if not _focus_whatsapp():
        # Try opening WhatsApp
        try:
            subprocess.Popen(["cmd", "/c", "start", "whatsapp:"], shell=True)
            time.sleep(3)
            _focus_whatsapp()
        except Exception:
            return "Could not open WhatsApp Desktop. Please make sure it's installed and running."

    # Step 2: Search for the contact
    if not _search_contact(contact):
        return f"Could not find contact '{contact}' in WhatsApp."

    # Step 3: Click the call button
    is_video = action in ("video_call", "video")

    if _click_call_button(video=is_video):
        call_type = "video" if is_video else "voice"
        return f"Calling {contact} on WhatsApp ({call_type} call)."
    else:
        return f"Could not initiate call to {contact}. Please try manually."
