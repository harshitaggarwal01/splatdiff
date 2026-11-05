"""End-to-end SplatDiff pipeline + CLI."""
from __future__ import annotations
import argparse, copy, json, logging, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import cv2
from . import diff as diffmod
from .meta_api import total_cost
from .privacy import redact_image, detect_sensitive
from .sam import track_concept, segment_image
from .spark import list_objects, judge_moved, write_claims, suggest_aliases, check_coverage, propose_floor_items
from .video_io import normalize_video, extract_keyframes, read_frame, draw_box
from .wonder import analyse_trend, judge_moved_wonder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("splatdiff.pipeline")
COLORS = {"added": (0, 200, 0), "removed": (0, 0, 220), "moved": (0, 140, 255), "on_floor": (30, 30, 180)}
MAX_CONCEPTS = 16
MAX_REPAIR_CONCEPTS = 6
REPAIR_MIN_CONF = 0.5
PRIVACY_NOTE = "People and paper documents were blurred before any frame was stored, shown or sent to the reasoning model."
ANCHOR_WORDS = diffmod.ANCHOR_WORDS
FLOOR_MIN_CONF = 0.5
FLOOR_BOTTOM_FRAC = 0.6
BRICK_RED = (30, 30, 180)  # BGR brick red
ESCALATION_MIN_CONF = 0.55
ESCALATION_MAX_CONF = 0.80  # exclusive
INTENTIONAL_RISK_REASON = "Dad says he did this on purpose — consider making it the new setup."
INTENTIONAL_CHANGES = ("moved", "removed", "added", "on_floor")
FEED_PATH = Path("cache") / "feed.jsonl"

def _safe(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(s).lower()).strip("_")

def _norm_concept(s: str) -> str:
    return " ".join(str(s).strip().lower().split())

def _clean_list(items) -> list[str]:
    """Accept None / comma string / iterable; return stripped strings."""
    if not items:
        return []
    if isinstance(items, str):
        items = [c.strip() for c in items.split(",")]
    out = []
    for item in items:
        c = str(item).strip()
        if c:
            out.append(c)
    return out

def _clean_intentional(intentional) -> list[dict]:
    """Normalise the ``intentional`` kwarg to [{'concept','quote','speaker'}]."""
    out: list[dict] = []
    if not intentional:
        return out
    if isinstance(intentional, dict):
        intentional = intentional.get("intentional") or intentional.get("items") or []
    if isinstance(intentional, str):
        intentional = [c.strip() for c in intentional.split(",") if c.strip()]
    for item in intentional or []:
        if isinstance(item, dict):
            concept = " ".join(str(item.get("concept", "") or "").strip().lower().split())
            if not concept:
                continue
            out.append({"concept": concept,
                        "quote": str(item.get("quote", "") or ""),
                        "speaker": str(item.get("speaker", "") or "unknown") or "unknown"})
        elif isinstance(item, str) and item.strip():
            out.append({"concept": " ".join(item.strip().lower().split()), "quote": "", "speaker": "unknown"})
    return out

def _token_overlap(a: str, b: str) -> int:
    return len(set(_norm_concept(a).split()) & set(_norm_concept(b).split()))

def _match_intentional(concept: str, intentional_list: list[dict]):
    """Best token-overlap intentional item for a concept, or None."""
    best, best_overlap = None, 0
    for item in intentional_list or []:
        overlap = _token_overlap(concept, str(item.get("concept", "")))
        if overlap > best_overlap:
            best, best_overlap = item, overlap
    return best if best_overlap > 0 else None

def _dedupe_prepend(priority: list[str], rest: list[str], cap: int = MAX_CONCEPTS) -> list[str]:
    """priority first, then rest; dedupe case-insensitively; cap total."""
    out, seen = [], set()
    for c in list(priority) + list(rest):
        key = _norm_concept(c)
        if not key or key in seen:
            continue
        seen.add(key); out.append(str(c).strip())
        if len(out) >= cap:
            break
    return out

def _find_summary(concept: str, summaries: dict):
    """Exact (normalised) match, else best token-overlap match."""
    n = _norm_concept(concept)
    for k, v in summaries.items():
        if _norm_concept(k) == n:
            return k, v
    best_key, best_v, best_overlap = None, None, 0
    for k, v in summaries.items():
        overlap = len(set(_norm_concept(k).split()) & set(n.split()))
        if overlap > best_overlap:
            best_key, best_v, best_overlap = k, v, overlap
    return best_key, best_v

def build_report(result: dict) -> str:
    lines = ["# Second Look — grounded change report", "", result.get("summary") or ""]
    if result.get("room") or result.get("filmed_by"):
        lines += ["", f"Room: {result.get('room') or ''} · Filmed by: {result.get('filmed_by') or 'unknown'}"]
    cov = result.get("coverage")
    if isinstance(cov, dict):
        try:
            pct = round(float(cov.get("score", 0) or 0) * 100)
        except Exception:
            pct = 0
        if cov.get("ok"):
            lines += ["", f"Coverage: both walkthroughs covered the same room ({pct}%)."]
        else:
            lines += ["", f"Coverage: these two walkthroughs don't cover the same corners ({pct}%). {cov.get('retake_tip','')}"]
    priv = result.get("privacy")
    if isinstance(priv, dict):
        lines += ["", f"Privacy: {priv.get('people_blurred',0)} people and {priv.get('documents_blurred',0)} papers blurred. {priv.get('note','')}"]
    trend = result.get("trend")
    if isinstance(trend, dict) and trend.get("trend"):
        lines += ["", f"Trend across visits: {trend['trend']}"]
        for item in trend.get("repeat_items") or []:
            if isinstance(item, dict):
                lines.append(f"- Repeat item: **{item.get('concept','')}** flagged {item.get('times','?')} of {item.get('of_checks','?')} checks.")
    lines += ["", "## Kept claims (SAM-grounded)"]
    if result.get("aliases"):
        lines += ["", "## Vocabulary repair (SAM alias tracking)"]
        for concept, info in result["aliases"].items():
            if isinstance(info, dict) and info.get("alias"):
                try:
                    cval = float(info.get("c", 0) or 0)
                except Exception:
                    cval = 0.0
                lines.append(f"- **{concept}** tracked as \"{info['alias']}\" (best image confidence {cval:.2f}; tried: {', '.join(info.get('tried') or [])})")
    if not result.get("claims"):
        lines.append("- No grounded changes found.")
    for c in result.get("claims", []):
        ev = c.get("evidence", {}) or {}
        try:
            conf_b = float(ev.get("confidence_before", 0) or 0)
        except Exception:
            conf_b = 0.0
        try:
            conf_a = float(ev.get("confidence_after", 0) or 0)
        except Exception:
            conf_a = 0.0
        lines.append(f"- **{c['concept']} — {c['change']}** ({c.get('source','')}) "
                     f"[risk: {c.get('risk','')}] : {c.get('explanation','')} "
                     f"[frames before={ev.get('frames_before')} after={ev.get('frames_after')}, "
                     f"conf before={conf_b:.2f} after={conf_a:.2f}]")
        if c.get("risk_reason"):
            lines.append(f"  - Risk: {c.get('risk','')} — {c['risk_reason']}")
        if isinstance(c.get("intentional"), dict) and c["intentional"].get("quote"):
            lines.append(f"  - On purpose ({c['intentional'].get('speaker','unknown')}): \"{c['intentional']['quote']}\"")
        if c.get("safety_note"):
            lines.append(f"  - Safety note: {c['safety_note']}")
    fc = result.get("floor_check")
    if isinstance(fc, dict) and (fc.get("items") or fc.get("dropped")):
        lines += ["", "## Floor check"]
        for it in fc.get("items", []):
            lines.append(f"- **{it.get('concept','')} — on the floor**: {it.get('where','')} (c={float(it.get('c',0) or 0):.2f})")
        for d in fc.get("dropped", []):
            lines.append(f"- ~~{d.get('concept','')}~~ — dropped: {d.get('reason','')}")
    if result.get("watchlist_status"):
        lines += ["", "## Watchlist"]
        for w in result["watchlist_status"]:
            lines.append(f"- **{w.get('concept','')} — {w.get('status','')}** "
                         f"[risk: {w.get('risk','')}] : {w.get('note','')}")
    lines += ["", "## Dropped claims (not supported by SAM)"]
    if not result.get("dropped"):
        lines.append("- None.")
    for d in result.get("dropped", []):
        lines.append(f"- ~~{d.get('concept','')} — {d.get('change','')}~~ "
                     f"[risk: {d.get('risk','')}] — dropped: {d.get('reason','')}")
    lines += ["", f"Cost estimate (ledger total): ${result.get('cost_usd',0):.4f} · Latency: {result.get('latency_s',0):.1f}s"]
    return "\n".join(lines) + "\n"

def _best_detection(parsed) -> dict | None:
    """Highest-confidence detection (c >= threshold) in segment_image output."""
    best = None
    if isinstance(parsed, (list, tuple)):
        iterable = [parsed]
    elif isinstance(parsed, dict):
        iterable = list(parsed.values())
    else:
        iterable = []
    for dets in iterable:
        if isinstance(dets, dict):
            dets = [dets]
        for d in dets or []:
            try:
                c = float(d.get("c", 0))
            except Exception:
                continue
            if c >= diffmod.CONF_THRESHOLD and (best is None or c > best["c"]):
                box = d.get("box")
                best = {"box": list(box) if box is not None else None, "c": c}
    return best

def _all_detections(parsed) -> list[dict]:
    """Flat detection list (any confidence) from segment_image output."""
    out = []
    if isinstance(parsed, dict):
        iterable = list(parsed.values())
    elif isinstance(parsed, (list, tuple)):
        iterable = [parsed]
    else:
        iterable = []
    for dets in iterable:
        if isinstance(dets, dict):
            dets = [dets]
        for d in dets or []:
            if not isinstance(d, dict):
                continue
            try:
                c = float(d.get("c", 0) or 0)
                box = [float(v) for v in (d.get("box") or [])]
                if len(box) != 4:
                    continue
                h = float(d.get("h", 0) or 0); w = float(d.get("w", 0) or 0)
            except Exception:
                continue
            out.append({"box": box, "c": c, "w": w, "h": h})
    return out

def _run_vocab_repair(summaries: dict, watchlist_list: list, before_norm, after_norm,
                      before_keyframes: list, after_keyframes: list, prog, emit=None,
                      before_tracks: dict | None = None, after_tracks: dict | None = None) -> dict:
    def _emit(ev: dict):
        if emit is not None:
            try:
                emit(ev)
            except Exception:
                log.exception("on_event callback failed for %s", ev)

    empty = {"aliases": {}, "repair_sam_calls": 0, "repaired": 0,
             "spark_calls": 0, "sam_requests": 0, "sam_frames": 0}
    watch_norm = [_norm_concept(w) for w in (watchlist_list or [])]

    def _priority(concept: str) -> int:
        n = _norm_concept(concept)
        return watch_norm.index(n) if n in watch_norm else len(watch_norm)

    candidates = [c for c, s in summaries.items() if isinstance(s, dict) and s.get("label") == "not_found"]
    candidates = sorted(candidates, key=_priority)[:MAX_REPAIR_CONCEPTS]
    if not candidates:
        return empty

    _emit({"stage": "repair", "status": "start", "concepts": list(candidates)})
    prog(f"Vocabulary repair: SAM found nothing for {len(candidates)} concept(s) "
         f"({', '.join(candidates)}); trying Spark-suggested aliases…")
    spark_keyframes = list(before_keyframes or [])[:2] + list(after_keyframes or [])[:2]
    test_keyframes = list(before_keyframes or [])[:3] + list(after_keyframes or [])[:3]

    aliases_result: dict = {}
    repair_sam_calls = 0
    repaired = 0
    spark_calls = 0
    retrack_requests = 0
    retrack_frames = 0

    for concept in candidates:
        tried: list[str] = []
        best_alias = None
        best_c = 0.0
        spark_calls += 1
        try:
            raw_aliases = suggest_aliases(concept, spark_keyframes)
        except Exception as e:
            log.warning("suggest_aliases failed for %s: %s", concept, e)
            raw_aliases = []
        seen = set()
        for a in raw_aliases or []:
            alias = " ".join(str(a or "").strip().lower().split())
            if alias and alias != _norm_concept(concept) and alias not in seen:
                seen.add(alias); tried.append(alias)
        tried = tried[:3]

        if tried and test_keyframes:
            tasks = [(alias, kf) for alias in tried for kf in test_keyframes]
            per_alias_best: dict[str, float] = {}
            repair_sam_calls += len(tasks)

            def _test(task):
                alias, kf = task
                try:
                    parsed = segment_image(kf, alias)
                except Exception as e:
                    log.warning("SAM alias test failed for %s as '%s' on %s: %s", concept, alias, kf, e)
                    return alias, None
                return alias, _best_detection(parsed)

            with ThreadPoolExecutor(max_workers=6) as ex:
                futures = [ex.submit(_test, t) for t in tasks]
                for fut in as_completed(futures):
                    try:
                        alias, det = fut.result()
                    except Exception:
                        log.exception("SAM alias test job failed for %s", concept)
                        continue
                    if det is not None and float(det["c"]) > per_alias_best.get(alias, 0.0):
                        per_alias_best[alias] = float(det["c"])
            for alias in tried:
                cval = per_alias_best.get(alias, 0.0)
                if cval >= REPAIR_MIN_CONF and cval > best_c:
                    best_alias, best_c = alias, float(cval)

        if best_alias is not None:
            alias_before, alias_after = {}, {}
            try:
                alias_before = track_concept(before_norm, best_alias) or {}
            except Exception as e:
                log.exception("SAM repair tracking (before) failed for %s as '%s': %s", concept, best_alias, e)
            try:
                alias_after = track_concept(after_norm, best_alias) or {}
            except Exception as e:
                log.exception("SAM repair tracking (after) failed for %s as '%s': %s", concept, best_alias, e)
            repair_sam_calls += 2
            retrack_requests += 2
            try:
                retrack_frames += len(alias_before) + len(alias_after)
            except Exception:
                pass
            norm_before = {int(k): v for k, v in dict(alias_before).items()}
            norm_after = {int(k): v for k, v in dict(alias_after).items()}
            if before_tracks is not None:
                before_tracks[concept] = norm_before
            if after_tracks is not None:
                after_tracks[concept] = norm_after
            try:
                recomputed = diffmod.summarize_tracks({concept: norm_before}, {concept: norm_after})
                if concept in recomputed:
                    summaries[concept] = recomputed[concept]
            except Exception:
                log.exception("summarize_tracks failed for repaired concept %s", concept)
            if isinstance(summaries.get(concept), dict):
                summaries[concept]["alias"] = best_alias
            aliases_result[concept] = {"alias": best_alias, "tried": list(tried), "c": float(best_c)}
            repaired += 1
            prog(f"Repair: '{concept}' tracked as \"{best_alias}\" (best image c={best_c:.2f}); "
                 f"label now '{summaries.get(concept, {}).get('label', 'not_found')}'")
        else:
            prog(f"Repair: no working alias for '{concept}' (tried: {', '.join(tried) or 'none'})")
        _emit({"stage": "repair", "status": "progress", "concept": concept,
               "alias": best_alias, "tried": list(tried),
               "c": float(best_c) if best_alias is not None else 0.0})

    _emit({"stage": "repair", "status": "done", "repaired": int(repaired)})
    return {"aliases": aliases_result, "repair_sam_calls": int(repair_sam_calls),
            "repaired": int(repaired), "spark_calls": int(spark_calls),
            "sam_requests": int(retrack_requests), "sam_frames": int(retrack_frames)}

def _run_image_rechecks(summaries: dict, before_keyframes: list, after_keyframes: list, prog,
                        emit=None) -> int:
    def _emit(ev: dict):
        if emit is not None:
            try:
                emit(ev)
            except Exception:
                log.exception("on_event callback failed for %s", ev)

    candidates = [(c, s) for c, s in summaries.items() if s.get("label") in ("added", "removed")]
    _emit({"stage": "recheck", "status": "start", "concept": "", "found": False, "c": 0.0})
    if not candidates:
        _emit({"stage": "recheck", "status": "done", "concept": "", "found": False, "c": 0.0})
        return 0
    prog(f"SAM image re-check for {len(candidates)} added/removed concept(s)…")
    absent_side = {}
    for concept, s in candidates:
        absent_side[concept] = "before" if s["label"] == "added" else "after"

    def _job(item):
        concept, s = item
        side = absent_side[concept]
        keyframes = before_keyframes if side == "before" else after_keyframes
        best, calls = None, 0
        for idx, kf_path in enumerate(keyframes or []):
            calls += 1
            try:
                parsed = segment_image(kf_path, concept)
            except Exception as e:
                log.warning("SAM image re-check failed for %s keyframe %s: %s", concept, idx, e)
                continue
            det = _best_detection(parsed)
            if det is not None and (best is None or det["c"] > best["c"]):
                best = {"video": side, "keyframe_index": idx, "box": det["box"], "c": det["c"]}
        return concept, side, best, calls

    found: dict[str, dict] = {}
    total_calls = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_job, item): item[0] for item in candidates}
        for fut in as_completed(futures):
            concept = futures[fut]
            try:
                concept, side, det, calls = fut.result()
            except Exception as e:
                log.exception("SAM image re-check job failed for %s", concept)
                det, calls = None, 0
            total_calls += calls
            if det is not None:
                found[concept] = det
            _emit({"stage": "recheck", "status": "progress", "concept": concept,
                   "found": det is not None,
                   "c": float(det["c"]) if det is not None else 0.0})
    for concept, s in candidates:
        side = absent_side[concept]
        keyframes = before_keyframes if side == "before" else after_keyframes
        if concept in found:
            det = found[concept]
            diffmod.apply_image_recheck(summaries, concept,
                                        {"checked": True, "found": True, "video": side,
                                         "keyframe_index": det["keyframe_index"],
                                         "box": det["box"], "c": det["c"]})
            prog(f"Re-check: SAM image found '{concept}' in {side.upper()} "
                 f"keyframe {det['keyframe_index']} (c={det['c']:.2f}) - label now 'present_both' (was '{s.get('original_label')}')")
        else:
            diffmod.apply_image_recheck(summaries, concept,
                                        {"checked": True, "found": False, "video": side,
                                         "keyframe_index": None, "box": None, "c": 0.0,
                                         "keyframes_checked": len(keyframes or [])})
    _emit({"stage": "recheck", "status": "done", "concept": "", "found": False, "c": 0.0})
    return total_calls

def _judge_frame(side: str, s: dict, norm_path, keyframes: list):
    recheck = s.get("recheck") or {}
    if recheck.get("found") and str(recheck.get("video", "")).lower() == side:
        idx = recheck.get("keyframe_index")
        if idx is not None and keyframes and 0 <= int(idx) < len(keyframes):
            frame = cv2.imread(str(keyframes[int(idx)]))
            if frame is not None:
                return frame, recheck.get("box")
        log.warning("re-check keyframe unavailable for %s side %s; falling back to video frame",
                    s.get("concept"), side)
    summ = s[side]
    frame = read_frame(norm_path, summ["best_frame"] or 0) if summ["best_frame"] is not None else read_frame(norm_path, 0)
    return frame, summ["best_box"]

def _watchlist_note(concept: str, status: str) -> str:
    c = str(concept)
    if status == "missing":
        return (f"{c} is no longer where it was. Check it is within reach of the bed/chair "
                f"and find it before it is needed.")
    if status == "moved":
        return (f"{c} has moved from where it was. Check it is within reach of the bed/chair "
                f"and has not become a trip hazard.")
    if status == "not_seen":
        return (f"{c} was not detected in either video - check it manually; SAM may have missed it, "
                f"or it may have been removed before the BEFORE video.")
    if status == "appeared":
        return (f"{c} was not seen in the BEFORE video but appears in the AFTER video - check it is "
                f"stored safely, within reach if it is needed, and not blocking a walkway.")
    return f"{c} appears to still be in place."

_WATCHLIST_RISK = {"missing": "high", "moved": "high", "not_seen": "medium",
                   "appeared": "medium", "in_place": "low"}

def _build_watchlist_status(watchlist_list: list[str], summaries: dict, kept: list,
                            moved_verdicts: dict, images_for) -> list[dict]:
    moved_kept = {_norm_concept(c.get("concept", "")) for c in kept if c.get("change") == "moved"}
    out = []
    for item in watchlist_list:
        key, s = _find_summary(item, summaries)
        concept = key or _norm_concept(item)
        if s is None:
            status = "not_seen"
        else:
            label = s.get("label", "not_found")
            if label == "removed":
                status = "missing"
            elif label == "added":
                status = "appeared"
            elif label == "present_both":
                v = moved_verdicts.get(key) or {}
                try:
                    v_conf = float(v.get("confidence", 0.0) or 0.0)
                except Exception:
                    v_conf = 0.0
                verdict_kept = bool(v.get("moved")) and v_conf >= diffmod.MOVED_MIN_CONF
                status = "moved" if (_norm_concept(key) in moved_kept or verdict_kept) else "in_place"
            else:
                status = "not_seen"
        note = _watchlist_note(concept, status)
        alias = s.get("alias") if isinstance(s, dict) else None
        if alias and f'tracked as "{alias}"' not in note:
            note = f"{note} (tracked as \"{alias}\")"
        out.append({"concept": concept, "status": status,
                    "risk": _WATCHLIST_RISK.get(status, "medium"),
                    "note": note,
                    "images": images_for(concept)})
    return out

def _read_feed_entries(room: str) -> list[dict]:
    """Earlier family-feed entries for the same room, in file order."""
    entries: list[dict] = []
    try:
        if not FEED_PATH.is_file():
            return entries
        for line in FEED_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and _norm_concept(obj.get("room", "")) == _norm_concept(room):
                entries.append(obj)
    except Exception as e:  # noqa: BLE001
        log.warning("could not read feed for trend: %s", e)
        return []
    return entries

def run(before, after, concepts=None, out_dir="outputs", progress=None, on_event=None, watchlist=None,
        room=None, filmed_by=None, intentional=None) -> dict:
    def prog(msg: str):
        log.info(msg)
        if progress:
            progress(msg)

    start, cost_start = time.time(), total_cost()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    room = str(room).strip() if room and str(room).strip() else "Bedroom"
    filmed_by = str(filmed_by).strip() if filmed_by and str(filmed_by).strip() else None
    watchlist_list = _clean_list(watchlist)
    intentional_list = _clean_intentional(intentional)
    event_lock = threading.Lock()
    # Mutable counters for stages that also run inside annotation helpers.
    counters = {"privacy_checks": 0, "coverage_calls": 0, "floor_checks": 0, "floor_spark_calls": 0}
    wonder_state = {"called": False}
    wonder_lock = threading.Lock()

    def _mark_wonder_called():
        with wonder_lock:
            wonder_state["called"] = True

    def _running_cost() -> float:
        try:
            return round(float(total_cost()) - float(cost_start), 6)
        except Exception:
            return 0.0

    def emit(ev: dict):
        """Thread-safe structured event: adds elapsed_s + running cost_usd."""
        if on_event is None:
            return
        event = dict(ev)
        event["elapsed_s"] = round(time.time() - start, 3)
        event["cost_usd"] = _running_cost()
        with event_lock:
            try:
                on_event(event)
            except Exception:
                log.exception("on_event callback failed for %s", event)

    try:
        out = Path(out_dir) / run_id; out.mkdir(parents=True, exist_ok=True)

        def _url(filename: str) -> str:
            return f"/outputs/{run_id}/{filename}"

        def _images_for(concept: str) -> dict:
            safe = _safe(concept)
            b_name, a_name = f"before_{safe}.jpg", f"after_{safe}.jpg"
            return {"before": _url(b_name) if (out / b_name).exists() else None,
                    "after": _url(a_name) if (out / a_name).exists() else None}

        def _redact_frame_arr(frame):
            """Privacy-blur a raw ndarray frame (annotated evidence).

            Runs the same two SAM image checks as the keyframe privacy
            stage and blurs any sensitive boxes. Never raises.
            """
            if frame is None:
                return frame
            counters["privacy_checks"] += 2
            try:
                sensitive = detect_sensitive(frame)
                boxes = (sensitive or {}).get("boxes") or []
                if boxes:
                    return redact_image(frame, boxes)
            except Exception as e:
                log.warning("annotated-frame redaction failed: %s", e)
            return frame

        # 1. Normalize
        emit({"stage": "normalize", "status": "start"})
        prog("Normalising videos (ffmpeg, 5 fps, max 30 s)…")
        before_norm, after_norm = normalize_video(before), normalize_video(after)
        emit({"stage": "normalize", "status": "done"})

        # 2. Keyframes
        prog("Extracting keyframes…")
        bf = extract_keyframes(before_norm, 6, out / "keyframes_before")
        af = extract_keyframes(after_norm, 6, out / "keyframes_after")
        keyframe_urls = {
            "before": [f"/outputs/{run_id}/keyframes_before/{Path(p).name}" for p in (bf or [])],
            "after": [f"/outputs/{run_id}/keyframes_after/{Path(p).name}" for p in (af or [])],
        }
        emit({"stage": "keyframes", "status": "done",
              "before": list(keyframe_urls["before"]), "after": list(keyframe_urls["after"])})

        # 2b. Privacy — BEFORE any keyframe is sent to Muse Spark.
        # SAM 3.1 itself sees raw frames because it is the detector.
        privacy = {"people_blurred": 0, "documents_blurred": 0, "frames_checked": 0, "note": PRIVACY_NOTE}
        emit({"stage": "privacy", "status": "start"})
        prog("Blurring people and paper documents in keyframes (SAM 3.1)…")
        try:
            all_kf = [p for p in list(bf or []) + list(af or []) if p is not None]
            privacy["frames_checked"] = int(len(all_kf))
            counters["privacy_checks"] += 2 * len(all_kf)

            def _privacy_job(kf):
                people, docs = [], []
                try:
                    sensitive = detect_sensitive(kf) or {}
                    people = list(sensitive.get("person") or [])
                    docs = list(sensitive.get("paper document") or sensitive.get("paper_document") or [])
                    boxes = list(sensitive.get("boxes") or (people + docs))
                    if boxes:
                        redact_image(kf, boxes)  # in place for path inputs
                except Exception as e:
                    log.warning("privacy redaction failed for keyframe %s: %s", kf, e)
                return len(people), len(docs)

            if all_kf:
                with ThreadPoolExecutor(max_workers=6) as ex:
                    futures = [ex.submit(_privacy_job, kf) for kf in all_kf]
                    for fut in as_completed(futures):
                        try:
                            n_people, n_docs = fut.result()
                        except Exception:
                            log.exception("privacy job failed")
                            n_people, n_docs = 0, 0
                        privacy["people_blurred"] += int(n_people)
                        privacy["documents_blurred"] += int(n_docs)
            emit({"stage": "privacy", "status": "done",
                  "people_blurred": int(privacy["people_blurred"]),
                  "documents_blurred": int(privacy["documents_blurred"]),
                  "frames_checked": int(privacy["frames_checked"])})
            prog(f"Privacy: blurred {privacy['people_blurred']} people, "
                 f"{privacy['documents_blurred']} documents across {privacy['frames_checked']} keyframes.")
        except Exception as e:
            log.exception("privacy stage failed; continuing")
            privacy = {"people_blurred": int(privacy.get("people_blurred", 0) or 0),
                       "documents_blurred": int(privacy.get("documents_blurred", 0) or 0),
                       "frames_checked": int(privacy.get("frames_checked", 0) or 0),
                       "note": PRIVACY_NOTE}
            emit({"stage": "privacy", "status": "done",
                  "people_blurred": privacy["people_blurred"],
                  "documents_blurred": privacy["documents_blurred"],
                  "frames_checked": privacy["frames_checked"], "error": str(e)})

        # 3. Inventory (watchlist always tracked: prepended, capped)
        emit({"stage": "inventory", "status": "start", "model": "muse-spark-1.3",
              "concepts": [], "objects": []})
        prog("Inventorying objects with Muse Spark 1.3…")
        inventory_called = not bool(concepts)
        objects = list_objects(bf, af, concepts=concepts)
        inventory_concepts = [o["concept"] for o in objects if isinstance(o, dict) and o.get("concept")]
        concept_list = _dedupe_prepend(watchlist_list, inventory_concepts, cap=MAX_CONCEPTS)
        known = {_norm_concept(o.get("concept", "")) for o in objects if isinstance(o, dict)}
        extra_objects = [{"concept": c, "where_before": "", "where_after": "",
                          "suspected_change": "unchanged"}
                         for c in concept_list if _norm_concept(c) not in known]
        if extra_objects:
            objects = extra_objects + list(objects)
        emit({"stage": "inventory", "status": "done", "model": "muse-spark-1.3",
              "concepts": list(concept_list), "objects": objects})
        prog(f"Concepts ({len(concept_list)}): {', '.join(concept_list) or 'none'}")

        # 3b. Coverage (Spark part) — after inventory, before tracking.
        # Final score also needs post-tracking anchor overlap, so the
        # "done" event is emitted after tracking (see 4c).
        emit({"stage": "coverage", "status": "start", "model": "muse-spark-1.3"})
        prog("Checking walkthrough coverage with Muse Spark 1.3…")
        coverage_spark = {"score": 1.0, "missing_in_after": [], "missing_in_before": [], "retake_tip": ""}
        coverage_error = None
        counters["coverage_calls"] += 1
        try:
            cov = check_coverage(bf, af) or {}
            try:
                spark_score_tmp = float(cov.get("score", 1.0) or 0.0)
            except Exception:
                spark_score_tmp = 1.0
            coverage_spark = {"score": max(0.0, min(1.0, spark_score_tmp)),
                              "missing_in_after": [str(a) for a in (cov.get("missing_in_after") or [])],
                              "missing_in_before": [str(a) for a in (cov.get("missing_in_before") or [])],
                              "retake_tip": str(cov.get("retake_tip", "") or "")}
        except Exception as e:
            coverage_error = str(e)
            log.exception("coverage Spark call failed; continuing with anchor overlap only")

        # 4. SAM tracking (concurrent; progress as each future completes)
        prog("Tracking concepts with SAM 3.1 (concurrent)…")
        tasks = [(c, "before", before_norm) for c in concept_list] + [(c, "after", after_norm) for c in concept_list]
        emit({"stage": "track", "status": "start", "total": len(tasks)})
        before_tracks, after_tracks = {}, {}
        sam_requests, sam_frames = 0, 0

        def _job(t):
            concept, side, path = t
            try:
                return concept, side, track_concept(path, concept)
            except Exception as e:
                log.exception("SAM failed for %s/%s", concept, side); return concept, side, {}

        done_count = 0
        if tasks:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futures = {ex.submit(_job, t): t for t in tasks}
                for fut in as_completed(futures):
                    concept, side, parsed = fut.result()
                    parsed = parsed or {}
                    (before_tracks if side == "before" else after_tracks)[concept] = {
                        int(k): v for k, v in parsed.items()}
                    done_count += 1; sam_requests += 1
                    try:
                        n_frames = len(parsed)
                        n_dets = sum(len(v or []) for v in parsed.values())
                    except Exception:
                        n_frames, n_dets = 0, 0
                    sam_frames += n_frames
                    emit({"stage": "track", "status": "progress", "concept": concept,
                          "video": side, "frames": int(n_frames), "detections": int(n_dets),
                          "done": done_count, "total": len(tasks)})
        emit({"stage": "track", "status": "done"})
        summaries = diffmod.summarize_tracks(before_tracks, after_tracks)

        # 4b. Vocabulary repair
        repair = _run_vocab_repair(summaries, watchlist_list, before_norm, after_norm,
                                   bf, af, prog, emit=emit,
                                   before_tracks=before_tracks, after_tracks=after_tracks)
        aliases = repair.get("aliases", {}) or {}
        sam_requests += int(repair.get("sam_requests", 0) or 0)
        sam_frames += int(repair.get("sam_frames", 0) or 0)

        original_summaries = copy.deepcopy(summaries)

        # 5. SAM image re-checks (emits its own start/progress/done events)
        recheck_calls = _run_image_rechecks(summaries, bf, af, prog, emit=emit)
        rechecks_count = sum(1 for s in summaries.values() if (s.get("recheck") or {}).get("checked"))

        # 4c. Coverage (final) — deterministic anchor overlap after tracking.
        coverage = {"score": 1.0, "ok": True, "anchor_overlap": 1.0,
                    "spark_score": float(coverage_spark.get("score", 1.0) or 0.0),
                    "shared_anchors": [], "only_before": [], "only_after": [],
                    "missing_in_after": list(coverage_spark.get("missing_in_after") or []),
                    "missing_in_before": list(coverage_spark.get("missing_in_before") or []),
                    "retake_tip": str(coverage_spark.get("retake_tip", "") or "")}
        try:
            shared, only_b, only_a = [], [], []
            for concept, s in (summaries or {}).items():
                if not diffmod.is_anchor(concept):
                    continue
                b_present = bool((s.get("before") or {}).get("present"))
                a_present = bool((s.get("after") or {}).get("present"))
                if b_present and a_present:
                    shared.append(concept)
                elif b_present:
                    only_b.append(concept)
                elif a_present:
                    only_a.append(concept)
            either = len(shared) + len(only_b) + len(only_a)
            anchor_overlap = (len(shared) / either) if either else 1.0
            spark_score = float(coverage_spark.get("score", 1.0) or 0.0)
            final_score = min(spark_score, float(anchor_overlap))
            coverage = {"score": float(final_score), "ok": bool(final_score >= 0.6),
                        "anchor_overlap": float(anchor_overlap), "spark_score": float(spark_score),
                        "shared_anchors": shared, "only_before": only_b, "only_after": only_a,
                        "missing_in_after": list(coverage_spark.get("missing_in_after") or []),
                        "missing_in_before": list(coverage_spark.get("missing_in_before") or []),
                        "retake_tip": str(coverage_spark.get("retake_tip", "") or "")}
        except Exception as e:
            log.exception("coverage anchor computation failed; continuing")
            if coverage_error is None:
                coverage_error = str(e)
        cov_done = {"stage": "coverage", "status": "done", "score": float(coverage.get("score", 0) or 0),
                    "ok": bool(coverage.get("ok")), "retake_tip": str(coverage.get("retake_tip", "") or "")}
        if coverage_error:
            cov_done["error"] = coverage_error
        emit(cov_done)
        prog(f"Coverage: score={coverage['score']:.2f} ok={coverage['ok']} "
             f"(spark={coverage['spark_score']:.2f}, anchors={coverage['anchor_overlap']:.2f})")

        # 5b. Floor clutter check (grounded) — after tracking.
        floor_check = {"items": [], "dropped": []}
        floor_error = None
        emit({"stage": "floor", "status": "start", "model": "muse-spark-1.3"})
        prog("Checking the floor and walking path for clutter…")
        try:
            counters["floor_spark_calls"] += 1
            try:
                proposals = propose_floor_items(af) or []
            except Exception as e:
                log.warning("floor proposal failed: %s", e)
                proposals = []
                floor_error = str(e)
            proposals = [p for p in proposals if isinstance(p, dict) and p.get("concept")][:6]

            # Frame heights for the floor (y2) test, per AFTER keyframe.
            kf_heights: list[float] = []
            for kf in (af or []):
                hgt = 0.0
                try:
                    img_tmp = cv2.imread(str(kf))
                    if img_tmp is not None:
                        hgt = float(img_tmp.shape[0])
                except Exception:
                    hgt = 0.0
                kf_heights.append(hgt)

            def _floor_job(item):
                concept = " ".join(str(item.get("concept", "") or "").strip().lower().split())
                where = str(item.get("where", "") or "")
                best = None  # (c, box, kf_index, frame_h)
                calls = 0
                for idx, kf in enumerate(af or []):
                    calls += 1
                    try:
                        parsed = segment_image(kf, concept)
                    except Exception as e:
                        log.warning("floor SAM check failed for %s on %s: %s", concept, kf, e)
                        continue
                    for det in _all_detections(parsed):
                        frame_h = float(det.get("h") or 0) or (kf_heights[idx] if idx < len(kf_heights) else 0.0)
                        if frame_h <= 0:
                            continue
                        box = det["box"]
                        if float(det["c"]) >= FLOOR_MIN_CONF and float(box[3]) >= FLOOR_BOTTOM_FRAC * frame_h:
                            if best is None or float(det["c"]) > float(best[0]):
                                best = (float(det["c"]), [int(round(v)) for v in box], idx, frame_h)
                return {"concept": concept, "where": where, "_best": best, "_calls": calls}

            verified: list[dict] = []
            if proposals:
                with ThreadPoolExecutor(max_workers=6) as ex:
                    futures = [ex.submit(_floor_job, p) for p in proposals]
                    for fut in as_completed(futures):
                        try:
                            verified.append(fut.result())
                        except Exception:
                            log.exception("floor verification job failed")
            # Keep proposal order for deterministic output.
            order = {_norm_concept(p.get("concept", "")): i for i, p in enumerate(proposals)}
            verified.sort(key=lambda v: order.get(_norm_concept(v.get("concept", "")), 99))
            for v in verified:
                counters["floor_checks"] += int(v.pop("_calls", 0) or 0)
                best = v.pop("_best", None)
                concept = v["concept"]; where = v["where"]
                if best is None:
                    floor_check["dropped"].append({
                        "concept": concept,
                        "reason": (f"SAM did not confirm '{concept}' on the floor in the AFTER keyframes "
                                   f"(need c >= {FLOOR_MIN_CONF:.2f} and box bottom in the lower floor area)")})
                    continue
                c_val, box, kf_idx, _fh = best
                # Save a redacted, annotated image for this kept item.
                img_url = None
                try:
                    frame = cv2.imread(str((af or [])[kf_idx])) if af and 0 <= kf_idx < len(af) else None
                    if frame is None and af:
                        frame = cv2.imread(str(af[0]))
                    if frame is not None:
                        frame = _redact_frame_arr(frame)
                        fname = f"floor_{_safe(concept)}.jpg"
                        cv2.imwrite(str(out / fname), draw_box(frame, box, f"{concept}: on the floor", BRICK_RED))
                        img_url = _url(fname)
                except Exception as e:
                    log.warning("floor annotated image failed for %s: %s", concept, e)
                floor_check["items"].append({"concept": concept, "where": where,
                                             "c": float(c_val), "image": img_url,
                                             "box": box, "keyframe_index": int(kf_idx)})
            prog(f"Floor check: {len(floor_check['items'])} kept, {len(floor_check['dropped'])} dropped.")
        except Exception as e:
            floor_error = str(e)
            log.exception("floor stage failed; continuing")
            floor_check = {"items": [], "dropped": list(floor_check.get("dropped", []))}
        floor_done = {"stage": "floor", "status": "done",
                      "kept": int(len(floor_check.get("items", []))),
                      "dropped": int(len(floor_check.get("dropped", [])))}
        if floor_error:
            floor_done["error"] = floor_error
        emit(floor_done)

        # 6. Moved judge (concurrent; progress as each future completes)
        # Escalation: Spark confidence in [0.55, 0.80) -> muse-wonder-1.0
        # re-judges with the same evidence images and its verdict is final.
        prog("Judging moved objects with Muse Spark 1.3…")
        emit({"stage": "judge", "status": "start", "concept": "", "moved": False,
              "confidence": 0.0, "reason": ""})
        moved_verdicts = {}
        judge_items = [(concept, s) for concept, s in summaries.items() if s["label"] == "present_both"]
        if judge_items:
            prog(f"Judging moved objects concurrently for {len(judge_items)} concept(s)…")

        def _judge_job(item):
            concept, s = item
            bp = ap = None
            try:
                bframe, bbox = _judge_frame("before", s, before_norm, bf)
                aframe, abox = _judge_frame("after", s, after_norm, af)
                if bframe is None or aframe is None:
                    return concept, {"moved": False, "confidence": 0.0, "reason": "best frame unavailable"}
                bp, ap = out / f"_judge_{_safe(concept)}_before.jpg", out / f"_judge_{_safe(concept)}_after.jpg"
                cv2.imwrite(str(bp), bframe); cv2.imwrite(str(ap), aframe)
                try:
                    verdict = judge_moved(concept, str(bp), str(ap), bbox, abox)
                except Exception as e:
                    log.exception("judge_moved failed %s", concept)
                    verdict = {"moved": False, "confidence": 0.0, "reason": str(e)}
                if not isinstance(verdict, dict):
                    verdict = {"moved": False, "confidence": 0.0, "reason": "unparseable Spark response"}
                # --- Escalation judge (muse-wonder-1.0) ---
                try:
                    spark_conf = float(verdict.get("confidence", 0.0) or 0.0)
                except Exception:
                    spark_conf = 0.0
                if ESCALATION_MIN_CONF <= spark_conf < ESCALATION_MAX_CONF:
                    _mark_wonder_called()
                    prog(f"Escalating '{concept}' to muse-wonder-1.0 "
                         f"(Spark confidence {spark_conf:.2f} in [0.55, 0.80))…")
                    wonder_verdict = None
                    try:
                        wonder_verdict = judge_moved_wonder(concept, str(bp), str(ap), bbox, abox)
                    except Exception as e:  # noqa: BLE001
                        log.warning("Wonder escalation failed for %s: %s", concept, e)
                        wonder_verdict = None
                    if isinstance(wonder_verdict, dict) and "moved" in wonder_verdict:
                        try:
                            w_conf = float(wonder_verdict.get("confidence", 0.0) or 0.0)
                        except Exception:
                            w_conf = 0.0
                        verdict = {"moved": bool(wonder_verdict.get("moved")),
                                   "confidence": max(0.0, min(1.0, w_conf)),
                                   "reason": str(wonder_verdict.get("reason", "") or ""),
                                   "first_opinion": dict(verdict),
                                   "escalated": True,
                                   "model": "muse-wonder-1.0"}
                return concept, verdict
            except Exception as e:
                log.exception("judge_moved failed %s", concept)
                return concept, {"moved": False, "confidence": 0.0, "reason": str(e)}
            finally:
                for _p in (bp, ap):
                    if _p is not None:
                        try:
                            _p.unlink(missing_ok=True)
                        except Exception:
                            pass

        if judge_items:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futures = {ex.submit(_judge_job, item): item[0] for item in judge_items}
                for fut in as_completed(futures):
                    concept = futures[fut]
                    try:
                        concept, verdict = fut.result()
                    except Exception as e:
                        log.exception("judge job failed %s", concept)
                        verdict = {"moved": False, "confidence": 0.0, "reason": str(e)}
                    moved_verdicts[concept] = verdict
                    try:
                        v_conf = float(verdict.get("confidence", 0.0) or 0.0)
                    except Exception:
                        v_conf = 0.0
                    prog(f"Judged '{concept}': moved={bool(verdict.get('moved'))} (confidence {v_conf:.2f})"
                         + (" [escalated to muse-wonder-1.0]" if verdict.get("escalated") else ""))
                    judge_event = {"stage": "judge", "status": "progress", "concept": concept,
                                   "moved": bool(verdict.get("moved")), "confidence": v_conf,
                                   "reason": str(verdict.get("reason", ""))}
                    if verdict.get("escalated"):
                        judge_event["escalated"] = True
                        judge_event["model"] = "muse-wonder-1.0"
                    emit(judge_event)
        emit({"stage": "judge", "status": "done", "concept": "", "moved": False,
              "confidence": 0.0, "reason": ""})

        # 7. Final Spark report
        emit({"stage": "report", "status": "start", "model": "muse-spark-1.3", "raw_claims": 0})
        prog("Writing grounded report with Muse Spark 1.3…")
        written = write_claims(original_summaries, moved_verdicts, watchlist=watchlist_list)
        raw_claims = written.get("claims", [])
        emit({"stage": "report", "status": "done", "model": "muse-spark-1.3",
              "raw_claims": len(raw_claims)})

        # 8. Grounding filter (carries risk/risk_reason; coverage drop added)
        kept, dropped = diffmod.grounding_filter(raw_claims, summaries, moved_verdicts,
                                                 watchlist=watchlist_list, coverage=coverage)
        # A concept can be struck twice (Spark claim + SAM-only pass); show it once.
        _seen_drop, _deduped = set(), []
        for _d in dropped:
            _k = (str(_d.get("concept", "")).lower(), str(_d.get("change", "")))
            if _k not in _seen_drop:
                _seen_drop.add(_k)
                _deduped.append(_d)
        dropped = _deduped
        # The summary is written before the filter; if it repeats a struck claim, rebuild it
        # from what was actually proven so the headline never asserts an unproven change.
        _summary_text = str(written.get("summary", "") or "")
        _struck_names = [str(_d.get("concept", "")) for _d in dropped if _d.get("concept")]
        if _summary_text and any(n and n.lower() in _summary_text.lower() for n in _struck_names):
            _verb = {"moved": "moved", "added": "is new", "removed": "is gone", "on_floor": "is on the floor"}
            _proven = [f"{str(k.get('concept', '')).capitalize()} {_verb.get(k.get('change'), k.get('change'))}"
                       for k in kept]
            _rebuilt = ("; ".join(_proven) + ".") if _proven else "No change could be proven."
            _rebuilt += f" {len(dropped)} unproven claim{'s' if len(dropped) != 1 else ''} struck."
            written["summary"] = _rebuilt
        emit({"stage": "filter", "status": "done", "kept": len(kept), "dropped": len(dropped)})

        for claim in list(kept) + list(dropped):
            _key, _s = _find_summary(str(claim.get("concept", "")), summaries)
            alias = _s.get("alias") if isinstance(_s, dict) else None
            if not alias and _key in aliases:
                alias = (aliases.get(_key) or {}).get("alias")
            if not alias:
                continue
            phrase = f'tracked as "{alias}"'
            explanation = str(claim.get("explanation", "") or "")
            if phrase not in explanation:
                claim["explanation"] = (explanation + f" ({phrase})").strip() if explanation else f"({phrase})"
            ev = claim.get("evidence")
            if isinstance(ev, dict):
                ev["alias"] = alias
                ev["tracked_as"] = alias
                if phrase not in str(ev.get("note", "")):
                    ev["note"] = (str(ev.get("note", "")) + f" {phrase}").strip()

        # Effective change per concept for annotation colours
        eff = {c["concept"]: c["change"] for c in kept}
        annotated = []
        prog("Saving annotated keyframes and outputs…")
        for concept, s in summaries.items():
            change = eff.get(concept)
            color = COLORS.get(change, (180, 180, 180))
            label_text = f"{concept}: {change}" if change else f"{concept}: {s['label']}"
            for side, norm, summ, keyframes in (("before", before_norm, s["before"], bf), ("after", after_norm, s["after"], af)):
                recheck = s.get("recheck") or {}
                is_recheck_side = bool(recheck.get("found") and str(recheck.get("video", "")).lower() == side
                          and recheck.get("keyframe_index") is not None and recheck.get("box") is not None)
                if summ["best_frame"] is None or summ["best_box"] is None:
                    if not is_recheck_side:
                        continue
                    if change == "added" and side == "before":
                        continue
                    if change == "removed" and side == "after":
                        continue
                    idx = int(recheck["keyframe_index"])
                    if not (0 <= idx < len(keyframes or [])):
                        continue
                    frame = cv2.imread(str(keyframes[idx]))
                    if frame is None:
                        continue
                    frame = _redact_frame_arr(frame)
                    p = out / f"{side}_{_safe(concept)}.jpg"
                    cv2.imwrite(str(p), draw_box(frame, recheck["box"], label_text, color))
                    annotated.append(str(p))
                    continue
                if change == "added" and side == "before":
                    continue
                if change == "removed" and side == "after":
                    continue
                frame = read_frame(norm, summ["best_frame"])
                if frame is None:
                    continue
                frame = _redact_frame_arr(frame)
                p = out / f"{side}_{_safe(concept)}.jpg"
                cv2.imwrite(str(p), draw_box(frame, summ["best_box"], label_text, color))
                annotated.append(str(p))

        # Evidence images (annotated frames) on every kept + dropped claim.
        for claim in list(kept) + list(dropped):
            claim["images"] = _images_for(str(claim.get("concept", "")))
            claim.setdefault("risk", "medium")
            claim.setdefault("risk_reason", "")

        # Floor kept items are ALSO kept claims (change "on_floor").
        for item in floor_check.get("items", []):
            concept = item.get("concept", "")
            where = str(item.get("where", "") or "")
            where_l = where.lower()
            high = any(tok in where_l for tok in ("bed", "path", "walk", "door", "hallway", "route", "bathroom"))
            risk = "high" if high else "medium"
            claim = {"concept": concept, "change": "on_floor",
                     "explanation": where or f"'{concept}' is lying on the floor in a walking path.",
                     "safety_note": "Trip hazard on the floor — move it off the walking path.",
                     "source": "spark+sam", "risk": risk,
                     "risk_reason": ("On the floor near the bed/walking path — a trip hazard for an older adult."
                                     if high else "On the floor where someone may walk — a possible trip hazard."),
                     "evidence": {"concept": concept, "label": "on_floor",
                                  "frames_before": None, "frames_after": None,
                                  "best_box_before": None, "best_box_after": item.get("box"),
                                  "confidence_before": 0.0, "confidence_after": float(item.get("c", 0) or 0)},
                     "images": {"before": None, "after": item.get("image")}}
            kept.append(claim)
            if item.get("image"):
                img_path = out / Path(str(item["image"])).name
                if str(img_path) not in annotated and img_path.exists():
                    annotated.append(str(img_path))

        watchlist_status = _build_watchlist_status(watchlist_list, summaries, kept,
                                                   moved_verdicts, _images_for)

        # Dad's say: changes Dad says he made on purpose are intentional.
        if intentional_list:
            for claim in kept:
                if str(claim.get("change", "")) not in INTENTIONAL_CHANGES:
                    continue
                match = _match_intentional(str(claim.get("concept", "")), intentional_list)
                if match is None:
                    continue
                claim["intentional"] = {"quote": str(match.get("quote", "") or ""),
                                         "speaker": str(match.get("speaker", "") or "unknown") or "unknown"}
                claim["risk"] = "low"
                claim["risk_reason"] = INTENTIONAL_RISK_REASON
                prog(f"Intentional: '{claim.get('concept')}' ({claim.get('change')}) — "
                     f"{match.get('speaker', 'unknown')}: \"{match.get('quote', '')}\"")

        # Trend across visits: with >= 2 earlier feed entries for the
        # same room, muse-wonder-1.0 (text only) summarises the trend.
        # Skipped silently otherwise (or on any failure).
        trend_result = None
        try:
            earlier_feed = _read_feed_entries(room)
            if len(earlier_feed) >= 2:
                recent_feed = list(reversed(earlier_feed[-20:]))  # newest first, max 20
                _mark_wonder_called()
                trend_candidate = analyse_trend(recent_feed, kept, watchlist_status)
                if isinstance(trend_candidate, dict):
                    trend_result = trend_candidate
                    emit({"stage": "trend", "status": "done", "trend": trend_result,
                          "model": "muse-wonder-1.0"})
                    prog(f"Trend across {len(recent_feed)} earlier check(s): {trend_result.get('trend')}")
        except Exception as e:  # noqa: BLE001
            log.warning("trend stage skipped: %s", e)
            trend_result = None

        spark_calls = ((1 if inventory_called else 0) + len(judge_items) + 1
                       + int(repair.get("spark_calls", 0) or 0)
                       + int(counters.get("coverage_calls", 0) or 0)
                       + int(counters.get("floor_spark_calls", 0) or 0))
        stats = {"concepts": len(concept_list), "sam_requests": int(sam_requests),
                 "sam_frames": int(sam_frames), "spark_calls": int(spark_calls),
                 "rechecks": int(rechecks_count),
                 "repairs": int(repair.get("repair_sam_calls", 0) or 0),
                 "privacy_checks": int(counters.get("privacy_checks", 0) or 0),
                 "coverage_calls": int(counters.get("coverage_calls", 0) or 0),
                 "floor_checks": int(counters.get("floor_checks", 0) or 0)}
        models = ["muse-spark-1.3", "sam-3.1"]
        if wonder_state["called"] and "muse-wonder-1.0" not in models:
            models.append("muse-wonder-1.0")

        result = {"run_id": run_id, "before": str(before), "after": str(after),
                  "room": room, "filmed_by": filmed_by,
                  "normalized_before": before_norm, "normalized_after": after_norm,
                  "objects": objects, "concepts": concept_list, "summaries": summaries,
                  "diff_table": summaries, "moved_verdicts": moved_verdicts,
                  "summary": written.get("summary", ""), "raw_claims": raw_claims,
                  "claims": kept, "kept_claims": kept, "dropped": dropped,
                  "annotated_images": annotated, "aliases": aliases,
                  "privacy": privacy, "coverage": coverage, "floor_check": floor_check,
                  "trend": trend_result, "intentional": intentional_list,
                  "watchlist": list(watchlist_list), "watchlist_status": watchlist_status,
                  "keyframes": keyframe_urls, "stats": stats, "models": models,
                  "latency_s": round(time.time() - start, 3),
                  "cost_usd": round(total_cost() - cost_start, 6)}
        (out / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        (out / "report.md").write_text(build_report(result), encoding="utf-8")
        result["result_dir"] = str(out); result["report"] = build_report(result)
        prog(f"Done in {result['latency_s']:.1f}s — {len(kept)} kept, {len(dropped)} dropped.")
        emit({"stage": "done", "status": "done", "run_id": run_id})
        return result
    except Exception as e:
        log.exception("pipeline run %s failed", run_id)
        emit({"stage": "error", "status": "error", "message": str(e)})
        raise

def main(argv=None):
    ap = argparse.ArgumentParser(prog="splatdiff")
    ap.add_argument("before"); ap.add_argument("after")
    ap.add_argument("--concepts", default=None, help="comma list override")
    ap.add_argument("--watchlist", default=None, help="comma list of care items that must stay put")
    ap.add_argument("--room", default="Bedroom")
    ap.add_argument("--filmed-by", default=None)
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args(argv)
    concepts = [c.strip() for c in args.concepts.split(",")] if args.concepts else None
    watchlist = [c.strip() for c in args.watchlist.split(",") if c.strip()] if args.watchlist else None
    result = run(args.before, args.after, concepts=concepts, out_dir=args.out, watchlist=watchlist,
                 room=args.room, filmed_by=args.filmed_by)
    print(f"\n{'Concept':<24} {'Change':<10} {'Risk':<8} Source")
    print("-" * 60)
    for c in result["claims"]:
        print(f"{c['concept']:<24} {c['change']:<10} {c.get('risk',''):<8} {c.get('source','')}")
    for d in result["dropped"]:
        print(f"{d.get('concept',''):<24} {d.get('change',''):<10} {'':<8} DROPPED: {d.get('reason','')}")
    if result.get("watchlist_status"):
        print("\nWatchlist:")
        for w in result["watchlist_status"]:
            print(f"  {w['concept']:<24} {w['status']:<10} risk={w['risk']}")
    print(f"\nSummary: {result.get('summary','')}")
    print(f"Saved to {result.get('result_dir','outputs/'+result['run_id'])} | cost ${result['cost_usd']:.4f} | {result['latency_s']:.1f}s")

if __name__ == "__main__":
    main()
