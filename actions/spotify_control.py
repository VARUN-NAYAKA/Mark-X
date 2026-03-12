# actions/spotify_control.py
# LEO — Spotify Playback Controller
# Uses spotipy (Spotify Web API) for full playback control.
# Requires Spotify Premium + Developer App credentials in config/api_keys.json.

import json
import os
import subprocess
import time

# ── Spotipy setup ──────────────────────────────────────────────
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    _HAS_SPOTIPY = True
except ImportError:
    _HAS_SPOTIPY = False

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "api_keys.json")
_CACHE_PATH  = os.path.join(os.path.dirname(__file__), "..", "config", ".spotify_cache")

# Required scopes for playback control
_SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative"
)


def _get_spotify() -> "spotipy.Spotify | None":
    """Create an authenticated Spotify client."""
    if not _HAS_SPOTIPY:
        return None
    try:
        with open(_CONFIG_PATH, "r") as f:
            keys = json.load(f)
        client_id     = keys.get("spotify_client_id", "")
        client_secret = keys.get("spotify_client_secret", "")
        if not client_id or not client_secret:
            print("[Spotify] ⚠️ Missing spotify_client_id or spotify_client_secret in api_keys.json")
            return None

        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8888/callback",
            scope=_SCOPES,
            cache_path=_CACHE_PATH,
            open_browser=True,
        )
        return spotipy.Spotify(auth_manager=auth)
    except Exception as e:
        print(f"[Spotify] ⚠️ Auth failed: {e}")
        return None


def _ensure_device(sp) -> str | None:
    """
    Make sure there's an active Spotify device.
    If none found, try to open Spotify Desktop and wait for it.
    Returns the device_id or None.
    """
    # Check for existing devices
    devices = sp.devices().get("devices", [])
    for d in devices:
        if d.get("is_active"):
            return d["id"]

    # No active device — pick the first available
    if devices:
        device_id = devices[0]["id"]
        sp.transfer_playback(device_id, force_play=False)
        time.sleep(1)
        return device_id

    # No devices at all — try opening Spotify Desktop
    print("[Spotify] 🔄 No device found. Opening Spotify Desktop...")
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "spotify:"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )
    except Exception:
        pass

    # Wait for Spotify to register as a device (up to 8 seconds)
    for _ in range(8):
        time.sleep(1)
        devices = sp.devices().get("devices", [])
        if devices:
            device_id = devices[0]["id"]
            sp.transfer_playback(device_id, force_play=False)
            time.sleep(0.5)
            print(f"[Spotify] ✅ Device found: {devices[0].get('name', 'Unknown')}")
            return device_id

    print("[Spotify] ⚠️ No Spotify device found after waiting.")
    return None


# ── Playback actions ───────────────────────────────────────────

def _play(sp, query: str) -> str:
    """Search for a track/artist/album and start playback."""
    device_id = _ensure_device(sp)
    if not device_id:
        return "No Spotify device found. Please open Spotify Desktop and try again."

    if not query:
        try:
            sp.start_playback(device_id=device_id)
            return "Resumed playback."
        except Exception as e:
            return f"Could not resume: {e}"

    # Search for tracks
    results = sp.search(q=query, type="track", limit=5)
    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        # Try searching for artist
        results = sp.search(q=query, type="artist", limit=1)
        artists = results.get("artists", {}).get("items", [])
        if artists:
            artist_uri = artists[0]["uri"]
            sp.start_playback(device_id=device_id, context_uri=artist_uri)
            return f"Playing {artists[0]['name']} on Spotify."
        return f"No results found for '{query}'."

    # Play the first matching track
    track = tracks[0]
    track_name   = track["name"]
    artist_name  = track["artists"][0]["name"] if track["artists"] else "Unknown"
    sp.start_playback(device_id=device_id, uris=[track["uri"]])
    return f"Playing '{track_name}' by {artist_name} on Spotify."


def _pause(sp) -> str:
    try:
        sp.pause_playback()
        return "Paused Spotify."
    except Exception as e:
        return f"Could not pause: {e}"


def _resume(sp) -> str:
    device_id = _ensure_device(sp)
    try:
        sp.start_playback(device_id=device_id)
        return "Resumed Spotify."
    except Exception as e:
        return f"Could not resume: {e}"


def _next_track(sp) -> str:
    try:
        sp.next_track()
        return "Skipped to next track."
    except Exception as e:
        return f"Could not skip: {e}"


def _previous_track(sp) -> str:
    try:
        sp.previous_track()
        return "Went to previous track."
    except Exception as e:
        return f"Could not go back: {e}"


def _queue(sp, query: str) -> str:
    if not query:
        return "No song specified to queue."
    results = sp.search(q=query, type="track", limit=1)
    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        return f"No results found for '{query}'."
    track = tracks[0]
    sp.add_to_queue(track["uri"])
    return f"Added '{track['name']}' by {track['artists'][0]['name']} to queue."


def _current(sp) -> str:
    try:
        playing = sp.current_playback()
        if not playing or not playing.get("item"):
            return "Nothing is playing on Spotify right now."
        item = playing["item"]
        name   = item.get("name", "Unknown")
        artist = item["artists"][0]["name"] if item.get("artists") else "Unknown"
        album  = item.get("album", {}).get("name", "")
        is_playing = playing.get("is_playing", False)
        status = "Playing" if is_playing else "Paused"
        progress_ms = playing.get("progress_ms", 0) // 1000
        duration_ms = item.get("duration_ms", 0) // 1000
        mins_p, secs_p = divmod(progress_ms, 60)
        mins_d, secs_d = divmod(duration_ms, 60)
        return (
            f"{status}: '{name}' by {artist}"
            f" — Album: {album}"
            f" — {mins_p}:{secs_p:02d} / {mins_d}:{secs_d:02d}"
        )
    except Exception as e:
        return f"Could not get playback info: {e}"


def _set_volume(sp, volume: int) -> str:
    volume = max(0, min(100, volume))
    try:
        sp.volume(volume)
        return f"Spotify volume set to {volume}%."
    except Exception as e:
        return f"Could not set volume: {e}"


def _shuffle(sp) -> str:
    try:
        playing = sp.current_playback()
        current_state = playing.get("shuffle_state", False) if playing else False
        sp.shuffle(not current_state)
        new_state = "on" if not current_state else "off"
        return f"Shuffle {new_state}."
    except Exception as e:
        return f"Could not toggle shuffle: {e}"


def _repeat(sp) -> str:
    try:
        playing = sp.current_playback()
        current = playing.get("repeat_state", "off") if playing else "off"
        # cycle: off → context (album/playlist) → track → off
        next_state = {"off": "context", "context": "track", "track": "off"}.get(current, "off")
        sp.repeat(next_state)
        return f"Repeat mode: {next_state}."
    except Exception as e:
        return f"Could not toggle repeat: {e}"


# ── Public entry point ─────────────────────────────────────────

def spotify_control(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Spotify controller entry point (called by main.py).

    parameters:
        action  : play | pause | resume | next | skip | previous | queue |
                  current | volume | shuffle | repeat
        query   : Song/artist name for play/queue
        volume  : Volume level (0-100)
    """
    if not _HAS_SPOTIPY:
        return "Spotipy is not installed. Run: pip install spotipy"

    params = parameters or {}
    action = params.get("action", "play").strip().lower()
    query  = params.get("query", "").strip()

    sp = _get_spotify()
    if sp is None:
        return ("Spotify credentials not configured. "
                "Add spotify_client_id and spotify_client_secret to config/api_keys.json")

    print(f"[Spotify] 🎵 Action: {action}  Query: {query}")

    try:
        if action == "play":
            return _play(sp, query)
        elif action == "pause":
            return _pause(sp)
        elif action in ("resume", "unpause"):
            return _resume(sp)
        elif action in ("next", "skip"):
            return _next_track(sp)
        elif action in ("previous", "prev", "back"):
            return _previous_track(sp)
        elif action == "queue":
            return _queue(sp, query)
        elif action in ("current", "now_playing", "what_is_playing"):
            return _current(sp)
        elif action == "volume":
            vol = params.get("volume", 50)
            try:
                vol = int(vol)
            except (ValueError, TypeError):
                vol = 50
            return _set_volume(sp, vol)
        elif action == "shuffle":
            return _shuffle(sp)
        elif action == "repeat":
            return _repeat(sp)
        else:
            return f"Unknown Spotify action: {action}"
    except Exception as e:
        return f"Spotify error: {e}"
