"""V5 family agent — words only.

This module NEVER reads or sends images, image URLs, video paths or
transcripts. Its context is built exclusively from:

* the newest 30 family-feed entries (cache/feed.jsonl, or the server's
  in-memory feed list passed in by server.py),
* the rooms list (same data as ``GET /api/rooms``, passed in by server.py),
* a text-only digest of the 3 newest pipeline results in ``outputs/``.

Any dictionary key containing 'image', 'url', 'path', 'keyframe' or
'transcript' is stripped recursively before anything is sent to the model.
All model calls go through ``splatdiff.meta_api.responses`` (Muse Spark 1.3),
so they are disk-cached, retried and entered in the cost ledger exactly
like every other Spark call in the project.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from splatdiff import meta_api

log = logging.getLogger("splatdiff.agent")

MODEL = "muse-spark-1.3"
ROOT = Path(__file__).resolve().parent.parent
FEED_PATH = ROOT / "cache" / "feed.jsonl"
OUTPUTS_DIR = ROOT / "outputs"

_BAD_KEY_PARTS = ("image", "url", "path", "keyframe", "transcript")

_MAX_QUESTION_CHARS = 500
_MAX_NAME_CHARS = 100
_MAX_ANSWER_WORDS = 120
_MAX_UPDATE_WORDS = 110


# ---------------------------------------------------------------------------
# Sanitising helpers (words only)
# ---------------------------------------------------------------------------

def _is_bad_key(key) -> bool:
    low = str(key).lower()
    return any(part in low for part in _BAD_KEY_PARTS)


def strip_keys(obj):
    """Return a copy of *obj* with any risky key removed, recursively.

    A key is removed when its lowercase name contains 'image', 'url',
    'path', 'keyframe' or 'transcript'. Lists/tuples and nested dicts
    are walked. Scalars are returned unchanged.
    """
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if _is_bad_key(key):
                continue
            out[key] = strip_keys(value)
        return out
    if isinstance(obj, (list, tuple)):
        return [strip_keys(v) for v in obj]
    return obj


def _safe_str(value, limit: int = 500):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _truncate_words(text: str, max_words: int) -> str:
    words = str(text or "").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(",;:") + "."


# ---------------------------------------------------------------------------
# Loading feed / results (text only)
# ---------------------------------------------------------------------------

def _load_feed_from_disk() -> list:
    entries = []
    try:
        if FEED_PATH.is_file():
            for line in FEED_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    entries.append(obj)
    except Exception as exc:  # noqa: BLE001
        log.warning("agent: could not read feed file: %s", exc)
    return entries


def _load_recent_results(limit: int = 3) -> list:
    results = []
    try:
        if OUTPUTS_DIR.is_dir():
            files = sorted(
                OUTPUTS_DIR.glob("*/result.json"),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            )
            for path in files:
                if len(results) >= limit:
                    break
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(data, dict):
                    results.append(data)
    except Exception as exc:  # noqa: BLE001
        log.warning("agent: could not read recent results: %s", exc)
    return results


def _parse_dt(value):
    if isinstance(value, str) and value.strip():
        txt = value.strip()
        try:
            dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.astimezone()
        except Exception:
            pass
        for fmt in ("%Y%m%d_%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(txt[:19], fmt).astimezone()
            except Exception:
                continue
        # run_id prefix like 20261104_191500
        head = txt[:15]
        try:
            return datetime.strptime(head, "%Y%m%d_%H%M%S").astimezone()
        except Exception:
            return None
    return None


def _citation(room, dt) -> str | None:
    if dt is None:
        return None
    try:
        when = dt.strftime("%b %-d %-I:%M %p")
    except Exception:
        when = dt.strftime("%b %d %I:%M %p").replace(" 0", " ")
    return f"[{room or 'Room'}, {when}]"


# ---------------------------------------------------------------------------
# Text digest of one pipeline result
# ---------------------------------------------------------------------------

def _claim_concept(claim: dict):
    return _safe_str(claim.get("concept") or claim.get("name") or claim.get("item"), 120)


def _intentional_quote(claim: dict):
    """Extract an intentional quote from a claim, in any plausible shape."""
    for key in ("intentional_quote", "quote"):
        val = _safe_str(claim.get(key), 300)
        if val:
            return val
    intentional = claim.get("intentional")
    if isinstance(intentional, str) and intentional.strip():
        return _safe_str(intentional, 300)
    if isinstance(intentional, dict):
        for key in ("quote", "text", "reason", "note"):
            val = _safe_str(intentional.get(key), 300)
            if val:
                return val
    return None


def _watchlist_entries(result: dict) -> list:
    entries = []
    if not isinstance(result, dict):
        return entries
    for key in ("watchlist_results", "watchlist_status", "watched_items", "watchlist_items"):
        val = result.get(key)
        if isinstance(val, list):
            entries.extend([v for v in val if isinstance(v, dict)])
        elif isinstance(val, dict):
            entries.extend([v for v in val.values() if isinstance(v, dict)])
    val = result.get("watchlist")
    if isinstance(val, list):
        for v in val:
            if isinstance(v, dict):
                entries.append(v)
            elif isinstance(v, str) and v.strip():
                entries.append({"concept": v.strip(), "status": None, "note": None})
    elif isinstance(val, dict):
        for key in ("items", "results", "entries"):
            sub = val.get(key)
            if isinstance(sub, list):
                entries.extend([v for v in sub if isinstance(v, dict)])
    return entries


def digest_result(result: dict) -> dict:
    """Text-only digest of one pipeline result (no images/paths/transcripts)."""
    if not isinstance(result, dict):
        return {}
    run_id = _safe_str(result.get("run_id"), 80)
    room = _safe_str(result.get("room"), 80) or "Bedroom"
    date_val = None
    for key in ("ts", "date", "created_at", "timestamp"):
        date_val = _safe_str(result.get(key), 80)
        if date_val:
            break
    if not date_val:
        date_val = run_id
    dt = _parse_dt(date_val) or _parse_dt(run_id)

    coverage_in = result.get("coverage") if isinstance(result.get("coverage"), dict) else {}
    coverage = {
        "ok": coverage_in.get("ok"),
        "score": coverage_in.get("score"),
        "retake_tip": _safe_str(coverage_in.get("retake_tip"), 300),
    }

    privacy_in = result.get("privacy") if isinstance(result.get("privacy"), dict) else {}
    privacy = {
        "people_blurred": privacy_in.get("people_blurred", privacy_in.get("people", 0)),
        "documents_blurred": privacy_in.get("documents_blurred", privacy_in.get("documents", 0)),
        "frames_checked": privacy_in.get("frames_checked", 0),
    }

    trend_in = result.get("trend")
    if isinstance(trend_in, dict):
        trend = _safe_str(trend_in.get("trend") or trend_in.get("text") or trend_in.get("summary"), 300)
    elif isinstance(trend_in, str):
        trend = _safe_str(trend_in, 300)
    else:
        trend = None

    kept_claims = []
    raw_kept = result.get("kept_claims") or result.get("claims") or []
    if isinstance(raw_kept, list):
        for claim in raw_kept:
            if not isinstance(claim, dict):
                continue
            entry = {
                "concept": _claim_concept(claim),
                "change": _safe_str(claim.get("change") or claim.get("label"), 60),
                "risk": _safe_str(claim.get("risk"), 40),
                "explanation": _safe_str(claim.get("explanation") or claim.get("reason"), 400),
            }
            quote = _intentional_quote(claim)
            if quote:
                entry["intentional_quote"] = quote
            kept_claims.append(entry)

    dropped_claims = []
    raw_dropped = result.get("dropped") or result.get("dropped_claims") or []
    if isinstance(raw_dropped, list):
        for claim in raw_dropped:
            if not isinstance(claim, dict):
                continue
            dropped_claims.append({
                "concept": _claim_concept(claim),
                "change": _safe_str(claim.get("change") or claim.get("label"), 60),
                "reason": _safe_str(claim.get("reason"), 400),
            })

    watchlist_status = []
    for entry in _watchlist_entries(result):
        watchlist_status.append({
            "concept": _safe_str(entry.get("concept") or entry.get("name") or entry.get("item"), 120),
            "status": _safe_str(entry.get("status") or entry.get("state"), 60),
            "note": _safe_str(entry.get("note") or entry.get("reason") or entry.get("explanation"), 300),
        })

    digest = {
        "run_id": run_id,
        "room": room,
        "filmed_by": _safe_str(result.get("filmed_by"), 80),
        "date": date_val,
        "ts": date_val,
        "citation": _citation(room, dt),
        "summary": _safe_str(result.get("summary"), 600),
        "coverage": coverage,
        "privacy": privacy,
        "trend": trend,
        "kept_claims": kept_claims,
        "dropped_claims": dropped_claims,
        "watchlist_status": watchlist_status,
    }
    return strip_keys(digest)


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------

def build_context(feed_entries=None, rooms=None) -> dict:
    """Build the words-only context for the family agent.

    ``feed_entries`` is the server's existing feed list (chronological,
    oldest first — as kept in ``server.FEED`` / cache/feed.jsonl). When it
    is not supplied, the feed is read from ``cache/feed.jsonl``.
    ``rooms`` is the same data as ``GET /api/rooms`` (the server passes
    its computed list); when not supplied it is derived, minimally, from
    the feed so this function also works standalone.

    Returns {"feed": newest 30 entries, "rooms": [...],
    "recent_checks": [digest, digest, digest]} with every key containing
    'image'/'url'/'path'/'keyframe'/'transcript' stripped recursively.
    """
    if feed_entries is None:
        feed = _load_feed_from_disk()
    else:
        feed = [e for e in feed_entries if isinstance(e, dict)]
    newest_feed = list(reversed(feed[-30:]))

    if rooms is None:
        # Standalone fallback: one row per room seen in the feed.
        seen = {}
        for entry in feed:
            room = _safe_str(entry.get("room"), 80)
            if room and room not in seen:
                seen[room] = {"room": room, "last_check": None, "due": True}
        rooms_data = sorted(seen.values(), key=lambda r: str(r["room"]).lower())
    else:
        rooms_data = rooms if isinstance(rooms, list) else []

    recent_checks = [digest_result(r) for r in _load_recent_results(limit=3)]

    context = {
        "feed": newest_feed,
        "rooms": rooms_data,
        "recent_checks": recent_checks,
    }
    return strip_keys(context)


def _source_lookup(context: dict) -> dict:
    """run_id -> {"run_id", "room", "ts"} from the context (checks + feed)."""
    lookup = {}
    for digest in (context or {}).get("recent_checks") or []:
        if not isinstance(digest, dict):
            continue
        run_id = digest.get("run_id")
        if run_id and run_id not in lookup:
            lookup[str(run_id)] = {
                "run_id": str(run_id),
                "room": digest.get("room"),
                "ts": digest.get("ts") or digest.get("date"),
            }
    for entry in (context or {}).get("feed") or []:
        if not isinstance(entry, dict):
            continue
        run_id = entry.get("run_id") or entry.get("id")
        if run_id and str(run_id) not in lookup:
            lookup[str(run_id)] = {
                "run_id": str(run_id),
                "room": entry.get("room"),
                "ts": entry.get("ts"),
            }
    return lookup


# ---------------------------------------------------------------------------
# Muse Spark calls (via meta_api.responses -> cached + cost-ledgered)
# ---------------------------------------------------------------------------

def _spark_call(prompt: str, max_output_tokens: int) -> tuple[str, float]:
    body = {
        "model": MODEL,
        "input": [meta_api.user_message([meta_api.text_part(prompt)])],
        "reasoning": {"effort": "low"},
        "max_output_tokens": int(max_output_tokens),
    }
    started = time.time()
    resp = meta_api.responses(body)
    text = meta_api.extract_text(resp).strip()
    if not text:
        # Reasoning can use up the budget on a large records context; retry once with
        # more room. The metadata tag changes the cache key so the empty reply isn't reused.
        body["max_output_tokens"] = max(int(max_output_tokens) * 3, 4000)
        body["metadata"] = {"retry": "1"}
        resp = meta_api.responses(body)
        text = meta_api.extract_text(resp).strip()
    latency = time.time() - started
    return text, round(latency, 3)


def ask(question: str, context: dict | None = None) -> dict:
    """Answer a family question from the records only.

    Returns {"answer", "sources": [{"run_id","room","ts"}], "model",
    "latency_s"}. Raises ValueError for an empty / over-long question.
    """
    q = str(question or "").strip()
    if not q:
        raise ValueError("question is required")
    if len(q) > _MAX_QUESTION_CHARS:
        raise ValueError(f"question must be at most {_MAX_QUESTION_CHARS} characters")
    if context is None:
        context = build_context()
    context = strip_keys(context)
    lookup = _source_lookup(context)

    prompt = (
        "You are the family assistant for Second Look, which checks on Dad's rooms "
        "from short walkthrough videos. You are given RECORDS ONLY (words, never pictures).\n\n"
        "RULES — follow all of them:\n"
        "1. Answer ONLY from the records below. Never invent, guess or use outside knowledge.\n"
        "2. If the records don't say, your answer must include the exact sentence "
        "\"The checks don't show that yet\" and suggest re-filming the room.\n"
        "3. Cite the checks you use inline, like [Bedroom, Nov 4 7:15 PM], using each "
        "check's room and date (recent_checks have a ready-made 'citation' field — copy it).\n"
        "4. Use plain, warm language a family member would use.\n"
        "5. Never give medical advice.\n"
        "6. Never claim something is reachable, safe or unsafe beyond what was actually seen "
        "in a check; only report what the records say changed or was seen. Say 'seen where it "
        "was' (never 'where it should be', 'fine' or 'safe') and note that a check shows "
        "presence, not whether Dad can reach it.\n"
        "7. Keep the answer to at most 120 words.\n"
        "8. Return STRICT JSON only, no markdown fences: "
        "{\"answer\": \"<your answer>\", \"source_run_ids\": [\"<run_id of each check cited>\"]}. "
        "source_run_ids must only contain run_id values that appear in the records.\n\n"
        f"RECORDS (JSON):\n{json.dumps(context, ensure_ascii=False, default=str)}\n\n"
        f"QUESTION: {q}"
    )
    text, latency = _spark_call(prompt, max_output_tokens=2500)
    log.info("agent ask done (%.2fs): %s", latency, q[:80])

    answer = ""
    source_ids: list = []
    try:
        parsed = meta_api.parse_json_loose(text)
        if isinstance(parsed, dict):
            answer = str(parsed.get("answer") or "").strip()
            raw_ids = parsed.get("source_run_ids") or parsed.get("sources") or []
            if isinstance(raw_ids, list):
                for item in raw_ids:
                    if isinstance(item, dict):
                        item = item.get("run_id") or item.get("id")
                    if item is not None and str(item).strip():
                        source_ids.append(str(item).strip())
    except Exception:
        answer = text
    if not answer:
        answer = text or "The checks don't show that yet. It may help to re-film the room."
    answer = _truncate_words(answer, _MAX_ANSWER_WORDS)

    sources = []
    seen = set()
    for run_id in source_ids:
        if run_id in seen:
            continue
        seen.add(run_id)
        src = lookup.get(run_id)
        if src is not None:
            sources.append(src)
    return {"answer": answer, "sources": sources, "model": MODEL, "latency_s": latency}


_UPDATE_RULES = {
    "nearby": (
        "Write for the family member who lives NEARBY and will visit next. "
        "Give practical to-dos for the next visit, based only on the records. "
        "Tell them to ask Dad first, and to put things back together with him "
        "(not for him) where the records mention a change. Warm and concrete."
    ),
    "far": (
        "Write for the family member who lives FAR away. Say what changed, who "
        "is handling it (use filmed_by / the nearby person if the records say), "
        "and what, if anything, they can do from afar (for example: call Dad, "
        "or thank the person nearby). Do not alarm them; be calm and clear."
    ),
    "dad": (
        "Write directly TO Dad, in the second person (\"you\"). Be respectful "
        "and short. Use NO risk words (never say risk, danger, hazard, safety, "
        "fall or unsafe). Ask for his view on any change, in the spirit of: "
        "\"Did you move the lamp to read by your chair? If you like it there, "
        "we'll keep it that way.\" Never mention cameras, filming, videos, "
        "checks, AI or models."
    ),
}


def make_update(kind: str, name: str | None = None, context: dict | None = None) -> dict:
    """Write a short plain-text update for 'nearby' | 'far' | 'dad'.

    Returns {"text", "model", "latency_s"}. Raises ValueError for an
    unknown audience or an over-long name.
    """
    audience = str(kind or "").strip().lower()
    if audience not in _UPDATE_RULES:
        raise ValueError("for must be one of: nearby, far, dad")
    recipient = None
    if name is not None:
        recipient = str(name).strip() or None
        if recipient and len(recipient) > _MAX_NAME_CHARS:
            raise ValueError(f"name must be at most {_MAX_NAME_CHARS} characters")
    if context is None:
        context = build_context()
    context = strip_keys(context)

    name_line = ""
    if recipient:
        if audience == "dad":
            name_line = f"Dad's name is {recipient}; you may greet him by name.\n"
        else:
            name_line = f"The reader's name is {recipient}; you may use it naturally.\n"

    prompt = (
        "You write short family updates for Second Look, which checks on Dad's rooms. "
        "You are given RECORDS ONLY (words, never pictures).\n\n"
        f"AUDIENCE: {_UPDATE_RULES[audience]}\n"
        f"{name_line}"
        "RULES — follow all of them:\n"
        "1. Use ONLY what the records say. Never invent changes, people or plans.\n"
        "2. If the records show no changes at all, simply say things look as they were.\n"
        "3. Plain, warm language. No medical advice. Never claim something is reachable, "
        "safe or unsafe beyond what was seen.\n"
        "4. At most 110 words. Plain text only — no JSON, no markdown, no bullet symbols "
        "unless a short list genuinely helps (nearby audience only).\n\n"
        f"RECORDS (JSON):\n{json.dumps(context, ensure_ascii=False, default=str)}"
    )
    text, latency = _spark_call(prompt, max_output_tokens=2500)
    log.info("agent update for=%s done (%.2fs)", audience, latency)

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        # If the model still returned JSON, try to pull a text field out.
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                cleaned = str(parsed.get("text") or parsed.get("answer") or cleaned).strip()
        except Exception:
            pass
    cleaned = _truncate_words(cleaned, _MAX_UPDATE_WORDS)
    return {"text": cleaned, "model": MODEL, "latency_s": latency}
