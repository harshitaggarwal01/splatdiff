"""End-to-end SplatDiff pipeline + CLI."""
from __future__ import annotations
import argparse, copy, json, logging, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import cv2
from . import diff as diffmod
from .meta_api import total_cost
from .sam import track_concept, segment_image
from .spark import list_objects, judge_moved, write_claims
from .video_io import normalize_video, extract_keyframes, read_frame, draw_box

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("splatdiff.pipeline")
COLORS = {"added": (0, 200, 0), "removed": (0, 0, 220), "moved": (0, 140, 255)}

def _safe(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(s).lower()).strip("_")

def build_report(result: dict) -> str:
    lines = ["# SplatDiff — grounded change report", "", result.get("summary") or "", "", "## Kept claims (SAM-grounded)"]
    if not result.get("claims"):
        lines.append("- No grounded changes found.")
    for c in result.get("claims", []):
        ev = c.get("evidence", {})
        lines.append(f"- **{c['concept']} — {c['change']}** ({c.get('source','')}) : {c.get('explanation','')} "
                     f"[frames before={ev.get('frames_before')} after={ev.get('frames_after')}, "
                     f"conf before={ev.get('confidence_before',0):.2f} after={ev.get('confidence_after',0):.2f}]")
        if c.get("safety_note"):
            lines.append(f"  - Safety note: {c['safety_note']}")
    lines += ["", "## Dropped claims (not supported by SAM)"]
    if not result.get("dropped"):
        lines.append("- None.")
    for d in result.get("dropped", []):
        lines.append(f"- ~~{d.get('concept','')} — {d.get('change','')}~~ — dropped: {d.get('reason','')}")
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

def _run_image_rechecks(summaries: dict, before_keyframes: list, after_keyframes: list, prog) -> None:
    """SAM image re-check for added/removed concepts on the 'absent' side.

    Mutates summaries: stores per-concept 'recheck' info and flips the
    label to 'present_both' when a keyframe detection overturns the
    video-tracking label. Original label is kept as 'original_label'.
    """
    candidates = [(c, s) for c, s in summaries.items() if s.get("label") in ("added", "removed")]
    if not candidates:
        return
    prog(f"SAM image re-check for {len(candidates)} added/removed concept(s)…")
    tasks = []
    absent_side = {}
    for concept, s in candidates:
        # added -> supposedly absent in BEFORE; removed -> absent in AFTER
        side = "before" if s["label"] == "added" else "after"
        absent_side[concept] = side
        keyframes = before_keyframes if side == "before" else after_keyframes
        for idx, kf_path in enumerate(keyframes or []):
            tasks.append((concept, side, idx, kf_path))
    def _job(t):
        concept, side, idx, kf_path = t
        try:
            parsed = segment_image(kf_path, concept)
        except Exception as e:
            log.warning("SAM image re-check failed for %s keyframe %s: %s", concept, idx, e)
            return concept, side, idx, None
        det = _best_detection(parsed)
        if det is None:
            return concept, side, idx, None
        return concept, side, idx, {"video": side, "keyframe_index": idx,
                                    "box": det["box"], "c": det["c"]}
    found: dict[str, dict] = {}
    if tasks:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for concept, side, idx, det in ex.map(_job, tasks):
                if det is not None and (concept not in found or det["c"] > found[concept]["c"]):
                    found[concept] = det
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

def run(before, after, concepts=None, out_dir="outputs", progress=None) -> dict:
    def prog(msg: str):
        log.info(msg)
        if progress:
            progress(msg)
    start, cost_start = time.time(), total_cost()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(out_dir) / run_id; out.mkdir(parents=True, exist_ok=True)
    prog("Normalising videos (ffmpeg, 5 fps, max 30 s)…")
    before_norm, after_norm = normalize_video(before), normalize_video(after)
    prog("Extracting keyframes…")
    bf = extract_keyframes(before_norm, 6, out / "keyframes_before")
    af = extract_keyframes(after_norm, 6, out / "keyframes_after")
    prog("Inventorying objects with Muse Spark 1.3…")
    objects = list_objects(bf, af, concepts=concepts)
    concept_list = [o["concept"] for o in objects]
    prog(f"Concepts ({len(concept_list)}): {', '.join(concept_list) or 'none'}")
    prog("Tracking concepts with SAM 3.1 (concurrent)…")
    tasks = [(c, "before", before_norm) for c in concept_list] + [(c, "after", after_norm) for c in concept_list]
    before_tracks, after_tracks = {}, {}
    def _job(t):
        concept, side, path = t
        try:
            return concept, side, track_concept(path, concept)
        except Exception as e:
            log.exception("SAM failed for %s/%s", concept, side); return concept, side, {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for concept, side, parsed in ex.map(_job, tasks):
            (before_tracks if side == "before" else after_tracks)[concept] = {int(k): v for k, v in parsed.items()}
    summaries = diffmod.summarize_tracks(before_tracks, after_tracks)
    # Snapshot of ORIGINAL video-tracking labels: the final write_claims
    # call below must still see these (not re-check-corrected labels), so
    # Spark may e.g. claim 'armchair added' and the grounding filter can
    # visibly drop it citing the re-check.
    original_summaries = copy.deepcopy(summaries)
    _run_image_rechecks(summaries, bf, af, prog)
    prog("Judging moved objects with Muse Spark 1.3…")
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
            # ex.map preserves input order, so moved_verdicts keeps the
            # same key order as the sequential version; progress is
            # reported from the main thread as each result is yielded.
            for concept, verdict in ex.map(_judge_job, judge_items):
                moved_verdicts[concept] = verdict
                try:
                    prog(f"Judged '{concept}': moved={bool(verdict.get('moved'))} "
                         f"(confidence {float(verdict.get('confidence', 0.0)):.2f})")
                except Exception:
                    prog(f"Judged '{concept}': {verdict}")
    prog("Writing grounded report with Muse Spark 1.3…")
    # Deliberately pass original (pre-recheck) summaries: raw Spark claims
    # stay separate from, and are then checked against, corrected evidence.
    written = write_claims(original_summaries, moved_verdicts)
    raw_claims = written.get("claims", [])
    kept, dropped = diffmod.grounding_filter(raw_claims, summaries, moved_verdicts)
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
    result = {"run_id": run_id, "before": str(before), "after": str(after),
              "normalized_before": before_norm, "normalized_after": after_norm,
              "objects": objects, "concepts": concept_list, "summaries": summaries,
              "diff_table": summaries, "moved_verdicts": moved_verdicts,
              "summary": written.get("summary", ""), "raw_claims": raw_claims,
              "claims": kept, "kept_claims": kept, "dropped": dropped,
              "annotated_images": annotated, "latency_s": round(time.time() - start, 3),
              "cost_usd": round(total_cost() - cost_start, 6)}
    (out / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out / "report.md").write_text(build_report(result), encoding="utf-8")
    result["result_dir"] = str(out); result["report"] = build_report(result)
    prog(f"Done in {result['latency_s']:.1f}s — {len(kept)} kept, {len(dropped)} dropped.")
    return result

def main(argv=None):
    ap = argparse.ArgumentParser(prog="splatdiff")
    ap.add_argument("before"); ap.add_argument("after")
    ap.add_argument("--concepts", default=None, help="comma list override")
    ap.add_argument("--out", default="outputs")
    args = ap.parse_args(argv)
    concepts = [c.strip() for c in args.concepts.split(",")] if args.concepts else None
    result = run(args.before, args.after, concepts=concepts, out_dir=args.out)
    print(f"\n{'Concept':<24} {'Change':<10} Source")
    print("-" * 50)
    for c in result["claims"]:
        print(f"{c['concept']:<24} {c['change']:<10} {c.get('source','')}")
    for d in result["dropped"]:
        print(f"{d.get('concept',''):<24} {d.get('change',''):<10} DROPPED: {d.get('reason','')}")
    print(f"\nSummary: {result.get('summary','')}")
    print(f"Saved to {result.get('result_dir','outputs/'+result['run_id'])} | cost ${result['cost_usd']:.4f} | {result['latency_s']:.1f}s")

if __name__ == "__main__":
    main()
