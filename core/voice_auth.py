# core/voice_auth.py
# Voice enrollment & verification — speaker-locked LEO

import numpy as np
import json
import struct
import threading
from pathlib import Path

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    _HAS_RESEMBLYZER = True
except ImportError:
    _HAS_RESEMBLYZER = False

_BASE_DIR     = Path(__file__).resolve().parent.parent
_PROFILE_PATH = _BASE_DIR / "config" / "voice_profile.npy"
_CONFIG_PATH  = _BASE_DIR / "config" / "voice_config.json"

_encoder      = None
_owner_embed  = None
_lock         = threading.Lock()

# Threshold: cosine similarity above this = owner's voice
_SIMILARITY_THRESHOLD = 0.75


def _get_encoder():
    global _encoder
    if _encoder is None and _HAS_RESEMBLYZER:
        _encoder = VoiceEncoder()
    return _encoder


def is_available() -> bool:
    """Check if voice auth is available (resemblyzer installed)."""
    return _HAS_RESEMBLYZER


def is_enrolled() -> bool:
    """Check if the owner's voice is enrolled."""
    return _PROFILE_PATH.exists()


def load_profile() -> bool:
    """Load saved voice profile. Returns True if loaded."""
    global _owner_embed
    if _PROFILE_PATH.exists():
        try:
            _owner_embed = np.load(str(_PROFILE_PATH))
            print("[VoiceAuth] ✅ Voice profile loaded.")
            return True
        except Exception as e:
            print(f"[VoiceAuth] ⚠️ Failed to load profile: {e}")
    return False


def enroll_from_audio(audio_chunks: list[bytes], sample_rate: int = 16000) -> bool:
    """
    Enroll owner's voice from collected audio chunks (16-bit PCM).
    Needs 3-8 seconds of speech for a good embedding.
    """
    global _owner_embed

    encoder = _get_encoder()
    if encoder is None:
        print("[VoiceAuth] ❌ resemblyzer not available.")
        return False

    try:
        # Convert PCM bytes to float32 numpy array
        all_samples = []
        for chunk in audio_chunks:
            samples = struct.unpack(f'<{len(chunk)//2}h', chunk)
            all_samples.extend(samples)

        audio = np.array(all_samples, dtype=np.float32) / 32768.0

        if len(audio) < sample_rate * 2:  # need at least 2 seconds
            print("[VoiceAuth] ⚠️ Not enough audio for enrollment (need 2s+).")
            return False

        # Compute embedding
        embed = encoder.embed_utterance(audio)
        _owner_embed = embed

        # Save
        _PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(_PROFILE_PATH), embed)

        # Save config
        config = {"enrolled": True, "threshold": _SIMILARITY_THRESHOLD}
        with open(_CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

        print("[VoiceAuth] ✅ Voice enrolled successfully!")
        return True

    except Exception as e:
        print(f"[VoiceAuth] ❌ Enrollment failed: {e}")
        return False


def verify_speaker(audio_chunk: bytes, sample_rate: int = 16000) -> float:
    """
    Verify if audio chunk matches the enrolled voice.
    Returns similarity score (0.0 to 1.0).
    Returns 1.0 if no profile enrolled (allow all).
    """
    global _owner_embed

    if _owner_embed is None:
        return 1.0  # No profile = allow all

    encoder = _get_encoder()
    if encoder is None:
        return 1.0

    try:
        samples = struct.unpack(f'<{len(audio_chunk)//2}h', audio_chunk)
        audio = np.array(samples, dtype=np.float32) / 32768.0

        if len(audio) < 1600:  # need at least 0.1s of audio
            return 0.5  # too short to verify, neutral score

        with _lock:
            embed = encoder.embed_utterance(audio)
            similarity = float(np.dot(_owner_embed, embed) /
                              (np.linalg.norm(_owner_embed) * np.linalg.norm(embed)))

        return max(0.0, similarity)

    except Exception:
        return 0.5  # on error, return neutral


def is_owner(audio_chunk: bytes, sample_rate: int = 16000) -> bool:
    """Quick check: is this the owner speaking?"""
    if _owner_embed is None:
        return True  # no enrollment = everyone is owner
    score = verify_speaker(audio_chunk, sample_rate)
    return score >= _SIMILARITY_THRESHOLD


def get_threshold() -> float:
    """Get current similarity threshold."""
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH) as f:
                return json.load(f).get("threshold", _SIMILARITY_THRESHOLD)
        except Exception:
            pass
    return _SIMILARITY_THRESHOLD


def set_threshold(val: float):
    """Adjust verification strictness (0.5-0.95)."""
    global _SIMILARITY_THRESHOLD
    _SIMILARITY_THRESHOLD = max(0.5, min(0.95, val))
    config = {"enrolled": is_enrolled(), "threshold": _SIMILARITY_THRESHOLD}
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
