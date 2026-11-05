"""Privacy redaction helpers (SAM 3.1 based).

People and paper documents are detected with SAM 3.1 image segmentation
and Gaussian-blurred. SAM itself is the detector, so it necessarily sees
the raw frame; everything downstream (storage, UI, Muse Spark) only
ever sees the blurred result.
"""
from __future__ import annotations
import logging
from pathlib import Path
import cv2
import numpy as np
from . import sam as _sam_module
from .sam import segment_image as _orig_segment_image

# Re-exported so callers/tests can patch ``splatdiff.privacy.segment_image``.
segment_image = _orig_segment_image

log = logging.getLogger("splatdiff.privacy")

SENSITIVE_CONCEPTS = ("person", "paper document")
REDACT_MIN_CONF = 0.4
PAD_FRAC = 0.10


def _segment_image(img, concept):
    """Call SAM image segmentation, honouring patches on either module."""
    patched = globals().get("segment_image")
    if patched is not None and patched is not _orig_segment_image:
        return patched(img, concept)
    # Prefer the live attribute on the sam module (patch-friendly).
    fn = getattr(_sam_module, "segment_image", None) or _orig_segment_image
    return fn(img, concept)


def _extract_dets(parsed) -> list[dict]:
    """Normalise segment_image output into a flat detection list."""
    dets: list[dict] = []
    if parsed is None:
        return dets
    if isinstance(parsed, dict):
        # Could be a single detection {"box": ..., "c": ...} or
        # {frame_idx: [dets]}.
        if "box" in parsed or "c" in parsed:
            iterable = [parsed]
        else:
            iterable = []
            for v in parsed.values():
                if isinstance(v, dict):
                    iterable.append(v)
                elif isinstance(v, (list, tuple)):
                    iterable.extend([d for d in v if isinstance(d, dict)])
    elif isinstance(parsed, (list, tuple)):
        iterable = [d for d in parsed if isinstance(d, dict)]
    else:
        iterable = []
    for d in iterable:
        try:
            box = d.get("box")
            if box is None or len(box) != 4:
                continue
            box = [int(float(v)) for v in box]
            c = float(d.get("c", 0.0) or 0.0)
        except Exception:
            continue
        det = {"box": box, "c": c}
        # Preserve frame size when SAM gave it (handy for floor checks).
        for k in ("w", "h", "obj"):
            if d.get(k) is not None:
                det[k] = d[k]
        dets.append(det)
    return dets


def _box_of(item):
    """Accept a detection dict or a raw [x1,y1,x2,y2] box."""
    if item is None:
        return None, 0.0
    if isinstance(item, dict):
        box = item.get("box", item.get("bbox"))
        try:
            c = float(item.get("c", item.get("confidence", 1.0)) or 0.0)
        except Exception:
            c = 1.0
        if box is None and all(k in item for k in ("x1", "y1", "x2", "y2")):
            box = [item["x1"], item["y1"], item["x2"], item["y2"]]
    else:
        box, c = item, 1.0
    if box is None:
        return None, c
    try:
        if len(box) != 4:
            return None, c
        return [int(float(v)) for v in box], c
    except Exception:
        return None, c


def redact_image(path_or_ndarray, boxes):
    """Gaussian-blur every box (padded 10%) in an image.

    ``path_or_ndarray`` may be a filesystem path (str/Path) — the file is
    blurred IN PLACE and the path (as str) is returned — or an ndarray,
    in which case a blurred copy is returned and the input is untouched.
    ``boxes`` items may be detection dicts ({"box": [...], "c": ...}) or
    raw [x1, y1, x2, y2] boxes. Boxes with c < 0.4 are ignored when a
    confidence is present. Never raises on bad boxes; unreadable paths
    are returned unchanged.
    """
    is_path = isinstance(path_or_ndarray, (str, Path))
    if is_path:
        img = cv2.imread(str(path_or_ndarray))
        if img is None:
            log.warning("redact_image: could not read %s", path_or_ndarray)
            return str(path_or_ndarray)
    else:
        try:
            img = np.array(path_or_ndarray, copy=True)
        except Exception:
            log.warning("redact_image: unsupported image input %r", type(path_or_ndarray))
            return path_or_ndarray
        if img is None or getattr(img, "size", 0) == 0:
            return img
    h, w = img.shape[:2]
    for item in boxes or []:
        box, c = _box_of(item)
        if box is None:
            continue
        # Raw boxes default to c=1.0; explicit low confidences are skipped.
        if isinstance(item, dict) and ("c" in item or "confidence" in item) and c < REDACT_MIN_CONF:
            continue
        x1, y1, x2, y2 = box
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        pad_x, pad_y = int(round(PAD_FRAC * bw)), int(round(PAD_FRAC * bh))
        rx1, ry1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        rx2, ry2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
        if rx2 <= rx1 or ry2 <= ry1:
            continue
        roi = img[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            continue
        kw = max(15, (roi.shape[1] // 2) * 2 + 1)
        kh = max(15, (roi.shape[0] // 2) * 2 + 1)
        k = min(kw, kh, 99)
        if k % 2 == 0:
            k += 1
        try:
            img[ry1:ry2, rx1:rx2] = cv2.GaussianBlur(roi, (k, k), 0)
        except Exception:
            log.exception("redact_image: blur failed for box %s", box)
    if is_path:
        try:
            cv2.imwrite(str(path_or_ndarray), img)
        except Exception:
            log.exception("redact_image: could not write %s", path_or_ndarray)
        return str(path_or_ndarray)
    return img


def detect_sensitive(path) -> dict:
    """Detect people and paper documents in one image via SAM 3.1.

    ``path`` may be a path or an ndarray (``sam.segment_image`` accepts
    both). Runs one SAM image call per sensitive concept, keeps only
    detections with c >= 0.4, and never raises: a failed concept yields
    an empty list for that concept.

    Returns {"person": [dets], "paper document": [dets],
             "paper_document": [dets], "boxes": [all dets],
             "people": int, "documents": int,
             "people_blurred": int, "documents_blurred": int}
    where each det is {"box": [x1,y1,x2,y2], "c": float, "concept": str}.
    """
    result: dict = {"person": [], "paper document": [], "paper_document": [],
                    "boxes": [], "people": 0, "documents": 0,
                    "people_blurred": 0, "documents_blurred": 0}
    for concept in SENSITIVE_CONCEPTS:
        try:
            parsed = _segment_image(path, concept)
            dets = _extract_dets(parsed)
        except Exception as e:
            log.warning("detect_sensitive: SAM failed for '%s' on %r: %s", concept, path, e)
            dets = []
        kept = []
        for d in dets:
            if float(d.get("c", 0.0)) < REDACT_MIN_CONF:
                continue
            kept.append({"box": list(d["box"]), "c": float(d["c"]), "concept": concept,
                         **({"w": d["w"]} if "w" in d else {}),
                         **({"h": d["h"]} if "h" in d else {})})
        result[concept] = kept
        if concept == "paper document":
            result["paper_document"] = kept
        result["boxes"].extend(kept)
    result["people"] = len(result["person"])
    result["documents"] = len(result["paper document"])
    result["people_blurred"] = result["people"]
    result["documents_blurred"] = result["documents"]
    return result
