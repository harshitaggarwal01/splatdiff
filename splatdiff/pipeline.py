"""End-to-end SplatDiff pipeline + CLI."""
from __future__ import annotations
import argparse, copy, json, logging, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import cv2
from . import diff as diffmod
from .meta_api import total_cost
from .sam import track_concept, segment_image
from .spark import list_objects, judge_moved, write_claims, suggest_aliases
from .video_io import normalize_video, extract_keyframes, read_frame, draw_box

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("splatdiff.pipeline")
COLORS = {"added": (0, 200, 0), "removed": (0, 0, 220), "moved": (0, 140, 255)}
MAX_CONCEPTS = 16
MAX_REPAIR_CONCEPTS = 6
REPAIR_MIN_CONF = 0.5

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
    lines = ["# SplatDiff — grounded change report", "", result.get("summary") or "", "", "## Kept claims (SAM-grounded)"]
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
        ev = c.get("evidence", {})
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
        if c.get("safety_note"):
            lines.append(f"  - Safety note: {c['safety_note']}")
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

def _run_vocab_repair(summaries: dict, watchlist_list: list, before_norm, after_norm,
                      before_keyframes: list, after_keyframes: list, prog, emit=None,
                      before_tracks: dict | None = None, after_tracks: dict | None = None) -> dict:
    """Vocabulary repair for concepts SAM found in neither video.

    For each 'not_found' concept (watchlist items first, max 6): ask
    Spark for alias phrases, test each alias with SAM image segmentation
    on up to 3 BEFORE + 3 AFTER keyframes (concurrently), and if an alias
    reaches c >= 0.5 re-run SAM video tracking under the alias. The
    recomputed summary stays keyed under the ORIGINAL concept name, with
    summaries[concept]['alias'] set. Skipped entirely (no events) when
    nothing is not_found.

    Returns dict with keys: aliases, repair_sam_calls, repaired,
    spark_calls, sam_requests, sam_frames. ``repair_sam_calls`` counts
    every SAM call made by this stage (image tests + video re-runs);
    ``sam_requests``/``sam_frames`` count only the video re-runs so the
    caller can fold them into the run totals.
    """
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
    # Watchlist items first (in watchlist order), then the rest in
    # summary order; cap at MAX_REPAIR_CONCEPTS.
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
        # (1) Spark alias suggestions.
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

        # (2) Test each alias on keyframes, concurrently.
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
            # Highest confidence wins; ties keep Spark's earlier suggestion.
            for alias in tried:
                cval = per_alias_best.get(alias, 0.0)
                if cval >= REPAIR_MIN_CONF and cval > best_c:
                    best_alias, best_c = alias, float(cval)

        # (3) Re-track under the winning alias, keyed by original concept.
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
    """SAM image re-check for added/removed concepts on the 'absent' side.

    Mutates summaries: stores per-concept 'recheck' info and flips the
    label to 'present_both' when a keyframe detection overturns the
    video-tracking label. Original label is kept as 'original_label'.

    Emits recheck start/progress/done events (if ``emit`` is given) as
    each concept finishes. Returns the number of SAM image requests made.
    """
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
        # added -> supposedly absent in BEFORE; removed -> absent in AFTER
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
    """Return (frame_ndarray, box) for the moved judge for one side.

    If the image re-check found this concept on this (supposedly absent)
    side, use that keyframe and its box; otherwise use the best tracked
    video frame.
    """
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
        return (f"{c} is no longer where it was - check it is within reach of the bed/chair "
                f"and find it before it is needed.")
    if status == "moved":
        return (f"{c} has moved from where it was - check it is within reach of the bed/chair "
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
    """Derive per-watchlist-item status from SAM labels + moved verdicts."""
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
                # 'moved verdict kept' = a kept moved claim for this concept;
                # equivalently a true verdict at/above the grounding threshold.
                v = moved_verdicts.get(key) or {}
                try:
                    v_conf = float(v.get("confidence", 0.0) or 0.0)
                except Exception:
                    v_conf = 0.0
                verdict_kept = bool(v.get("moved")) and v_conf >= diffmod.MOVED_MIN_CONF
                status = "moved" if (_norm_concept(key) in moved_kept or verdict_kept) else "in_place"
            else:  # not_found
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

def run(before, after, concepts=None, out_dir="outputs", progress=None, on_event=None, watchlist=None) -> dict:
    def prog(msg: str):
        log.info(msg)
        if progress:
            progress(msg)

    start, cost_start = time.time(), total_cost()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    watchlist_list = _clean_list(watchlist)
    event_lock = threading.Lock()

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

        # 3. Inventory (watchlist always tracked: prepended, capped)
        emit({"stage": "inventory", "status": "start", "model": "muse-spark-1.3",
              "concepts": [], "objects": []})
        prog("Inventorying objects with Muse Spark 1.3…")
        inventory_called = not bool(concepts)
        objects = list_objects(bf, af, concepts=concepts)
        inventory_concepts = [o["concept"] for o in objects if isinstance(o, dict) and o.get("concept")]
        concept_list = _dedupe_prepend(watchlist_list, inventory_concepts, cap=MAX_CONCEPTS)
        # Ensure watchlist items are represented in `objects` too.
        known = {_norm_concept(o.get("concept", "")) for o in objects if isinstance(o, dict)}
        extra_objects = [{"concept": c, "where_before": "", "where_after": "",
                          "suspected_change": "unchanged"}
                         for c in concept_list if _norm_concept(c) not in known]
        if extra_objects:
            objects = extra_objects + list(objects)
        emit({"stage": "inventory", "status": "done", "model": "muse-spark-1.3",
              "concepts": list(concept_list), "objects": objects})
        prog(f"Concepts ({len(concept_list)}): {', '.join(concept_list) or 'none'}")

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

        # 4b. Vocabulary repair: aliases for not_found concepts, BEFORE
        # the image re-check (which only handles added/removed). Entirely
        # skipped — no events — when nothing is not_found.
        repair = _run_vocab_repair(summaries, watchlist_list, before_norm, after_norm,
                                   bf, af, prog, emit=emit,
                                   before_tracks=before_tracks, after_tracks=after_tracks)
        aliases = repair.get("aliases", {}) or {}
        sam_requests += int(repair.get("sam_requests", 0) or 0)
        sam_frames += int(repair.get("sam_frames", 0) or 0)

        # Snapshot of ORIGINAL video-tracking labels: the final write_claims
        # call below must still see these (not re-check-corrected labels), so
        # Spark may e.g. claim 'armchair added' and the grounding filter can
        # visibly drop it citing the re-check. Taken after repair so repaired
        # concepts are reported under their (alias-derived) labels, still
        # keyed by the original concept name.
        original_summaries = copy.deepcopy(summaries)

        # 5. SAM image re-checks (emits its own start/progress/done events)
        recheck_calls = _run_image_rechecks(summaries, bf, af, prog, emit=emit)
        rechecks_count = sum(1 for s in summaries.values() if (s.get("recheck") or {}).get("checked"))

        # 6. Moved judge (concurrent; progress as each future completes)
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
                return concept, verdict
            except Exception as e:
                log.exception("judge_moved failed %s", concept)
                return concept, {"moved": False, "confidence": 0.0, "reason": str(e)}
            finally:
                # judge temp files are per-concept, so concurrent cleanup is safe.
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
                    prog(f"Judged '{concept}': moved={bool(verdict.get('moved'))} (confidence {v_conf:.2f})")
                    emit({"stage": "judge", "status": "progress", "concept": concept,
                          "moved": bool(verdict.get("moved")), "confidence": v_conf,
                          "reason": str(verdict.get("reason", ""))})
        emit({"stage": "judge", "status": "done", "concept": "", "moved": False,
              "confidence": 0.0, "reason": ""})

        # 7. Final Spark report
        emit({"stage": "report", "status": "start", "model": "muse-spark-1.3", "raw_claims": 0})
        prog("Writing grounded report with Muse Spark 1.3…")
        # Deliberately pass original (pre-recheck) summaries: raw Spark claims
        # stay separate from, and are then checked against, corrected evidence.
        written = write_claims(original_summaries, moved_verdicts, watchlist=watchlist_list)
        raw_claims = written.get("claims", [])
        emit({"stage": "report", "status": "done", "model": "muse-spark-1.3",
              "raw_claims": len(raw_claims)})

        # 8. Grounding filter (carries risk/risk_reason through)
        kept, dropped = diffmod.grounding_filter(raw_claims, summaries, moved_verdicts,
                                                 watchlist=watchlist_list)
        emit({"stage": "filter", "status": "done", "kept": len(kept), "dropped": len(dropped)})

        # Repaired concepts: explanations/evidence must say what SAM
        # actually tracked them as, whoever authored the claim.
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
                    # Annotate the re-check keyframe that overturned the label.
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
                p = out / f"{side}_{_safe(concept)}.jpg"
                cv2.imwrite(str(p), draw_box(frame, summ["best_box"], label_text, color))
                annotated.append(str(p))

        # Evidence images (annotated frames) on every kept + dropped claim.
        for claim in list(kept) + list(dropped):
            claim["images"] = _images_for(str(claim.get("concept", "")))
            claim.setdefault("risk", "medium")
            claim.setdefault("risk_reason", "")

        watchlist_status = _build_watchlist_status(watchlist_list, summaries, kept,
                                                   moved_verdicts, _images_for)

        spark_calls = (1 if inventory_called else 0) + len(judge_items) + 1 + int(repair.get("spark_calls", 0) or 0)
        stats = {"concepts": len(concept_list), "sam_requests": int(sam_requests),
                 "sam_frames": int(sam_frames), "spark_calls": int(spark_calls),
                 "rechecks": int(rechecks_count),
                 "repairs": int(repair.get("repair_sam_calls", 0) or 0)}
        models = ["muse-spark-1.3", "sam-3.1"]

        result = {"run_id": run_id, "before": str(before), "after": str(after),
                  "normalized_before": before_norm, "normalized_after": after_norm,
                  "objects": objects, "concepts": concept_list, "summaries": summaries,
                  "diff_table": summaries, "moved_verdicts": moved_verdicts,
                  "summary": written.get("summary", ""), "raw_claims": raw_claims,
                  "claims": kept, "kept_claims": kept, "dropped": dropped,
                  "annotated_images": annotated, "aliases": aliases,
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
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args(argv)
    concepts = [c.strip() for c in args.concepts.split(",")] if args.concepts else None
    watchlist = [c.strip() for c in args.watchlist.split(",") if c.strip()] if args.watchlist else None
    result = run(args.before, args.after, concepts=concepts, out_dir=args.out, watchlist=watchlist)
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
