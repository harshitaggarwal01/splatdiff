"""Meta Model API client: retries, disk cache, cost ledger."""
from __future__ import annotations
import base64, hashlib, json, logging, os, threading, time
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("splatdiff.meta_api")
BASE_URL = "https://api.meta.ai/v1"
CACHE_DIR = Path("cache")
RESP_CACHE = CACHE_DIR / "responses"
COSTS_FILE = CACHE_DIR / "costs.jsonl"
_COST_LOCK = threading.Lock()  # SAM/Spark calls log from worker threads
FILES_CACHE = CACHE_DIR / "files.json"
_session = requests.Session()

def _api_key() -> str:
    key = os.getenv("MODEL_API_KEY", "")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return key

def _headers() -> dict:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}

def _no_cache() -> bool:
    return os.getenv("SPLATDIFF_NO_CACHE", "") == "1"

def _cache_key(body: dict) -> str:
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _usage_count(usage: dict, key: str, default: float) -> float:
    try:
        val = usage.get(key)
        return float(val) if val is not None else float(default)
    except Exception:
        return float(default)

def _estimate_cost(body: dict, resp: dict | None) -> tuple[float, str]:
    model = str(body.get("model", "unknown"))
    usage = (resp or {}).get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    if model == "muse-spark-1.3":
        try:
            it, ot = float(usage.get("input_tokens", 0)), float(usage.get("output_tokens", 0))
        except Exception:
            it, ot = 0.0, 0.0
        return (it * 1.25 + ot * 4.25) / 1_000_000.0, "responses"
    if model == "sam-3.1":
        s = json.dumps(body)
        if "input_video" in s:
            # Real billed frames from the API (already includes the
            # 50-frame billing minimum, e.g. 50 for a 40-frame clip).
            # Fall back to that minimum only if usage is absent.
            frames = _usage_count(usage, "video_frames_processed", 50)
            return frames * 0.20 / 1000.0, "video_segmentation"
        images = _usage_count(usage, "images_processed", 1)
        return images * 2.50 / 1000.0, "image_segmentation"
    if model.startswith("muse-image"):
        return 0.01, "image"
    return 0.0, "responses"

def _log_cost(model: str, kind: str, est_usd: float, latency_s: float) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        row = {"model": model, "kind": kind, "est_usd": round(float(est_usd), 6),
               "latency_s": round(float(latency_s), 3), "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with _COST_LOCK, COSTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:
        log.warning("cost ledger failed: %s", e)

def total_cost() -> float:
    """Sum the ledger, skipping any malformed line instead of zeroing the total."""
    total = 0.0
    try:
        lines = COSTS_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0.0
    for l in lines:
        try:
            total += float(json.loads(l).get("est_usd", 0))
        except Exception:
            continue
    return total

def responses(body: dict) -> dict:
    """POST /v1/responses with cache, retries on 429/5xx/timeout, never retry 400.

    Cached responses cost 0: a cache hit returns before any cost logging,
    so re-runs never re-log (or double-count) a call.
    """
    RESP_CACHE.mkdir(parents=True, exist_ok=True)
    key = _cache_key(body)
    cache_path = RESP_CACHE / f"{key}.json"
    if not _no_cache() and cache_path.exists():
        try:
            log.info("cache hit %s (no cost logged)", key[:12])
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("bad cache file, refetching: %s", e)
    url = f"{BASE_URL}/responses"
    last_err = None
    for attempt in range(3):
        start = time.time()
        try:
            r = _session.post(url, headers=_headers(), json=body, timeout=300)
            latency = time.time() - start
            if r.status_code == 400:
                print(f"Meta API 400 error body: {r.text[:4000]}")
                r.raise_for_status()
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"retryable {r.status_code}: {r.text[:1000]}", response=r)
            r.raise_for_status()
            data = r.json()
            est, kind = _estimate_cost(body, data)
            _log_cost(str(body.get("model", "unknown")), kind, est, latency)
            if not _no_cache():
                cache_path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                raise
            last_err = e
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
        if attempt < 2:
            wait = 2 ** attempt * 2
            log.warning("request failed (%s), retry in %ss", last_err, wait)
            time.sleep(wait)
    raise RuntimeError(f"Meta API request failed after 3 attempts: {last_err}")

def extract_text(resp: dict) -> str:
    parts = []
    for item in (resp or {}).get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text" and c.get("text"):
                    parts.append(c["text"])
    return "".join(parts)

def parse_json_loose(text: str):
    """Parse JSON robustly: strip fences, find first {..last } or [..]."""
    if not text:
        raise ValueError("empty text, cannot parse JSON")
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    for a, b in (("{", "}"), ("[", "]")):
        i, j = t.find(a), t.rfind(b)
        if i != -1 and j > i:
            return json.loads(t[i:j + 1])
    raise ValueError(f"no JSON found in: {text[:500]}")

def image_part(path_or_ndarray) -> dict:
    """Build input_image part from a file path or an OpenCV (BGR) ndarray."""
    if isinstance(path_or_ndarray, (str, Path)):
        data = Path(path_or_ndarray).read_bytes()
    else:
        import cv2
        ok, buf = cv2.imencode(".jpg", path_or_ndarray)
        if not ok:
            raise ValueError("failed to encode ndarray as JPEG")
        data = buf.tobytes()
    b64 = base64.b64encode(data).decode("ascii")
    return {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"}

def text_part(text: str) -> dict:
    return {"type": "input_text", "text": text}

def user_message(content: list) -> dict:
    return {"type": "message", "role": "user", "content": content}

def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def upload_file(path) -> str:
    """Upload via Files API, cached by sha256 in cache/files.json."""
    p = Path(path)
    sha = _file_sha256(p)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {}
    if FILES_CACHE.exists():
        try:
            mapping = json.loads(FILES_CACHE.read_text(encoding="utf-8"))
        except Exception:
            mapping = {}
    if sha in mapping and not _no_cache():
        return mapping[sha]
    url = f"{BASE_URL}/files"
    last_err = None
    for attempt in range(3):
        start = time.time()
        try:
            with p.open("rb") as fh:
                files = {"file": (p.name, fh, "video/mp4")}
                r = _session.post(url, headers={"Authorization": f"Bearer {_api_key()}"},
                                  data={"purpose": "user_data"}, files=files, timeout=300)
            if r.status_code == 400:
                print(f"Files API 400 error body: {r.text[:4000]}")
                r.raise_for_status()
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"retryable {r.status_code}", response=r)
            r.raise_for_status()
            fid = r.json()["id"]
            _log_cost("files-api", "upload", 0.0, time.time() - start)
            mapping[sha] = fid
            FILES_CACHE.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
            return fid
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                raise
            last_err = e
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
        if attempt < 2:
            time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"file upload failed: {last_err}")

def image_generate(prompt: str) -> bytes:
    """Muse Image generation; returns WEBP bytes."""
    start = time.time()
    r = _session.post(f"{BASE_URL}/images/generations", headers=_headers(),
                      json={"model": "muse-image-1.0", "prompt": prompt, "size": "1024x1024", "n": 1}, timeout=300)
    if r.status_code == 400:
        print(f"Muse Image 400: {r.text[:4000]}")
    r.raise_for_status()
    _log_cost("muse-image-1.0", "image_generation", 0.01, time.time() - start)
    return base64.b64decode(r.json()["data"][0]["b64_json"])

def image_edit(prompt: str, image_png_bytes: bytes) -> bytes:
    """Muse Image edit; returns WEBP bytes."""
    start = time.time()
    files = {"image": ("image.png", image_png_bytes, "image/png")}
    r = _session.post(f"{BASE_URL}/images/edits", headers={"Authorization": f"Bearer {_api_key()}"},
                      data={"model": "muse-image-1.0", "prompt": prompt}, files=files, timeout=300)
    if r.status_code == 400:
        print(f"Muse Image edit 400: {r.text[:4000]}")
    r.raise_for_status()
    _log_cost("muse-image-1.0", "image_edit", 0.01, time.time() - start)
    return base64.b64decode(r.json()["data"][0]["b64_json"])
