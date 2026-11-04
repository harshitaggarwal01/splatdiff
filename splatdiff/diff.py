"""Pure deterministic diff + grounding filter. No API calls."""
from __future__ import annotations

PRESENCE_MIN_FRAMES = 2
CONF_THRESHOLD = 0.5
MOVED_MIN_CONF = 0.8

def summarize_track(parsed: dict) -> dict:
    """Summarise one concept in one video."""
    frames, confs, best_frame, best_box, best_c, max_inst = 0, [], None, None, -1.0, 0
    for frame_idx in sorted((parsed or {}).keys(), key=lambda x: int(x)):
        dets = [d for d in parsed[frame_idx] if float(d.get("c", 0)) >= CONF_THRESHOLD]
        if not dets:
            continue
        frames += 1; max_inst = max(max_inst, len(dets))
        for d in dets:
            c = float(d.get("c", 0)); confs.append(c)
            if c > best_c:
                best_c, best_frame, best_box = c, int(frame_idx), list(d.get("box"))
    return {"frames_detected": frames, "max_instances": max_inst,
            "mean_conf": (sum(confs) / len(confs)) if confs else 0.0,
            "best_frame": best_frame, "best_box": best_box,
            "best_conf": best_c if best_c >= 0 else 0.0, "present": frames >= PRESENCE_MIN_FRAMES}

def summarize_tracks(before_tracks: dict, after_tracks: dict) -> dict:
    """Per-concept summaries + SAM label for both videos."""
    out = {}
    for concept in sorted(set(before_tracks) | set(after_tracks)):
        b = summarize_track(before_tracks.get(concept, {}))
        a = summarize_track(after_tracks.get(concept, {}))
        if a["present"] and not b["present"]:
            label = "added"
        elif b["present"] and not a["present"]:
            label = "removed"
        elif b["present"] and a["present"]:
            label = "present_both"
        else:
            label = "not_found"
        out[concept] = {"concept": concept, "before": b, "after": a, "label": label,
                        "original_label": label, "recheck": None,
                        "count_changed": b["max_instances"] != a["max_instances"]}
    return out

def apply_image_recheck(summaries: dict, concept: str, recheck: dict | None) -> dict:
    """Record a SAM image re-check result in ``summaries`` (in place).

    ``recheck`` should contain at least ``video`` (``"before"``/``"after"``,
    the side where the object was supposedly absent), ``keyframe_index``,
    ``box`` and ``c`` when a detection was found. If any detection with
    c >= CONF_THRESHOLD was found, a video-tracking label of ``added`` /
    ``removed`` is corrected to ``present_both``. The original
    video-tracking label is preserved as ``original_label`` so callers can
    still show Spark (and the grounding filter) what video tracking said.
    Returns the updated summary (or {} if the concept is unknown).
    """
    s = summaries.get(concept)
    if s is None:
        return {}
    if "original_label" not in s or not s.get("original_label"):
        s["original_label"] = s.get("label")
    if recheck is None:
        s["recheck"] = {"checked": False, "found": False, "video": None,
                        "keyframe_index": None, "box": None, "c": 0.0}
        return s
    info = dict(recheck)
    info.setdefault("checked", True)
    # Normalise / derive the "found" flag from the confidence.
    try:
        c_val = float(info.get("c", 0.0) or 0.0)
    except Exception:
        c_val = 0.0
    info["c"] = c_val
    if info.get("box") is not None:
        try:
            info["box"] = list(info["box"])
        except Exception:
            pass
    if info.get("keyframe_index") is not None:
        try:
            info["keyframe_index"] = int(info["keyframe_index"])
        except Exception:
            pass
    info["found"] = bool(info.get("found", c_val >= CONF_THRESHOLD and info.get("box") is not None))
    s["recheck"] = info
    if info["found"] and c_val >= CONF_THRESHOLD and s.get("label") in ("added", "removed"):
        s["label"] = "present_both"
    return s

def sam_labels(summaries: dict) -> dict:
    return {c: s.get("label", "not_found") for c, s in summaries.items()}

def _norm(s: str) -> str:
    return " ".join(str(s).lower().strip().split())

def _find(concept: str, summaries: dict):
    n = _norm(concept)
    if n in summaries:
        return n, summaries[n]
    best_key, best_v, best_overlap = None, None, 0
    for k, v in summaries.items():
        overlap = len(set(_norm(k).split()) & set(n.split()))
        if overlap > best_overlap:
            best_key, best_v, best_overlap = k, v, overlap
    if best_key is not None:
        return best_key, best_v
    return None, None

def _evidence(concept: str, s: dict) -> dict:
    return {"concept": concept, "label": s.get("label"),
            "original_label": s.get("original_label", s.get("label")),
            "recheck": s.get("recheck"),
            "frames_before": s["before"]["frames_detected"], "frames_after": s["after"]["frames_detected"],
            "best_box_before": s["before"]["best_box"], "best_box_after": s["after"]["best_box"],
            "best_frame_before": s["before"]["best_frame"], "best_frame_after": s["after"]["best_frame"],
            "confidence_before": s["before"]["best_conf"], "confidence_after": s["after"]["best_conf"],
            "mean_conf_before": s["before"]["mean_conf"], "mean_conf_after": s["after"]["mean_conf"],
            "max_instances_before": s["before"]["max_instances"], "max_instances_after": s["after"]["max_instances"]}

def _recheck_reason(key: str, s: dict, change: str) -> str | None:
    """Specific human-readable reason when a re-check overturns a claim."""
    r = s.get("recheck") or {}
    if not r.get("found"):
        return None
    try:
        c_val = float(r.get("c", 0.0) or 0.0)
    except Exception:
        c_val = 0.0
    video = str(r.get("video", "")).lower()
    side = "BEFORE" if video == "before" else "AFTER" if video == "after" else video.upper()
    idx = r.get("keyframe_index")
    if change == "added" and video == "before":
        return (f"SAM image re-check found '{key}' in BEFORE keyframe {idx} "
                f"(c={c_val:.2f}) - not added")
    if change == "removed" and video == "after":
        return (f"SAM image re-check found '{key}' in AFTER keyframe {idx} "
                f"(c={c_val:.2f}) - not removed")
    return None

def grounding_filter(raw_claims: list, summaries: dict, moved_verdicts: dict | None = None) -> tuple[list, list]:
    """Keep only claims SAM supports; add SAM-only added/removed claims.

    'moved' requires present_both AND a moved verdict with
    confidence >= MOVED_MIN_CONF.
    """
    moved_verdicts = moved_verdicts or {}
    kept, dropped, kept_concepts = [], [], set()
    for claim in raw_claims or []:
        concept_raw, change = str(claim.get("concept", "")), claim.get("change")
        key, s = _find(concept_raw, summaries)
        if s is None:
            dropped.append({**claim, "reason": f"no SAM evidence: concept '{concept_raw}' was not tracked"}); continue
        label = s["label"]
        ok, reason = False, ""
        if change == "added":
            ok = label == "added"
            reason = _recheck_reason(key, s, "added") or (
                f"SAM label is '{label}', not 'added' for '{key}'")
        elif change == "removed":
            ok = label == "removed"
            reason = _recheck_reason(key, s, "removed") or (
                f"SAM label is '{label}', not 'removed' for '{key}'")
        elif change == "moved":
            v = moved_verdicts.get(key) or moved_verdicts.get(concept_raw) or {}
            try:
                v_conf = float(v.get("confidence", 0.0) or 0.0)
            except Exception:
                v_conf = 0.0
            v_moved = bool(v.get("moved"))
            if label != "present_both":
                rc = _recheck_reason(key, s, "moved")
                reason = rc or f"SAM label is '{label}', not 'present_both' for '{key}' - not moved"
            elif not v_moved:
                detail = f": {v.get('reason')}" if v.get("reason") else ""
                reason = (f"moved-judge said not moved for '{key}' "
                          f"(confidence {v_conf:.2f}){detail}")
            elif v_conf < MOVED_MIN_CONF:
                reason = f"moved-judge confidence {v_conf:.2f} < {MOVED_MIN_CONF:.2f}"
            else:
                ok = True
        else:
            reason = f"unsupported change type '{change}'"
        if ok:
            kept.append({"concept": key, "change": change, "explanation": claim.get("explanation", ""),
                         "safety_note": claim.get("safety_note"), "source": "spark", "evidence": _evidence(key, s)})
            kept_concepts.add(key)
        else:
            dropped.append({**claim, "concept": key, "reason": reason})
    # SAM-only added/removed that Spark missed
    for concept, s in summaries.items():
        if s["label"] in ("added", "removed") and concept not in kept_concepts:
            kept.append({"concept": concept, "change": s["label"],
                         "explanation": f"SAM 3.1 detected '{concept}' as {s['label']} (present in "
                                        f"{s['after']['frames_detected'] if s['label']=='added' else s['before']['frames_detected']} frames).",
                         "safety_note": None, "source": "sam", "evidence": _evidence(concept, s)})
            kept_concepts.add(concept)
    return kept, dropped
