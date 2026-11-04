"""Pure deterministic diff + grounding filter. No API calls."""
from __future__ import annotations

PRESENCE_MIN_FRAMES = 2
CONF_THRESHOLD = 0.5
MOVED_MIN_CONF = 0.8

def summarize_track(parsed: dict) -> dict:
    """Summarise one concept in one video.

    ``best_frame``/``best_box`` are chosen by a demo-friendly score rather
    than raw confidence alone: detections cut off at the frame border are
    penalised (centrality 0.5 vs 1.0 for boxes at least 2 px inside every
    edge), with a small bonus for larger boxes:

        score = c * centrality * (0.75 + 0.25 * min(1, area_frac * 8))

    ``best_conf`` remains the raw confidence of the chosen detection, and
    ``mean_conf``/``frames_detected``/``max_instances`` are unchanged.
    """
    frames, confs, best_frame, best_box, best_c, best_score, max_inst = 0, [], None, None, -1.0, -1.0, 0
    for frame_idx in sorted((parsed or {}).keys(), key=lambda x: int(x)):
        dets = [d for d in parsed[frame_idx] if float(d.get("c", 0)) >= CONF_THRESHOLD]
        if not dets:
            continue
        frames += 1; max_inst = max(max_inst, len(dets))
        for d in dets:
            c = float(d.get("c", 0)); confs.append(c)
            box = list(d.get("box") or [])
            # Centrality / area need a valid box and frame size; be defensive.
            centrality, area_frac = 1.0, 0.0
            try:
                w, h = float(d.get("w", 0) or 0), float(d.get("h", 0) or 0)
                if len(box) == 4 and w > 0 and h > 0:
                    x1, y1, x2, y2 = (float(v) for v in box)
                    touches = x1 < 2 or y1 < 2 or x2 > w - 2 or y2 > h - 2
                    centrality = 0.5 if touches else 1.0
                    area_frac = max(0.0, (x2 - x1) * (y2 - y1)) / (w * h)
            except Exception:
                centrality, area_frac = 1.0, 0.0
            score = c * centrality * (0.75 + 0.25 * min(1.0, area_frac * 8))
            if score > best_score:
                best_score, best_c, best_frame, best_box = score, c, int(frame_idx), list(d.get("box"))
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

def _clean_watchlist(watchlist) -> list[str]:
    if not watchlist:
        return []
    if isinstance(watchlist, str):
        watchlist = [c.strip() for c in watchlist.split(",")]
    out, seen = [], set()
    for item in watchlist or []:
        c = _norm(item)
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out

def _is_watchlist(concept: str, watchlist_norm: list[str]) -> bool:
    """Case-insensitive watchlist match with token-overlap fuzziness."""
    n = _norm(concept)
    if not n or not watchlist_norm:
        return False
    if n in watchlist_norm:
        return True
    n_tokens = set(n.split())
    for w in watchlist_norm:
        if n_tokens & set(w.split()):
            return True
    return False

def _clean_risk(value) -> str | None:
    v = str(value or "").strip().lower()
    return v if v in ("high", "medium", "low") else None

def _claim_risk(claim: dict, concept: str, watchlist_norm: list[str]) -> tuple[str, str]:
    """Risk carried from Spark, with a defensive fallback."""
    risk = _clean_risk(claim.get("risk"))
    reason = str(claim.get("risk_reason") or "")
    if risk is not None:
        return risk, reason
    # Spark omitted/invalid risk: watchlist changes are safety-relevant.
    if _is_watchlist(concept, watchlist_norm):
        return "high", reason or f"'{concept}' is on the caregiver watchlist, so any change to it is treated as high risk."
    return "medium", reason

def _sam_only_risk(concept: str, change: str, watchlist_norm: list[str]) -> tuple[str, str]:
    """Simple risk rule for SAM-only kept claims (no Spark judgement)."""
    if _is_watchlist(concept, watchlist_norm):
        return "high", (f"'{concept}' is on the caregiver watchlist and SAM detected it as {change}; "
                        "check it is within reach and not a trip hazard.")
    return "medium", (f"SAM detected '{concept}' as {change} but Spark did not assess it; "
                      "defaulting to medium risk pending a caregiver check.")

def grounding_filter(raw_claims: list, summaries: dict, moved_verdicts: dict | None = None,
                     watchlist=None) -> tuple[list, list]:
    """Keep only claims SAM supports; add SAM-only added/removed claims.

    'moved' requires present_both AND a moved verdict with
    confidence >= MOVED_MIN_CONF.

    ``risk``/``risk_reason`` from Spark (see spark.write_claims) are
    carried through onto BOTH kept and dropped claims. SAM-only kept
    claims get risk from a simple rule: watchlist item -> high,
    otherwise medium.
    """
    moved_verdicts = moved_verdicts or {}
    watchlist_norm = _clean_watchlist(watchlist)
    kept, dropped, kept_concepts = [], [], set()
    for claim in raw_claims or []:
        if not isinstance(claim, dict):
            dropped.append({"concept": str(claim), "change": None, "explanation": "", "safety_note": None,
                            "risk": "medium", "risk_reason": "",
                            "reason": "malformed claim (not an object)"}); continue
        concept_raw, change = str(claim.get("concept", "")), claim.get("change")
        key, s = _find(concept_raw, summaries)
        risk, risk_reason = _claim_risk(claim, key or concept_raw, watchlist_norm)
        if s is None:
            dropped.append({**claim, "concept": concept_raw, "risk": risk, "risk_reason": risk_reason,
                            "reason": f"no SAM evidence: concept '{concept_raw}' was not tracked"}); continue
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
                         "safety_note": claim.get("safety_note"), "source": "spark",
                         "risk": risk, "risk_reason": risk_reason,
                         "evidence": _evidence(key, s)})
            kept_concepts.add(key)
        else:
            dropped.append({**claim, "concept": key, "risk": risk, "risk_reason": risk_reason,
                            "reason": reason})
    # SAM-only added/removed that Spark missed
    for concept, s in summaries.items():
        if s["label"] in ("added", "removed") and concept not in kept_concepts:
            risk, risk_reason = _sam_only_risk(concept, s["label"], watchlist_norm)
            kept.append({"concept": concept, "change": s["label"],
                         "explanation": f"SAM 3.1 detected '{concept}' as {s['label']} (present in "
                                        f"{s['after']['frames_detected'] if s['label']=='added' else s['before']['frames_detected']} frames).",
                         "safety_note": None, "source": "sam",
                         "risk": risk, "risk_reason": risk_reason,
                         "evidence": _evidence(concept, s)})
            kept_concepts.add(concept)
    return kept, dropped
