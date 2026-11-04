"""Muse Spark 1.3: inventory, moved judgement, final claims."""
from __future__ import annotations
import logging
from pathlib import Path
import cv2
from .meta_api import responses, extract_text, parse_json_loose, image_part, text_part, user_message
from .video_io import draw_box

log = logging.getLogger("splatdiff.spark")
MODEL = "muse-spark-1.3"

def _call(content: list, max_tokens: int = 4000) -> str:
    body = {"model": MODEL, "input": [user_message(content)], "reasoning": {"effort": "low"}, "max_output_tokens": max_tokens}
    return extract_text(responses(body))

def list_objects(before_frames: list, after_frames: list, concepts=None) -> list[dict]:
    """Inventory objects from keyframes of both videos, or honour override."""
    if concepts:
        if isinstance(concepts, str):
            concepts = [c.strip() for c in concepts.split(",") if c.strip()]
        return [{"concept": c, "where_before": "", "where_after": "", "suspected_change": "unchanged"} for c in concepts]
    content = [text_part(
        "You are inventorying a room from phone-video keyframes. Images are labelled BEFORE frame i and AFTER frame i; "
        "camera viewpoint may differ. List at most 12 movable household objects visible in either set. Prioritise movable "
        "household objects (lamp, chair, backpack, suitcase, walker, plant, box, book, cushion, etc.), short singular noun "
        "phrases SAM can segment. Return STRICT JSON only, no markdown: "
        '{"objects": [{"concept": "floor lamp", "where_before": "str", "where_after": "str", '
        '"suspected_change": "added|removed|moved|unchanged"}]}')]
    for i, p in enumerate(before_frames):
        content.append(text_part(f"BEFORE frame {i}")); content.append(image_part(p))
    for i, p in enumerate(after_frames):
        content.append(text_part(f"AFTER frame {i}")); content.append(image_part(p))
    text = _call(content)
    try:
        data = parse_json_loose(text)
        objs = data.get("objects", []) if isinstance(data, dict) else data
    except Exception as e:
        log.warning("inventory parse failed: %s; text=%s", e, text[:500]); objs = []
    clean = []
    for o in objs[:12]:
        if isinstance(o, dict) and o.get("concept"):
            clean.append({"concept": str(o["concept"]).strip().lower(),
                          "where_before": str(o.get("where_before", "")), "where_after": str(o.get("where_after", "")),
                          "suspected_change": str(o.get("suspected_change", "unchanged"))})
    return clean

def _crop(frame_path, box, out_path):
    img = cv2.imread(str(frame_path))
    if img is None or not box:
        return None
    h, w = img.shape[:2]; x1, y1, x2, y2 = [int(v) for v in box]
    pad_x, pad_y = int(0.6 * max(1, x2 - x1)), int(0.6 * max(1, y2 - y1))
    crop = img[max(0, y1 - pad_y):min(h, y2 + pad_y), max(0, x1 - pad_x):min(w, x2 + pad_x)]
    if crop.size == 0:
        return None
    cv2.imwrite(str(out_path), crop); return str(out_path)

def judge_moved(concept: str, before_img, after_img, before_box=None, after_box=None) -> dict:
    """Ask Spark whether an object present in both videos moved, relative to surroundings."""
    tmp = Path("cache") / "judge"; tmp.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in concept.lower())
    bp, ap = tmp / f"{safe}_before.jpg", tmp / f"{safe}_after.jpg"
    cv2.imwrite(str(bp), draw_box(before_img, before_box, concept, (0, 165, 255)))
    cv2.imwrite(str(ap), draw_box(after_img, after_box, concept, (0, 165, 255)))
    content = [text_part(
        f"The orange box marks '{concept}' in the BEFORE frame and the AFTER frame of the same room. "
        "Camera viewpoint differs between videos, so do NOT judge by raw pixel position. Judge position relative to "
        "surrounding furniture and room landmarks. Also shown are context crops. Return STRICT JSON only: "
        '{"moved": true, "confidence": 0.0, "reason": "short reason"} with confidence in 0..1.'),
        text_part("BEFORE full frame"), image_part(str(bp)), text_part("AFTER full frame"), image_part(str(ap))]
    for label, src, box, name in (("BEFORE crop", str(bp), before_box, "b_crop"), ("AFTER crop", str(ap), after_box, "a_crop")):
        # crop from original annotated image area is approximate but gives context
        crop_path = _crop(src, box, tmp / f"{safe}_{name}.jpg")
        if crop_path:
            content.append(text_part(label)); content.append(image_part(crop_path))
    text = _call(content, max_tokens=1000)
    try:
        d = parse_json_loose(text)
        return {"moved": bool(d.get("moved")), "confidence": float(d.get("confidence", 0.0)), "reason": str(d.get("reason", ""))}
    except Exception as e:
        log.warning("judge_moved parse failed for %s: %s", concept, e)
        return {"moved": False, "confidence": 0.0, "reason": "unparseable Spark response"}

def write_claims(diff_table, moved_verdicts=None) -> dict:
    """Final Spark call: write claims from the SAM diff table."""
    import json as _json
    payload = {"diff_table": diff_table, "moved_verdicts": moved_verdicts or {}}
    content = [text_part(
        "You are writing a grounded room-change report (caregiver safety / rental inspection). Below is SAM 3.1 evidence "
        "per concept: presence, frames detected, boxes, confidences, SAM label (added/removed/present_both/not_found) and "
        "pairwise moved verdicts. Write claims ONLY for real changes (added/removed/moved). Do not invent objects. "
        "Return STRICT JSON only: {\"summary\": \"str\", \"claims\": [{\"concept\": \"str\", "
        "\"change\": \"added|removed|moved\", \"explanation\": \"str\", \"safety_note\": \"str or null\"}]}. "
        "safety_note: a short caregiver/rental-relevant note or null.\nDATA:\n" + _json.dumps(payload, default=str))]
    text = _call(content)
    try:
        d = parse_json_loose(text)
        claims = []
        for c in d.get("claims", []):
            if c.get("concept") and c.get("change") in ("added", "removed", "moved"):
                claims.append({"concept": str(c["concept"]).strip().lower(), "change": c["change"],
                               "explanation": str(c.get("explanation", "")), "safety_note": c.get("safety_note")})
        return {"summary": str(d.get("summary", "")), "claims": claims}
    except Exception as e:
        log.warning("write_claims parse failed: %s; %s", e, text[:500])
        return {"summary": "", "claims": []}
