"""Muse Spark 1.3: inventory, moved judgement, final claims."""
from __future__ import annotations
import logging
from pathlib import Path
import cv2
from .meta_api import responses, extract_text, parse_json_loose, image_part, text_part, user_message
from .video_io import draw_box

log = logging.getLogger("splatdiff.spark")
MODEL = "muse-spark-1.3"

def _make_body(content: list, max_tokens: int = 4000, retry: bool = False) -> dict:
    body = {"model": MODEL, "input": [user_message(content)], "reasoning": {"effort": "low"},
            "max_output_tokens": 8000 if retry else max_tokens}
    if retry:
        # Extra field changes the request-json hash, so a cached (possibly
        # empty) first response is not returned again from the disk cache.
        body["metadata"] = {"retry": "1"}
    return body

def _call(content: list, max_tokens: int = 4000, retry: bool = False) -> str:
    return extract_text(responses(_make_body(content, max_tokens=max_tokens, retry=retry)))

def _call_json(content: list, max_tokens: int = 4000, what: str = "spark"):
    """Call Spark and parse strict JSON, retrying once on empty/bad output.

    Retry uses metadata={'retry': '1'} (bypasses the disk cache for the
    original request), max_output_tokens=8000 and reasoning effort 'low'.
    Raises the last parse/empty error if both attempts fail, so callers can
    return their conservative defaults. Empty responses are never treated
    as valid and are not (re-)served for the retry thanks to the changed
    request body / cache key.
    """
    last_exc: Exception | None = None
    for attempt in (0, 1):
        retry = attempt == 1
        text = _call(content, max_tokens=max_tokens, retry=retry)
        if not text or not str(text).strip():
            last_exc = ValueError("empty text, cannot parse JSON")
            log.warning("%s: empty text from Spark (attempt %d/2)%s",
                        what, attempt + 1, "; retrying with larger budget" if not retry else "")
            continue
        try:
            return parse_json_loose(text)
        except Exception as e:
            last_exc = e
            log.warning("%s parse failed (attempt %d/2): %s; text=%s",
                        what, attempt + 1, e, str(text)[:500])
            continue
    assert last_exc is not None
    raise last_exc

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
    try:
        data = _call_json(content, what="list_objects")
        objs = data.get("objects", []) if isinstance(data, dict) else data
    except Exception as e:
        log.warning("inventory parse failed: %s", e); objs = []
    if not isinstance(objs, (list, tuple)):
        objs = []
    clean = []
    for o in objs[:12]:
        if isinstance(o, dict) and o.get("concept"):
            clean.append({"concept": str(o["concept"]).strip().lower(),
                          "where_before": str(o.get("where_before", "")), "where_after": str(o.get("where_after", "")),
                          "suspected_change": str(o.get("suspected_change", "unchanged"))})
    return clean

def check_coverage(before_frames: list, after_frames: list) -> dict:
    """Judge whether BEFORE and AFTER walkthroughs cover the same room areas.

    Sends 3 BEFORE + 3 AFTER keyframes to Spark. Returns
    {"score": 0..1, "missing_in_after": [str], "missing_in_before": [str],
     "retake_tip": str}. On any failure returns a neutral default
    (score 1.0, no missing areas) so a coverage-call failure never by
    itself condemns a run; the pipeline still applies the deterministic
    anchor-overlap cap afterwards.
    """
    before_paths = [p for p in list(before_frames or [])[:3] if p is not None]
    after_paths = [p for p in list(after_frames or [])[:3] if p is not None]
    content = [text_part(
        "You are checking whether two phone walkthroughs of the same room cover the same parts of the room. "
        "Images are labelled BEFORE frame i and AFTER frame i; camera viewpoints and order may differ. "
        "Judge which areas/corners/landmarks (e.g. 'bathroom door corner', 'window wall', 'bedside') are visible "
        "in one walkthrough but not the other. Return STRICT JSON only, no markdown: "
        '{"score": 0.0, "missing_in_after": ["area str"], "missing_in_before": ["area str"], "retake_tip": "str"} '
        "with score in 0..1 (1 = both walkthroughs cover essentially the same parts of the room, 0 = almost no "
        "overlap). retake_tip is one short plain sentence telling the filmer what to re-film if coverage differs, "
        "or an empty string if coverage is good.")]
    for i, p in enumerate(before_paths):
        content.append(text_part(f"BEFORE frame {i}"))
        try:
            content.append(image_part(p))
        except Exception as e:
            log.warning("check_coverage: skipping unreadable keyframe %s: %s", p, e)
    for i, p in enumerate(after_paths):
        content.append(text_part(f"AFTER frame {i}"))
        try:
            content.append(image_part(p))
        except Exception as e:
            log.warning("check_coverage: skipping unreadable keyframe %s: %s", p, e)
    default = {"score": 1.0, "missing_in_after": [], "missing_in_before": [], "retake_tip": ""}
    try:
        d = _call_json(content, max_tokens=1500, what="check_coverage")
        if not isinstance(d, dict):
            raise ValueError("parsed JSON is not an object")
    except Exception as e:
        log.warning("check_coverage failed: %s", e)
        return dict(default)
    try:
        score = float(d.get("score", 1.0) or 0.0)
    except Exception:
        score = 1.0
    score = max(0.0, min(1.0, score))
    def _areas(v) -> list[str]:
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, (list, tuple)):
            return []
        return [str(a).strip() for a in v if str(a).strip()]
    return {"score": score,
            "missing_in_after": _areas(d.get("missing_in_after")),
            "missing_in_before": _areas(d.get("missing_in_before")),
            "retake_tip": str(d.get("retake_tip", "") or "")}

def propose_floor_items(after_frames: list) -> list[dict]:
    """Propose up to 6 specific objects lying ON THE FLOOR in a walking path.

    Looks only at AFTER keyframes. Returns [{"concept": str, "where": str}]
    (concept = short singular noun phrase SAM can segment). [] on failure.
    These are proposals only — the pipeline grounds each with SAM before
    keeping it.
    """
    paths = [p for p in list(after_frames or []) if p is not None]
    content = [text_part(
        "You are doing a caregiver fall-safety check of an older adult's room from AFTER-walkthrough keyframes. "
        "List up to 6 SPECIFIC objects lying ON THE FLOOR in a walking path (the route someone walks, e.g. door to "
        "bed to bathroom door) — things that could trip someone: shoes, bags, boxes, cables, laundry, books, etc. "
        "Only list objects you can actually see on the floor in these frames; do NOT list furniture, rugs that lie "
        "flat, or objects on tables/beds/shelves. Use a short singular noun phrase a segmentation model can find "
        "for 'concept', and say where it lies in 'where' (e.g. 'on the floor beside the bed, in the walking path'). "
        'Return STRICT JSON only, no markdown: {"items": [{"concept": "shoes", "where": "str"}]}. '
        "If nothing is on the floor in a walking path, return {\"items\": []}.")]
    for i, p in enumerate(paths):
        content.append(text_part(f"AFTER frame {i}"))
        try:
            content.append(image_part(p))
        except Exception as e:
            log.warning("propose_floor_items: skipping unreadable keyframe %s: %s", p, e)
    try:
        d = _call_json(content, max_tokens=1500, what="propose_floor_items")
        raw = d.get("items", []) if isinstance(d, dict) else d
    except Exception as e:
        log.warning("propose_floor_items failed: %s", e)
        return []
    if not isinstance(raw, (list, tuple)):
        raw = []
    out, seen = [], set()
    for item in raw:
        if isinstance(item, str):
            item = {"concept": item, "where": ""}
        if not isinstance(item, dict):
            continue
        concept = " ".join(str(item.get("concept", "") or "").strip().lower().split())
        if not concept or concept in seen:
            continue
        seen.add(concept)
        out.append({"concept": concept, "where": str(item.get("where", "") or "")})
        if len(out) >= 6:
            break
    return out

# Aliases (same floor-clutter proposer under other plausible names).
floor_clutter_items = propose_floor_items
propose_floor_clutter = propose_floor_items
list_floor_items = propose_floor_items
coverage_check = check_coverage

def suggest_aliases(concept, keyframe_paths) -> list[str]:
    """Suggest up to 3 SAM-friendly alternative names for ``concept``.

    Sends 2 BEFORE keyframes + 2 AFTER keyframes (the caller passes them
    in that order; generically the first half are labelled BEFORE and the
    rest AFTER) and asks Spark for short visual noun phrases a
    text-prompted segmentation model would recognise for this object as
    it appears in these photos (e.g. walker -> 'walking frame',
    'metal walker'). Returns a cleaned list of at most 3 aliases,
    excluding the original concept; [] on any failure.
    """
    concept_clean = " ".join(str(concept or "").strip().lower().split())
    if not concept_clean:
        return []
    paths = []
    if keyframe_paths:
        try:
            paths = list(keyframe_paths)
        except Exception:
            paths = [keyframe_paths]
    paths = [p for p in paths if p is not None and str(p) != ""]
    # Pipeline passes 2 BEFORE + 2 AFTER. Split in half generically so a
    # direct caller passing 4 (or 2, or 6) paths still gets every image
    # sent, labelled BEFORE for the first half and AFTER for the rest.
    if len(paths) >= 2:
        n_before = min(2, (len(paths) + 1) // 2) if len(paths) != 4 else 2
        if len(paths) == 4:
            n_before = 2
    elif paths:
        n_before = 1
    else:
        n_before = 0
    before_paths, after_paths = paths[:n_before], paths[n_before:]
    content = [text_part(
        f"The object '{concept_clean}' was not found by a text-prompted segmentation model (SAM) "
        "under that name in these room photos. Give up to 3 alternative short visual noun phrases a "
        "text-prompted segmentation model would recognise for this object as it appears in these photos "
        "(e.g. walker -> 'walking frame', 'metal walker'). Use short singular visual noun phrases that "
        "describe what the object looks like, not its function alone. Do not repeat the original concept. "
        'Return STRICT JSON only, no markdown: {"aliases": ["...", "..."]}'
    )]
    for i, p in enumerate(before_paths):
        content.append(text_part(f"BEFORE frame {i}"))
        try:
            content.append(image_part(p))
        except Exception as e:
            log.warning("suggest_aliases: skipping unreadable keyframe %s: %s", p, e)
    for i, p in enumerate(after_paths):
        content.append(text_part(f"AFTER frame {i}"))
        try:
            content.append(image_part(p))
        except Exception as e:
            log.warning("suggest_aliases: skipping unreadable keyframe %s: %s", p, e)
    try:
        data = _call_json(content, max_tokens=1000, what=f"suggest_aliases {concept_clean}")
    except Exception as e:
        log.warning("suggest_aliases failed for %s: %s", concept_clean, e)
        return []
    if isinstance(data, dict):
        raw = data.get("aliases", [])
    elif isinstance(data, (list, tuple)):
        raw = data
    else:
        raw = []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    out, seen = [], set()
    for item in raw:
        if isinstance(item, dict):
            item = item.get("alias") or item.get("concept") or item.get("name") or ""
        alias = " ".join(str(item or "").strip().lower().split())
        if not alias or alias == concept_clean or alias in seen:
            continue
        seen.add(alias)
        out.append(alias)
        if len(out) >= 3:
            break
    return out

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
    try:
        d = _call_json(content, max_tokens=1000, what=f"judge_moved {concept}")
        if not isinstance(d, dict):
            raise ValueError("empty text, cannot parse JSON" if not d else "parsed JSON is not an object")
        return {"moved": bool(d.get("moved")), "confidence": float(d.get("confidence", 0.0)), "reason": str(d.get("reason", ""))}
    except Exception as e:
        log.warning("judge_moved parse failed for %s: %s", concept, e)
        if "empty" in str(e).lower():
            return {"moved": False, "confidence": 0.0, "reason": "no response"}
        return {"moved": False, "confidence": 0.0, "reason": "unparseable Spark response"}

def _clean_watchlist(watchlist) -> list[str]:
    if not watchlist:
        return []
    if isinstance(watchlist, str):
        watchlist = [c.strip() for c in watchlist.split(",")]
    out, seen = [], set()
    for item in watchlist:
        c = str(item).strip().lower()
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out

def _clean_risk(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in ("high", "medium", "low") else "medium"

def write_claims(diff_table, moved_verdicts=None, watchlist=None) -> dict:
    """Final Spark call: write claims from the SAM diff table.

    Every claim carries ``risk`` (high|medium|low) and ``risk_reason``
    judged through a caregiver fall/safety lens for an older adult.
    ``watchlist`` items are called out in the prompt so Spark knows
    which items matter most to the caregiver.
    """
    import json as _json
    watch = _clean_watchlist(watchlist)
    payload = {"diff_table": diff_table, "moved_verdicts": moved_verdicts or {},
               "watchlist": watch}
    watch_text = (
        "The caregiver WATCHLIST (items that must stay put and matter most): "
        + (", ".join(watch) if watch else "(none)")
        + ". Changes to watchlist items should normally be high risk unless "
          "the evidence clearly shows the item remains safely within reach. "
    )
    content = [text_part(
        "You are writing a grounded room-change report (caregiver safety / rental inspection). Below is SAM 3.1 evidence "
        "per concept: presence, frames detected, boxes, confidences, SAM label (added/removed/present_both/not_found) and "
        "pairwise moved verdicts. Write claims ONLY for real changes (added/removed/moved). Do not invent objects. "
        + watch_text +
        "For EVERY claim also judge 'risk' (\"high\"|\"medium\"|\"low\") and 'risk_reason' (short str) through a caregiver "
        "fall/safety lens for an older adult living alone: HIGH = trip hazards on the floor, or mobility aids (walker, "
        "cane), medication, or a phone moved out of reach / missing, or anything blocking a walkway to the bed, chair, "
        "bathroom or exit; MEDIUM = changes that could plausibly affect safety, reach, lighting or daily routine but are "
        "not an immediate fall/reach hazard; LOW = cosmetic or safety-irrelevant changes (decor, cushions, books). "
        "Return STRICT JSON only: {\"summary\": \"str\", \"claims\": [{\"concept\": \"str\", "
        "\"change\": \"added|removed|moved\", \"explanation\": \"str\", \"safety_note\": \"str or null\", "
        "\"risk\": \"high|medium|low\", \"risk_reason\": \"str\"}]}. "
        "safety_note: a short caregiver/rental-relevant note or null.\nDATA:\n" + _json.dumps(payload, default=str))]
    try:
        d = _call_json(content, what="write_claims")
        if not isinstance(d, dict):
            raise ValueError("empty text, cannot parse JSON" if not d else "parsed JSON is not an object")
        claims = []
        for c in d.get("claims", []):
            if isinstance(c, dict) and c.get("concept") and c.get("change") in ("added", "removed", "moved"):
                claims.append({"concept": str(c["concept"]).strip().lower(), "change": c["change"],
                               "explanation": str(c.get("explanation", "")), "safety_note": c.get("safety_note"),
                               "risk": _clean_risk(c.get("risk")),
                               "risk_reason": str(c.get("risk_reason") or "")})
        return {"summary": str(d.get("summary", "")), "claims": claims}
    except Exception as e:
        log.warning("write_claims parse failed: %s", e)
        return {"summary": "", "claims": []}
