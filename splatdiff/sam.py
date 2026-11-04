"""SAM 3.1 concept-prompt segmentation; parse token grammar, ignore masks."""
from __future__ import annotations
import logging, re
from .meta_api import responses, extract_text, upload_file, image_part, text_part, user_message

log = logging.getLogger("splatdiff.sam")
MODEL = "sam-3.1"
_FRAME_RE = re.compile(r"<(\d+)f>")
_BOX_RE = re.compile(r"(\d+)\s*<\|box;([^|]*)\|>")

def _parse_pairs(s: str) -> dict:
    out = {}
    for part in s.split(";"):
        if "=" in part:
            k, v = part.split("=", 1); out[k.strip()] = v.strip()
    return out

def parse_sam_text(text: str) -> dict:
    """Parse SAM token text into {frame_idx: [{obj, box, c, w, h}]}."""
    result: dict[int, list] = {}
    if not text:
        return result
    chunks = _FRAME_RE.split(text)
    # chunks: [prefix, frame1, seg1, frame2, seg2, ...]
    for i in range(1, len(chunks) - 1, 2):
        try:
            frame_idx = int(chunks[i])
        except Exception:
            continue
        seg = chunks[i + 1] or ""
        dets = []
        for m in _BOX_RE.finditer(seg):
            kv = _parse_pairs(m.group(2))
            try:
                box = [int(float(kv["x1"])), int(float(kv["y1"])), int(float(kv["x2"])), int(float(kv["y2"]))]
                c = float(kv.get("c", 0.0)); w = int(float(kv.get("w", 0))); h = int(float(kv.get("h", 0)))
            except Exception:
                continue
            dets.append({"obj": int(m.group(1)), "box": box, "c": c, "w": w, "h": h})
        if dets:
            result.setdefault(frame_idx, []).extend(dets[:16])
    return result

def track_concept(video_path, concept: str) -> dict:
    """Upload video (cached) and run SAM concept-prompt video segmentation."""
    file_id = upload_file(video_path)
    body = {"model": MODEL,
            "input": [user_message([text_part(concept), {"type": "input_video", "file_id": file_id}])],
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"}, "store": False}
    resp = responses(body)
    return parse_sam_text(extract_text(resp))

def segment_image(img, concept: str) -> dict:
    """SAM segmentation on a single image (path or ndarray)."""
    body = {"model": MODEL,
            "input": [user_message([text_part(concept), image_part(img)])],
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"}, "store": False}
    resp = responses(body)
    parsed = parse_sam_text(extract_text(resp))
    return parsed if parsed else ({0: parsed[0]} if 0 in parsed else {})
