"""Muse Voice Transcribe (muse-voice-transcribe-1.0) support.

Converts any audio/video input to 16 kHz mono WAV with ffmpeg, sends it to
POST https://api.meta.ai/v1/asr/transcribe, and (via Muse Spark 1.3) extracts
a caregiver watchlist of objects that must stay in place / within reach.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from . import meta_api

log = logging.getLogger("splatdiff.voice")

MODEL = "muse-voice-transcribe-1.0"
ASR_URL = "https://api.meta.ai/v1/asr/transcribe"
# $0.18 per audio hour.
COST_PER_AUDIO_HOUR_USD = 0.18
MAX_SECONDS = 600  # API max: 10 min
MAX_BYTES = 32 * 1024 * 1024  # API max: 32 MB

_NO_STREAM_PHRASES = (
    "does not contain any stream",
    "output file does not contain any stream",
    "matches no streams",
    "no stream",
)


def _log_cost(model: str, kind: str, est_usd: float, latency_s: float) -> None:
    """Reuse meta_api's cost-ledger helper (public alias if present, else private)."""
    fn = getattr(meta_api, "log_cost", None) or getattr(meta_api, "_log_cost", None)
    if fn is not None:
        try:
            fn(model, kind, est_usd, latency_s)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("cost ledger via meta_api failed: %s", exc)


def _api_key() -> str:
    fn = getattr(meta_api, "_api_key", None)
    if callable(fn):
        return fn()
    key = os.getenv("MODEL_API_KEY", "")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return key


def _ffmpeg_exe() -> str:
    from imageio_ffmpeg import get_ffmpeg_exe

    return get_ffmpeg_exe()


def _probe_has_audio_stream(src: Path) -> bool | None:
    """Return True/False if ffmpeg's banner clearly shows an audio stream, else None."""
    try:
        proc = subprocess.run(
            [_ffmpeg_exe(), "-hide_banner", "-i", str(src)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("audio probe failed for %s: %s", src, exc)
        return None
    banner = (proc.stderr or "") + (proc.stdout or "")
    if ": Audio:" in banner:
        return True
    # ffmpeg -i without an output exits non-zero but prints stream info; if it
    # printed any Stream lines and none was Audio, there is no audio stream.
    if "Stream #" in banner:
        return False
    return None


def _convert_to_wav(src: Path) -> Path | None:
    """Convert to 16 kHz mono s16 WAV. Returns None if there is no audio stream."""
    tmp_dir = Path("cache") / "voice_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="splatdiff_voice_", suffix=".wav", dir=str(tmp_dir))
    os.close(fd)
    out = Path(tmp_name)
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-v", "error",
        "-i", str(src),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-sample_fmt", "s16",
        "-t", str(MAX_SECONDS),
        str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as exc:  # noqa: BLE001
        out.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg audio conversion failed: {exc}") from exc
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        out.unlink(missing_ok=True)
        if any(phrase in stderr.lower() for phrase in _NO_STREAM_PHRASES):
            log.info("no audio stream in %s", src)
            return None
        raise RuntimeError(f"ffmpeg audio conversion failed: {stderr[:1000] or 'unknown error'}")
    if not out.is_file() or out.stat().st_size <= 44:
        out.unlink(missing_ok=True)
        log.info("no usable audio produced from %s", src)
        return None
    return out


def _wav_duration_ms(wav_path: Path) -> int:
    try:
        size = wav_path.stat().st_size
    except Exception:  # noqa: BLE001
        return 0
    # 16000 samples/s * 1 channel * 2 bytes/sample = 32000 bytes/s (plus header).
    payload = max(0, size - 44)
    return int(payload / 32000.0 * 1000)


def transcribe(path) -> dict:
    """Transcribe an audio/video file.

    Returns {'transcript': str, 'duration_ms': int, 'latency_s': float}.
    A file with no audio stream yields an empty transcript (no API call).
    """
    start = time.time()
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"audio/video file not found: {src}")

    if _probe_has_audio_stream(src) is False:
        return {"transcript": "", "duration_ms": 0, "latency_s": round(time.time() - start, 3)}

    wav_path = _convert_to_wav(src)
    if wav_path is None:
        return {"transcript": "", "duration_ms": 0, "latency_s": round(time.time() - start, 3)}

    try:
        wav_bytes = wav_path.read_bytes()
        if len(wav_bytes) > MAX_BYTES:  # -t 600 should prevent this; be defensive.
            wav_bytes = wav_bytes[:MAX_BYTES]
        fallback_duration_ms = _wav_duration_ms(wav_path)

        request_json = json.dumps(
            {"model": MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
        )
        headers = {"Authorization": f"Bearer {_api_key()}", "Accept": "application/json"}

        last_err: Exception | None = None
        api_start = time.time()
        for attempt in range(3):
            api_start = time.time()
            try:
                resp = requests.post(
                    ASR_URL,
                    headers=headers,
                    files={
                        "request": (None, request_json, "application/json"),
                        "audio": ("note.wav", wav_bytes, "audio/wav"),
                    },
                    timeout=300,
                )
                if resp.status_code == 400:
                    print(f"Voice Transcribe 400 error body: {resp.text[:4000]}")
                    resp.raise_for_status()
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(
                        f"retryable {resp.status_code}: {resp.text[:1000]}", response=resp
                    )
                resp.raise_for_status()
                data = resp.json()
                api_latency = time.time() - api_start

                transcript = data.get("transcript") or ""
                if not isinstance(transcript, str):
                    transcript = str(transcript)
                try:
                    duration_ms = int(data.get("audioDurationMs") or fallback_duration_ms)
                except Exception:  # noqa: BLE001
                    duration_ms = fallback_duration_ms

                est_usd = COST_PER_AUDIO_HOUR_USD * (duration_ms / 1000.0 / 3600.0)
                _log_cost(MODEL, "transcribe", est_usd, api_latency)
                return {
                    "transcript": transcript,
                    "duration_ms": duration_ms,
                    "latency_s": round(time.time() - start, 3),
                }
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 400:
                    raise
                last_err = exc
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_err = exc
            if attempt < 2:
                wait = 2 ** attempt * 2
                log.warning("transcribe failed (%s), retry in %ss", last_err, wait)
                time.sleep(wait)
        raise RuntimeError(f"Voice Transcribe failed after 3 attempts: {last_err}")
    finally:
        wav_path.unlink(missing_ok=True)


def extract_watchlist(transcript) -> list[str]:
    """Use Muse Spark 1.3 to pull up to 8 watchlist objects from a transcript."""
    if not transcript or not str(transcript).strip():
        return []
    text = str(transcript).strip()
    prompt = (
        "Extract the physical household objects the speaker says must stay in place, "
        "stay within reach, or be checked on. Examples of the kind of thing to extract: "
        "'walker', 'floor lamp', 'pill organizer'.\n"
        "Rules:\n"
        "- Return up to 8 items.\n"
        "- Each item is a short, singular noun phrase a segmentation model could find "
        "(e.g. 'walker', not 'her walker should stay by the chair').\n"
        "- Only include objects actually mentioned in the transcript; invent nothing.\n"
        "- If no such objects are mentioned, return an empty list.\n"
        'Respond with strict JSON only, no markdown fences: {"items": ["walker", "pill organizer"]}\n\n'
        f"Transcript:\n{text}"
    )
    body = {
        "model": "muse-spark-1.3",
        "input": [meta_api.user_message([meta_api.text_part(prompt)])],
        "reasoning": {"effort": "low"},
        "max_output_tokens": 1000,
    }
    resp = meta_api.responses(body)
    raw = meta_api.extract_text(resp)
    parsed = meta_api.parse_json_loose(raw)
    if isinstance(parsed, dict):
        items = parsed.get("items") or []
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []

    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip().strip(".,;:!?\"'").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= 8:
            break
    return out
