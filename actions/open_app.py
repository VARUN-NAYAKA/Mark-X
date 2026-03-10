# actions/open_app.py
# LEO — App Launcher (based on proven app_launcher.py)
# Strategy: misrecognition fix → alias → PATH → Start Menu → UWP → websites → fallback

import os
import sys
import glob
import shutil
import subprocess
import webbrowser


# ============================================================
#  App Alias Table — maps spoken names → launch commands
# ============================================================

APP_ALIASES: dict[str, str] = {
    # Browsers
    "chrome":              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome":       r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "brave":               r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "brave browser":       r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "firefox":             "firefox",
    "edge":                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "microsoft edge":      r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "microsoft":           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",

    # Dev tools
    "vs code":             "code",
    "visual studio code":  "code",
    "vscode":              "code",
    "terminal":            "wt",
    "windows terminal":    "wt",
    "command prompt":      "cmd",
    "cmd":                 "cmd",
    "powershell":          "powershell",
    "git bash":            r"C:\Program Files\Git\git-bash.exe",

    # System utilities
    "notepad":             "notepad",
    "calculator":          "calc",
    "calc":                "calc",
    "file explorer":       "explorer",
    "explorer":            "explorer",
    "task manager":        "taskmgr",
    "settings":            "ms-settings:",
    "control panel":       "control",
    "paint":               "mspaint",
    "snipping tool":       "snippingtool",
    "snip":                "snippingtool",

    # Microsoft Office
    "word":                "winword",
    "excel":               "excel",
    "powerpoint":          "powerpnt",

    # Communication / Media
    "telegram":            "telegram",
    "discord":             "discord",
    "spotify":             "spotify",
    "vlc":                 "vlc",
    "zoom":                "zoom",
}

# Common misrecognitions → correct name
MISRECOGNITION_MAP: dict[str, str] = {
    "what's up":    "whatsapp",
    "whats up":     "whatsapp",
    "what sup":     "whatsapp",
    "whatapp":      "whatsapp",
    "watch out":    "whatsapp",
    "brew":         "brave",
    "brev":         "brave",
    "breve":        "brave",
    "drev":         "brave",
    "drift":        "brave",
    "v s code":     "vs code",
    "v.s. code":    "vs code",
    "vs core":      "vs code",
    "via code":     "vs code",
    "viscode":      "vs code",
    "chrom":        "chrome",
    "krom":         "chrome",
    "glock":        "clock",
    "block":        "clock",
}

# Spoken name → UWP search term
UWP_SEARCH_MAP: dict[str, str] = {
    "clock":        "alarms",
    "alarm":        "alarms",
    "alarms":       "alarms",
    "timer":        "alarms",
    "stopwatch":    "alarms",
    "camera":       "camera",
    "photos":       "photos",
    "mail":         "outlook",
    "outlook":      "outlook",
    "store":        "store",
    "maps":         "maps",
    "weather":      "weather",
    "whatsapp":     "whatsapp",
}

# Website shortcuts (fallback: open in default browser)
_WEBSITES: dict[str, str] = {
    "youtube":       "https://www.youtube.com",
    "google":        "https://www.google.com",
    "gmail":         "https://mail.google.com",
    "github":        "https://github.com",
    "chatgpt":       "https://chat.openai.com",
    "twitter":       "https://twitter.com",
    "x":             "https://twitter.com",
    "reddit":        "https://www.reddit.com",
    "instagram":     "https://www.instagram.com",
    "facebook":      "https://www.facebook.com",
    "linkedin":      "https://www.linkedin.com",
    "netflix":       "https://www.netflix.com",
    "amazon":        "https://www.amazon.com",
    "wikipedia":     "https://www.wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
}


# ============================================================
#  Process Map (for closing apps)
# ============================================================

PROCESS_MAP: dict[str, list[str]] = {
    "chrome":             ["chrome.exe"],
    "google chrome":      ["chrome.exe"],
    "brave":              ["brave.exe"],
    "brave browser":      ["brave.exe"],
    "firefox":            ["firefox.exe"],
    "edge":               ["msedge.exe"],
    "microsoft edge":     ["msedge.exe"],
    "microsoft":          ["msedge.exe"],
    "vs code":            ["Code.exe"],
    "visual studio code": ["Code.exe"],
    "vscode":             ["Code.exe"],
    "terminal":           ["WindowsTerminal.exe"],
    "windows terminal":   ["WindowsTerminal.exe"],
    "command prompt":     ["cmd.exe"],
    "powershell":         ["powershell.exe"],
    "git bash":           ["git-bash.exe", "mintty.exe"],
    "notepad":            ["notepad.exe"],
    "calculator":         ["Calculator.exe", "CalculatorApp.exe"],
    "calc":               ["Calculator.exe", "CalculatorApp.exe"],
    "file explorer":      ["explorer.exe"],
    "task manager":       ["Taskmgr.exe"],
    "paint":              ["mspaint.exe"],
    "snipping tool":      ["SnippingTool.exe", "ScreenClippingHost.exe"],
    "control panel":      ["control.exe"],
    "settings":           ["SystemSettings.exe"],
    "word":               ["WINWORD.EXE"],
    "excel":              ["EXCEL.EXE"],
    "powerpoint":         ["POWERPNT.EXE"],
    "whatsapp":           ["WhatsApp.exe"],
    "telegram":           ["Telegram.exe"],
    "discord":            ["Discord.exe", "Update.exe"],
    "spotify":            ["Spotify.exe"],
    "vlc":                ["vlc.exe"],
    "zoom":               ["Zoom.exe"],
    "teams":              ["ms-teams.exe", "Teams.exe"],
    "slack":              ["slack.exe"],
}


# ============================================================
#  Start Menu shortcut search
# ============================================================

_SHORTCUT_DIRS = [
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
]


def _find_shortcut(app_name: str) -> str | None:
    """Fuzzy search Start Menu for a .lnk matching app_name."""
    app_lower = app_name.lower()
    for base in _SHORTCUT_DIRS:
        if not os.path.isdir(base):
            continue
        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            lnk_name = os.path.basename(lnk).lower().replace(".lnk", "")
            if app_lower in lnk_name or lnk_name in app_lower:
                return lnk
    return None


# ============================================================
#  UWP / Microsoft Store app search
# ============================================================

def _find_uwp_app(app_name: str) -> str | None:
    """Search installed UWP/Store apps via PowerShell."""
    search_term = UWP_SEARCH_MAP.get(app_name, app_name)
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"Get-AppxPackage -Name '*{search_term}*' | "
                f"Select-Object -First 1 -ExpandProperty PackageFamilyName"
            ],
            capture_output=True, text=True, timeout=8,
        )
        pfn = result.stdout.strip()
        if pfn:
            return f"shell:AppsFolder\\{pfn}!App"
    except Exception as e:
        print(f"[open_app] ⚠️ UWP search failed: {e}")
    return None


def _launch_uwp(uri: str) -> bool:
    """Launch a shell:AppsFolder URI."""
    try:
        os.system(f'start "" "{uri}"')
        return True
    except Exception as e:
        print(f"[open_app] ⚠️ UWP launch failed: {e}")
        return False


# ============================================================
#  Main Open App
# ============================================================

def _open_app_core(raw_name: str) -> str:
    """
    Open an application by spoken name.
    Strategy: fix misrecognitions → alias table → PATH lookup →
              Start Menu → UWP → websites → give up gracefully.
    """
    name = raw_name.strip().lower().rstrip(".")

    # 1. Fix common misrecognitions
    if name in MISRECOGNITION_MAP:
        name = MISRECOGNITION_MAP[name]

    display_name = name.title()

    # 2. Check alias table
    if name in APP_ALIASES:
        cmd = APP_ALIASES[name]
        try:
            if cmd.startswith("ms-"):
                os.startfile(cmd)
            elif os.path.isfile(cmd):
                subprocess.Popen([cmd], shell=False)
            else:
                subprocess.Popen(cmd, shell=True)
            print(f"[open_app] ✅ Alias: {name} → {cmd}")
            return f"Opening {display_name} for you."
        except Exception as e:
            print(f"[open_app] ⚠️ Alias failed for {name}: {e}")

    # 3. Check PATH
    exe = shutil.which(name)
    if exe:
        try:
            subprocess.Popen([exe], shell=False)
            print(f"[open_app] ✅ PATH: {name} → {exe}")
            return f"Opening {display_name} for you."
        except Exception as e:
            print(f"[open_app] ⚠️ PATH launch failed: {e}")

    # 4. Search Start Menu shortcuts
    lnk = _find_shortcut(name)
    if lnk:
        try:
            os.startfile(lnk)
            print(f"[open_app] ✅ Shortcut: {name} → {lnk}")
            return f"Opening {display_name} for you."
        except Exception as e:
            print(f"[open_app] ⚠️ Shortcut failed: {e}")

    # 5. Search UWP / Microsoft Store apps
    uwp_uri = _find_uwp_app(name)
    if uwp_uri:
        if _launch_uwp(uwp_uri):
            print(f"[open_app] ✅ UWP: {name}")
            return f"Opening {display_name} for you."

    # 6. Check if it's a website (fallback)
    if name in _WEBSITES:
        url = _WEBSITES[name]
        webbrowser.open(url)
        print(f"[open_app] ✅ Website: {name} → {url}")
        return f"Opened {url} in your default browser."

    return f"Sorry, I couldn't find {display_name} on your system."


# ============================================================
#  Close App
# ============================================================

def _close_app_core(raw_name: str) -> str:
    """
    Close an application by spoken name.
    Strategy: taskkill by known process → PowerShell wildcard → generic guess.
    """
    name = raw_name.strip().lower().rstrip(".")

    if name in MISRECOGNITION_MAP:
        name = MISRECOGNITION_MAP[name]

    display_name = name.title()

    # Tier 1: Known process mapping
    processes = PROCESS_MAP.get(name)
    if processes:
        killed = False
        for proc in processes:
            try:
                result = subprocess.run(
                    ["taskkill", "/IM", proc, "/F"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    killed = True
            except Exception:
                pass
        if killed:
            return f"Closed {display_name} for you."

    # Tier 2: PowerShell wildcard
    search_term = name.replace(" ", "")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process -Name '*{search_term}*' -ErrorAction SilentlyContinue | "
             f"Stop-Process -Force -ErrorAction SilentlyContinue; "
             f"if ($?) {{ 'KILLED' }} else {{ 'NONE' }}"],
            capture_output=True, text=True, timeout=8,
        )
        if "KILLED" in result.stdout:
            return f"Closed {display_name} for you."
    except Exception:
        pass

    # Tier 3: Generic guess
    for guess in [f"{name}.exe", f"{search_term}.exe"]:
        try:
            result = subprocess.run(
                ["taskkill", "/IM", guess, "/F"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return f"Closed {display_name} for you."
        except Exception:
            pass

    return f"Sorry, I couldn't close {display_name}. It may not be running."


# ============================================================
#  System Commands (shutdown, restart, lock, sleep)
# ============================================================

def _system_command(command: str) -> str:
    """Shutdown, restart, lock, sleep, hibernate, sign out."""
    cmd = command.strip().lower()

    try:
        if cmd in ["shutdown", "shut down", "power off", "turn off",
                    "shutdown pc", "turn off pc", "turn off the computer"]:
            subprocess.Popen(["shutdown", "/s", "/t", "5"], shell=True)
            return "Shutting down your computer in 5 seconds."

        elif cmd in ["restart", "reboot", "re start"]:
            subprocess.Popen(["shutdown", "/r", "/t", "5"], shell=True)
            return "Restarting your computer in 5 seconds."

        elif cmd in ["cancel shutdown", "cancel restart", "cancel", "abort"]:
            subprocess.run(["shutdown", "/a"], capture_output=True)
            return "Shutdown cancelled."

        elif cmd in ["lock", "lock screen", "lock computer", "lock the screen",
                      "lock pc", "lock my pc"]:
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
            return "Locking your screen."

        elif cmd in ["sleep", "sleep mode", "sleep pc", "put pc to sleep",
                      "put my pc to sleep", "put computer to sleep"]:
            import ctypes, threading
            def _do_sleep():
                import time as _t
                _t.sleep(4)
                HWND_BROADCAST  = 0xFFFF
                WM_SYSCOMMAND   = 0x0112
                SC_MONITORPOWER = 0xF170
                MONITOR_OFF     = 2
                ctypes.windll.user32.SendMessageW(
                    HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF
                )
            threading.Thread(target=_do_sleep, daemon=True).start()
            return "Putting your computer to sleep. Goodnight!"

        elif cmd in ["hibernate", "hibernate pc"]:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName System.Windows.Forms; "
                 "[System.Windows.Forms.Application]::SetSuspendState('Hibernate', $false, $false)"]
            )
            return "Hibernating your computer."

        elif cmd in ["sign out", "log out", "log off", "sign off", "logout"]:
            subprocess.Popen(["shutdown", "/l"], shell=True)
            return "Signing you out."

        else:
            return f"I don't know how to do '{cmd}'."

    except Exception as e:
        return f"System command failed: {e}"


# ============================================================
#  Public Entry Point (called by main.py)
# ============================================================

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    app_name = params.get("app_name", "").strip()
    url      = params.get("url", "").strip()
    action   = params.get("action", "open").strip().lower()

    # URL shortcut
    if url:
        webbrowser.open(url)
        return f"Opened {url} in your default browser."

    if not app_name:
        return "What app should I open?"

    # Route by action
    if action == "close":
        return _close_app_core(app_name)
    elif action in ["shutdown", "restart", "lock", "sleep",
                     "hibernate", "sign out", "log out"]:
        return _system_command(action)
    else:
        return _open_app_core(app_name)