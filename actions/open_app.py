# actions/open_app.py
# LEO — Direct App Launcher (subprocess-based, no searchbar)

import os
import sys
import glob
import shutil
import subprocess
import platform
import webbrowser
import time

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ── App paths for Windows (direct executable paths) ────────────
_WIN_APPS = {
    "notepad":       "notepad.exe",
    "calculator":    "calc.exe",
    "paint":         "mspaint.exe",
    "wordpad":       "write.exe",
    "cmd":           "cmd.exe",
    "powershell":    "powershell.exe",
    "terminal":      "wt.exe",
    "task manager":  "taskmgr.exe",
    "explorer":      "explorer.exe",
    "file explorer":  "explorer.exe",
    "snipping tool":  "SnippingTool.exe",
    "control panel":  "control.exe",
    "settings":       "ms-settings:",
    "store":          "ms-windows-store:",
}

# UWP / Store apps (launched via start command)
_WIN_UWP = {
    "whatsapp":      "whatsapp:",
    "telegram":      "telegram:",
    "spotify":       "spotify:",
    "netflix":       "netflix:",
    "tiktok":        "tiktok:",
    "xbox":          "xbox:",
    "photos":        "ms-photos:",
    "camera":        "microsoft.windows.camera:",
    "maps":          "bingmaps:",
    "mail":          "outlookmail:",
    "calendar":      "outlookcal:",
    "clock":         "ms-clock:",
    "weather":       "bingweather:",
}

# Desktop apps (search in common install paths)
_WIN_DESKTOP = {
    "chrome":        [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "firefox":       [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "edge":          [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "brave":         [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "vscode":        [
        r"C:\Users\*\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        r"C:\Program Files\Microsoft VS Code\Code.exe",
    ],
    "vs code":       [
        r"C:\Users\*\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        r"C:\Program Files\Microsoft VS Code\Code.exe",
    ],
    "discord":       [
        r"C:\Users\*\AppData\Local\Discord\Update.exe --processStart Discord.exe",
    ],
    "steam":         [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
    ],
    "vlc":           [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ],
    "obs":            [
        r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    ],
    "zoom":           [
        r"C:\Users\*\AppData\Roaming\Zoom\bin\Zoom.exe",
    ],
    "slack":          [
        r"C:\Users\*\AppData\Local\slack\slack.exe",
    ],
    "postman":        [
        r"C:\Users\*\AppData\Local\Postman\Postman.exe",
    ],
}

# Website shortcuts (open in default browser)
_WEBSITES = {
    "youtube":     "https://www.youtube.com",
    "google":      "https://www.google.com",
    "gmail":       "https://mail.google.com",
    "github":      "https://github.com",
    "chatgpt":     "https://chat.openai.com",
    "twitter":     "https://twitter.com",
    "x":           "https://twitter.com",
    "reddit":      "https://www.reddit.com",
    "instagram":   "https://www.instagram.com",
    "facebook":    "https://www.facebook.com",
    "linkedin":    "https://www.linkedin.com",
    "netflix":     "https://www.netflix.com",
    "amazon":      "https://www.amazon.com",
    "wikipedia":   "https://www.wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
}


def _normalize(raw: str) -> str:
    return raw.strip().lower().replace("_", " ")


def _find_exe(paths: list[str]) -> str | None:
    """Find first existing executable from a list of paths (supports glob)."""
    for p in paths:
        if "*" in p:
            matches = glob.glob(p)
            if matches:
                return matches[0]
        elif os.path.isfile(p):
            return p
    return None


def _launch_windows(app_name: str) -> tuple[bool, str]:
    """Launch app directly via subprocess — NO searchbar, NO pyautogui."""
    norm = _normalize(app_name)

    # 1. Check system apps (direct executables)
    if norm in _WIN_APPS:
        exe = _WIN_APPS[norm]
        try:
            if exe.endswith(":"):
                os.startfile(exe)
            else:
                subprocess.Popen(exe, shell=True)
            return True, f"Opened {app_name}"
        except Exception as e:
            return False, f"Failed: {e}"

    # 2. Check UWP/Store apps
    if norm in _WIN_UWP:
        uri = _WIN_UWP[norm]
        try:
            os.startfile(uri)
            return True, f"Opened {app_name}"
        except Exception as e:
            return False, f"Failed: {e}"

    # 3. Check websites (open in default browser)
    if norm in _WEBSITES:
        url = _WEBSITES[norm]
        webbrowser.open(url)
        return True, f"Opened {url} in default browser"

    # 4. Check desktop apps (find executable path)
    if norm in _WIN_DESKTOP:
        exe = _find_exe(_WIN_DESKTOP[norm])
        if exe:
            try:
                subprocess.Popen([exe], shell=True)
                return True, f"Opened {app_name}"
            except Exception as e:
                return False, f"Failed: {e}"

    # 5. Try shutil.which (finds apps on PATH)
    which = shutil.which(norm) or shutil.which(app_name)
    if which:
        try:
            subprocess.Popen([which], shell=True)
            return True, f"Opened {app_name}"
        except Exception as e:
            return False, f"Failed: {e}"

    # 6. Try 'start' command (Windows shell)
    try:
        subprocess.Popen(f'start "" "{app_name}"', shell=True)
        time.sleep(1)
        return True, f"Opened {app_name} via shell"
    except Exception:
        pass

    return False, f"Could not find {app_name}"


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()
    url      = (parameters or {}).get("url", "").strip()

    # If a URL is provided, open in default browser
    if url:
        webbrowser.open(url)
        print(f"[open_app] 🌐 Opened URL: {url}")
        return f"Opened {url} in your default browser."

    if not app_name:
        return "What app should I open?"

    system = platform.system()
    print(f"[open_app] 🚀 Launching: {app_name} ({system})")

    if system != "Windows":
        return f"Currently only Windows is supported for direct app launching."

    success, msg = _launch_windows(app_name)

    if success:
        print(f"[open_app] ✅ {msg}")
        return msg
    else:
        print(f"[open_app] ❌ {msg}")
        return msg