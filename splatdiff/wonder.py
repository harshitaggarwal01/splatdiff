"""Muse Wonder 1.0 escalation and trend analysis.

Wonder is used only where the spec calls for it:
- as an escalation judge when Muse Spark's moved verdict is uncertain
  (confidence in [0.55, 0.80)), accepting the same ``input_image`` parts
  and request shape as Spark via ``POST /v1/responses``;
- as a text-only trend analyst across earlier family-feed entries for
  the same room.

All calls go through :mod:`splatdiff.meta_api`, so retries, the disk
response cache and the cost ledger behave exactly as for Spark.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2

from .meta_api import extract_text, image_part, parse_json_loose, responses, text_part, user_message
from .video_io import draw_box

log = logging.getLogger("splatdiff.wonder")

MODEL = "muse-wonder-1.0"


def _make_body(content: list, max_tokens: int = 2000, retry: bool = False) -> dict:
    body = {"model": MODEL, "input": [user_message(content)],
            "reasoning": {"effort": "low"}, "max_output_tokens": max_tokens}
    if retry:
        # Changed request hash so a cached bad/empty first response is
        # not served again for the retry.
        body["metadata"] = {"retry": "1"}
    return body


def _call_json(content: list, max_tokens: int = 2000, what: str = "wonder"):
    """Call Wonder and parse strict JSON; retry once, return None on failure."""
    last_exc: Exception | None = None
    for attempt in (0, 1):
        retry = attempt == 1
        try:
            text = extract_text(responses(_make_body(content, max_tokens=max_tokens, retry=retry)))
        except Exception as e:  # noqa: BLE001
            last_exc = e
            log.warning("%s: Wonder call failed (attempt %d/2): %s", what, attempt + 1, e)
            continue
        if not text or not str(text).strip():
            last_exc = ValueError("empty text, cannot parse JSON")
            log.warning("%s: empty text from Wonder (attempt %d/2)", what, attempt + 1)
            continue
        try:
            return parse_json_loose(text)
        except Exception as e:  # noqa: BLE001
            last_exc = e
            log.warning("%s parse failed (attempt %d/2): %s; text=%s",
                        what, attempt + 1, e, str(text)[:500])
            continue
    log.warning("%s: giving up after retries: %s", what, last_exc)
    return None


def _crop(frame_path, box, out_path):
    img = cv2.imread(str(frame_path))
    if img is None or not box:
        return None
    try:
        h, w = img.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in box]
    except Exception:  # noqa: BLE001
        return None
    pad_x, pad_y = int(0.6 * max(1, x2 - x1)), int(0.6 * max(1, y2 - y1))
    crop = img[max(0, y1 - pad_y):min(h, y2 + pad_y), max(0, x1 - pad_x):min(w, x2 + pad_x)]
    if crop.size == 0:
        return None
    cv2.imwrite(str(out_path), crop)
    return str(out_path)


def judge_moved_wonder(concept: str, before_img, after_img, before_box=None, after_box=None) -> dict | None:
    """Escalation moved-judgement with muse-wonder-1.0.

    Same question and same before/after evidence images (SAM box drawn,
    plus context crops) as :func:`splatdiff.spark.judge_moved`.
    Returns {"moved": bool, "confidence": float, "reason": str} or
    None on any failure, so the caller can keep the Spark verdict.
    """
    try:
        tmp = Path("cache") / "judge_wonder"
        tmp.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in str(concept).lower())
        bp, ap = tmp / f"{safe}_before.jpg", tmp / f"{safe}_after.jpg"
        cv2.imwrite(str(bp), draw_box(before_img, before_box, concept, (0, 165, 255)))
        cv2.imwrite(str(ap), draw_box(after_img, after_box, concept, (0, 165, 255)))
        content = [text_part(
            f"The orange box marks '{concept}' in the BEFORE frame and the AFTER frame of the same room. "
            "Camera viewpoint differs between videos, so do NOT judge by raw pixel position. Judge position relative to "
            "surrounding furniture and room landmarks. Also shown are context crops. Return STRICT JSON only: "
            '{"moved": true, "confidence": 0.0, "reason": "short reason"} with confidence in 0..1.'),
            text_part("BEFORE full frame"), image_part(str(bp)),
            text_part("AFTER full frame"), image_part(str(ap))]
        for label, src, box, name in (("BEFORE crop", str(bp), before_box, "b_crop"),
                                      ("AFTER crop", str(ap), after_box, "a_crop")):
            crop_path = _crop(src, box, tmp / f"{safe}_{name}.jpg")
            if crop_path:
                content.append(text_part(label))
                content.append(image_part(crop_path))
        d = _call_json(content, max_tokens=2000, what=f"judge_moved_wonder {concept}")
        if not isinstance(d, dict):
            return None
        try:
            conf = float(d.get("confidence", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            conf = 0.0
        return {"moved": bool(d.get("moved")),
                "confidence": max(0.0, min(1.0, conf)),
                "reason": str(d.get("reason", "") or "")}
    except Exception as e:  # noqa: BLE001
        log.warning("judge_moved_wonder failed for %s: %s", concept, e)
        return None


def analyse_trend(feed_entries, kept_claims, watchlist_status) -> dict | None:
    """Text-only trend across earlier visits, with muse-wonder-1.0.

    ``feed_entries`` are earlier family-feed entries for the same room,
    newest first (max 20, enforced by the caller and re-enforced here).
    Returns {"trend": str|None, "repeat_items": [{"concept", "times",
    "of_checks"}]} or None on any failure (caller skips silently).
    """
    try:
        entries = [e for e in (feed_entries or []) if isinstance(e, dict)][:20]
        payload = {"earlier_checks_newest_first": entries,
                   "this_run_kept_claims": kept_claims or [],
                   "this_run_watchlist_status": watchlist_status or []}
        content = [text_part(
            "You are summarising the trend across repeated 'Second Look' room checks for an elderly parent's room, "
            "for a family caregiver. Below are earlier family-feed entries for the SAME room (newest first, at most "
            "20), plus this run's kept (SAM-grounded) claims and watchlist status. Look for items that keep changing "
            "or keep being flagged across checks. Return STRICT JSON only, no markdown: "
            '{"trend": "one plain sentence or null", "repeat_items": [{"concept": "str", "times": 0, "of_checks": 0}]} '
            "where 'trend' is ONE plain sentence describing the overall trend across visits (or null if there is no "
            "meaningful pattern), and 'repeat_items' lists concepts flagged in at least 2 checks, with 'times' = in "
            "how many of those checks the concept was flagged and 'of_checks' = the total number of checks considered "
            "(earlier entries plus this run). Do not invent items that never appear in the data.\nDATA:\n"
            + json.dumps(payload, default=str))]
        d = _call_json(content, max_tokens=2000, what="analyse_trend")
        if not isinstance(d, dict):
            return None
        trend = d.get("trend")
        if trend is not None:
            trend = str(trend).strip() or None
        repeat_items = []
        raw_items = d.get("repeat_items") or []
        if isinstance(raw_items, (list, tuple)):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                concept = " ".join(str(item.get("concept", "") or "").strip().lower().split())
                if not concept:
                    continue
                try:
                    times = int(item.get("times", 0) or 0)
                except Exception:  # noqa: BLE001
                    times = 0
                try:
                    of_checks = int(item.get("of_checks", 0) or 0)
                except Exception:  # noqa: BLE001
                    of_checks = 0
                repeat_items.append({"concept": concept, "times": times, "of_checks": of_checks})
        return {"trend": trend, "repeat_items": repeat_items}
    except Exception as e:  # noqa: BLE001
        log.warning("analyse_trend failed: %s", e)
        return None


# Friendly aliases.
trend_analysis = analyse_trend
analyze_trend = analyse_trend
judge_moved = judge_moved_wonder
