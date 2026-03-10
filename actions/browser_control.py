# actions/browser_control.py
# LEO — Default Browser Controller
# Opens URLs in the system's default browser using webbrowser module.
# For page interaction, uses pyautogui (keyboard/mouse automation).

import time
import webbrowser
import urllib.parse

try:
    import pyautogui
    pyautogui.PAUSE = 0.3
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False


def _open_url(url: str) -> str:
    """Open URL in system default browser."""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        webbrowser.open(url)
        time.sleep(2)  # wait for browser to open
        return f"Opened: {url}"
    except Exception as e:
        return f"Failed to open: {e}"


def _search_web(query: str, engine: str = "google") -> str:
    """Search the web using the default browser."""
    engines = {
        "google":     f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}",
        "bing":       f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}",
        "duckduckgo": f"https://duckduckgo.com/?q={urllib.parse.quote_plus(query)}",
        "youtube":    f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}",
    }
    url = engines.get(engine.lower(), engines["google"])
    return _open_url(url)


def _youtube_play(query: str) -> str:
    """Open YouTube search results and auto-play the first video."""
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
    result = _open_url(url)

    if not _HAS_PYAUTOGUI:
        return result + " (Cannot auto-play: pyautogui not installed)"

    # Wait for page to load, then click first video
    time.sleep(4)

    # Tab to first video result and press Enter
    # YouTube's first result is typically reachable via Tab presses
    pyautogui.press("tab", presses=5, interval=0.15)
    time.sleep(0.3)
    pyautogui.press("enter")

    return f"Playing YouTube: {query}"


def _click_element(text: str = None, x: int = None, y: int = None) -> str:
    """Click on an element by text or coordinates."""
    if not _HAS_PYAUTOGUI:
        return "pyautogui not available"

    if x is not None and y is not None:
        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})"

    if text:
        # Try to find and click text on screen
        try:
            location = pyautogui.locateOnScreen(text)
            if location:
                pyautogui.click(location)
                return f"Clicked: {text}"
        except Exception:
            pass
        return f"Could not find '{text}' on screen"

    return "No click target specified"


def _type_text(text: str, press_enter: bool = True) -> str:
    """Type text into the currently focused element."""
    if not _HAS_PYAUTOGUI:
        return "pyautogui not available"

    pyautogui.write(text, interval=0.03)
    if press_enter:
        time.sleep(0.2)
        pyautogui.press("enter")
    return f"Typed: {text}"


def _press_key(key: str) -> str:
    """Press a keyboard key."""
    if not _HAS_PYAUTOGUI:
        return "pyautogui not available"
    pyautogui.press(key)
    return f"Pressed: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    """Scroll the page."""
    if not _HAS_PYAUTOGUI:
        return "pyautogui not available"
    clicks = amount if direction == "up" else -amount
    pyautogui.scroll(clicks)
    return f"Scrolled {direction} by {amount}"


def browser_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None
) -> str:
    """
    Browser controller using system default browser + pyautogui.

    parameters:
        action      : go_to | search | youtube_play | click | type | scroll | press
        url         : URL for go_to
        query       : search query for search/youtube_play
        engine      : google | bing | duckduckgo | youtube (default: google)
        text        : text for click or type
        x, y        : coordinates for click
        direction   : up | down for scroll
        amount      : scroll amount (default: 3)
        key         : key name for press (e.g. Enter, Escape, Tab)
        press_enter : bool, press Enter after typing (default: True)
    """
    action = (parameters or {}).get("action", "").lower().strip()
    result = "Unknown action."

    try:
        if action == "go_to":
            url = parameters.get("url", "")
            result = _open_url(url)

        elif action == "search":
            query  = parameters.get("query", "")
            engine = parameters.get("engine", "google")
            result = _search_web(query, engine)

        elif action == "youtube_play":
            query = parameters.get("query", "")
            result = _youtube_play(query)

        elif action == "click":
            result = _click_element(
                text=parameters.get("text"),
                x=parameters.get("x"),
                y=parameters.get("y"),
            )

        elif action == "type":
            result = _type_text(
                text=parameters.get("text", ""),
                press_enter=parameters.get("press_enter", True),
            )

        elif action == "scroll":
            result = _scroll(
                direction=parameters.get("direction", "down"),
                amount=parameters.get("amount", 3),
            )

        elif action == "press":
            result = _press_key(parameters.get("key", "Enter"))

        elif action == "close":
            if _HAS_PYAUTOGUI:
                pyautogui.hotkey("alt", "F4")
                result = "Closed active window."
            else:
                result = "Cannot close: pyautogui not available."

        else:
            result = f"Unknown browser action: {action}"

    except Exception as e:
        result = f"Browser error: {e}"

    print(f"[Browser] {result[:80]}")
    return result