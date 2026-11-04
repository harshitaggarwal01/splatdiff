"""Video normalisation, keyframes, drawing, synthetic pan videos."""
from __future__ import annotations
import hashlib, logging, subprocess
from pathlib import Path
import cv2
import numpy as np
import imageio_ffmpeg

log = logging.getLogger("splatdiff.video_io")

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def normalize_video(in_path) -> str:
    """Transcode to H.264 MP4 fps=5 scale=640:-2 max 30s, cached by sha256."""
    src = Path(in_path)
    if not src.exists():
        raise FileNotFoundError(src)
    cache = Path("cache") / "normalized"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{_sha256(src)}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return str(out)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-i", str(src), "-vf", "fps=5,scale=640:-2", "-t", "30",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)]
    log.info("normalize: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-3000:]}")
    return str(out)

def extract_keyframes(video_path, k: int = 6, out_dir=None) -> list[str]:
    """Extract K evenly spaced JPEG frames."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release(); raise RuntimeError(f"no frames in {video_path}")
    if out_dir is None:
        out_dir = Path("cache") / "keyframes" / Path(str(video_path)).stem
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    idxs = np.linspace(0, total - 1, min(k, total)).astype(int).tolist()
    paths = []
    for n, idx in enumerate(idxs):
        frame = read_frame(video_path, int(idx), _cap=cap)
        if frame is None:
            continue
        p = out_dir / f"frame_{n:02d}_{int(idx)}.jpg"
        cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        paths.append(str(p))
    cap.release()
    return paths

def read_frame(video_path, idx: int, _cap=None):
    cap = _cap or cv2.VideoCapture(str(video_path))
    own = _cap is None
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        if own:
            cap.release()

def draw_box(img, box, label: str = "", color=(0, 255, 0)):
    """Draw box+label on a path-or-ndarray image; returns annotated ndarray (BGR)."""
    if isinstance(img, (str, Path)):
        frame = cv2.imread(str(img))
        if frame is None:
            raise FileNotFoundError(img)
    else:
        frame = np.array(img).copy()
    if box is not None and len(box) == 4:
        x1, y1, x2, y2 = [int(v) for v in box]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1); x2, y2 = min(w - 1, x2), min(h - 1, y2)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        if label:
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            ty = max(th + 6, y1)
            cv2.rectangle(frame, (x1, ty - th - 6), (x1 + tw + 6, ty), color, -1)
            cv2.putText(frame, label, (x1 + 3, ty - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
    elif label:
        cv2.putText(frame, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return frame

def pan_video_from_image(img_path, out_mp4, seconds: int = 8, fps: int = 10) -> str:
    """Ken-Burns pan across a still with slight handheld jitter, then ffmpeg H.264."""
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(img_path)
    out_mp4 = Path(out_mp4); out_mp4.parent.mkdir(parents=True, exist_ok=True)
    H, W = img.shape[:2]
    crop_w, crop_h = int(W * 0.62), int(H * 0.62)
    n = max(1, int(seconds * fps))
    tmp = out_mp4.with_suffix(".tmp.mp4")
    writer = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 360))
    if not writer.isOpened():
        raise RuntimeError("VideoWriter failed")
    for i in range(n):
        t = i / max(1, n - 1)
        cx = int(crop_w / 2 + t * (W - crop_w))
        cy = int(H / 2 + 8 * np.sin(t * 6.28))
        cx += int(3 * np.sin(i * 0.7)); cy += int(2 * np.cos(i * 0.9))
        x1 = int(np.clip(cx - crop_w / 2, 0, W - crop_w)); y1 = int(np.clip(cy - crop_h / 2, 0, H - crop_h))
        frame = cv2.resize(img[y1:y1 + crop_h, x1:x1 + crop_w], (640, 360))
        writer.write(frame)
    writer.release()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-i", str(tmp), "-vf", "fps=5,scale=640:-2", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-an", str(out_mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg pan encode failed: {r.stderr[-3000:]}")
    return str(out_mp4)
