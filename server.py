"""SplatDiff HTTP server (FastAPI + uvicorn).

Implements the 'HTTP server' section of build_log/UI_CONTRACT.md exactly.
Run: python server.py  -> uvicorn on 127.0.0.1:$PORT (default 8000)
"""
import asyncio
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from splatdiff import pipeline
from splatdiff import voice as voice_mod

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s server: %(message)s")
log = logging.getLogger("splatdiff.server")

app = FastAPI(title="SplatDiff")

# Per-run state: run_id -> {"status", "events": list, "cond": Condition, "result"}
RUNS: dict = {}
RUNS_LOCK = threading.Lock()


def _split_csv(value: Optional[str]):
    if not value:
        return None
    items = [s.strip() for s in str(value).split(",") if s.strip()]
    return items or None


def _merge_watchlist(existing, extra):
    """Merge two watchlists, deduping case-insensitively, preserving order."""
    merged = []
    seen = set()
    for source in (existing or [], extra or []):
        for item in source:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
    return merged


def _json_safe(obj):
    return json.loads(json.dumps(obj, default=str))


def _new_state():
    return {"status": "running", "events": [], "cond": threading.Condition(), "result": None}


def _append_event(state, event):
    with state["cond"]:
        state["events"].append(event)
        state["cond"].notify_all()


def _run_pipeline(run_id: str, before: str, after: str, concepts, watchlist, narration: bool = False):
    state = RUNS[run_id]
    run_started = time.time()
    log.info("run %s start before=%s after=%s concepts=%s watchlist=%s narration=%s", run_id, before, after, concepts, watchlist, narration)

    def cb(event):
        try:
            ev = _json_safe(event) if isinstance(event, dict) else {"stage": "log", "status": "info", "message": str(event)}
        except Exception:
            ev = {"stage": "log", "status": "info", "message": str(event)}
        _append_event(state, ev)

    voice_info = None
    effective_watchlist = watchlist
    if narration:
        try:
            voice_started = time.time()
            transcribed = voice_mod.transcribe(before)
            transcript = transcribed.get("transcript", "") if isinstance(transcribed, dict) else ""
            items = voice_mod.extract_watchlist(transcript)
            effective_watchlist = _merge_watchlist(watchlist, items) or None
            voice_info = {"transcript": transcript, "items": items}
            _append_event(state, {
                "stage": "voice",
                "status": "done",
                "model": "muse-voice-transcribe-1.0",
                "transcript": transcript,
                "items": items,
                "elapsed_s": round(time.time() - run_started, 3),
                "cost_usd": 0.0,
            })
            log.info("run %s voice note done items=%s (%.2fs)", run_id, items, time.time() - voice_started)
        except Exception as exc:  # noqa: BLE001
            log.exception("run %s narration failed, continuing without it: %s", run_id, exc)
            _append_event(state, {"stage": "voice", "status": "error", "message": str(exc)})

    try:
        result = pipeline.run(before, after, concepts=concepts or None, watchlist=effective_watchlist or None, on_event=cb)
        if result is None:
            raise RuntimeError("pipeline returned no result")
        if voice_info is not None and isinstance(result, dict):
            models = result.get("models")
            if not isinstance(models, list):
                models = [models] if models else []
                result["models"] = models
            if "muse-voice-transcribe-1.0" not in models:
                models.append("muse-voice-transcribe-1.0")
            result["narration"] = {"transcript": voice_info["transcript"], "items": voice_info["items"]}
        safe_result = _json_safe(result)
        # Append full-result event BEFORE marking status done, so SSE clients get it.
        final_event = {"stage": "result", "status": "done", "result": safe_result}
        with state["cond"]:
            state["events"].append(final_event)
            state["cond"].notify_all()
            state["result"] = safe_result
            state["status"] = "done"
        log.info("run %s done pipeline_run_id=%s", run_id, safe_result.get("run_id") if isinstance(safe_result, dict) else "?")
    except Exception as exc:  # noqa: BLE001
        log.exception("run %s failed: %s", run_id, exc)
        err_event = {"stage": "error", "status": "error", "message": str(exc)}
        with state["cond"]:
            # Avoid duplicate error events if pipeline already emitted one.
            if not any(isinstance(e, dict) and e.get("stage") == "error" for e in state["events"]):
                state["events"].append(err_event)
            state["status"] = "error"
            state["cond"].notify_all()


@app.get("/")
async def root():
    index = ROOT / "web" / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return HTMLResponse("<!doctype html><html><body><h1>SplatDiff</h1><p>web/index.html not found yet.</p></body></html>")


@app.get("/api/sample")
async def api_sample():
    return {
        "before": "/data/sample_before.mp4",
        "after": "/data/sample_after.mp4",
        "watchlist": ["walker", "floor lamp", "backpack"],
        "label": "Synthetic living room (Muse Image)",
    }


def _voice_note_sync(path: str) -> dict:
    transcribed = voice_mod.transcribe(path)
    transcript = transcribed.get("transcript", "") if isinstance(transcribed, dict) else ""
    items = voice_mod.extract_watchlist(transcript)
    try:
        latency_s = float(transcribed.get("latency_s", 0.0)) if isinstance(transcribed, dict) else 0.0
    except Exception:
        latency_s = 0.0
    return {"transcript": transcript, "items": items, "latency_s": latency_s}


@app.post("/api/voice-note")
async def api_voice_note(audio: UploadFile = File(...)):
    suffix = Path(audio.filename or "").suffix
    if not suffix or len(suffix) > 10 or not suffix[1:].replace("-", "").replace("_", "").isalnum():
        suffix = ".webm"
    upload_dir = ROOT / "cache" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"voice_{uuid.uuid4().hex}{suffix}"
    try:
        data = await audio.read()
        dest.write_bytes(data)
        log.info("voice note saved %s (%d bytes)", dest, len(data))
        return await asyncio.to_thread(_voice_note_sync, str(dest))
    except Exception as exc:  # noqa: BLE001
        log.exception("voice note failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.post("/api/runs")
async def api_create_run(
    before: Optional[UploadFile] = File(None),
    after: Optional[UploadFile] = File(None),
    sample: Optional[str] = Form(None),
    watchlist: Optional[str] = Form(None),
    concepts: Optional[str] = Form(None),
    narration: Optional[str] = Form(None),
):
    run_id = uuid.uuid4().hex[:12]
    concepts_list = _split_csv(concepts)
    watchlist_list = _split_csv(watchlist)
    narration_enabled = bool(narration and str(narration).strip() == "1")

    if sample and str(sample).strip() == "1":
        before_path = ROOT / "data" / "sample_before.mp4"
        after_path = ROOT / "data" / "sample_after.mp4"
    else:
        if before is None or after is None:
            return JSONResponse({"error": "before and after files are required unless sample=1"}, status_code=400)
        upload_dir = ROOT / "cache" / "uploads" / run_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        async def _save(upload: UploadFile, stem: str) -> Path:
            suffix = Path(upload.filename or "").suffix
            # Preserve original extension (default .mp4); sanity-check it.
            if not suffix or len(suffix) > 10 or not suffix[1:].replace("-", "").replace("_", "").isalnum():
                suffix = ".mp4"
            dest = upload_dir / f"{stem}{suffix}"
            data = await upload.read()
            dest.write_bytes(data)
            return dest

        before_path = await _save(before, "before")
        after_path = await _save(after, "after")

    state = _new_state()
    with RUNS_LOCK:
        RUNS[run_id] = state

    thread = threading.Thread(
        target=_run_pipeline,
        args=(run_id, str(before_path), str(after_path), concepts_list, watchlist_list, narration_enabled),
        daemon=True,
        name=f"splatdiff-run-{run_id}",
    )
    thread.start()
    log.info("run %s queued thread=%s", run_id, thread.name)
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/events")
async def api_run_events(run_id: str):
    with RUNS_LOCK:
        state = RUNS.get(run_id)
    if state is None:
        return JSONResponse({"error": "run not found"}, status_code=404)

    async def event_stream():
        idx = 0
        last_ping = time.monotonic()
        while True:
            # Poll the shared list without blocking the event loop.
            with state["cond"]:
                pending = list(state["events"][idx:])
                status = state["status"]
            sent_terminal = False
            for ev in pending:
                idx += 1
                last_ping = time.monotonic()
                yield f"data: {json.dumps(ev, default=str)}\n\n"
                if isinstance(ev, dict) and ev.get("stage") in ("result", "error"):
                    sent_terminal = True
            if sent_terminal:
                return
            # Fallback: thread finished but no terminal result/error event was produced.
            with state["cond"]:
                drained = idx >= len(state["events"])
            if status in ("done", "error") and drained and pending == []:
                return
            now = time.monotonic()
            if now - last_ping >= 15:
                last_ping = now
                yield ": ping\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/runs/{run_id}")
async def api_get_run(run_id: str):
    with RUNS_LOCK:
        state = RUNS.get(run_id)
    if state is None:
        return JSONResponse({"error": "run not found"}, status_code=404)
    with state["cond"]:
        events = list(state["events"])
        status = state["status"]
        result = state["result"]
    return _json_safe({"status": status, "events": events, "result": result})


@app.get("/api/history")
async def api_history():
    outputs_dir = ROOT / "outputs"
    entries = []
    if outputs_dir.is_dir():
        files = sorted(outputs_dir.glob("*/result.json"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        for path in files:
            try:
                result = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            try:
                if not isinstance(result, dict):
                    continue
                kept_claims = result.get("kept_claims") or result.get("claims") or []
                dropped_claims = result.get("dropped") or []
                thumb = None
                for claim in kept_claims:
                    if not isinstance(claim, dict):
                        continue
                    images = claim.get("images") or {}
                    if isinstance(images, dict) and (images.get("after") or images.get("before")):
                        thumb = images.get("after") or images.get("before")
                        break
                if not thumb:
                    keyframes = result.get("keyframes") or {}
                    if isinstance(keyframes, dict):
                        for side in ("after", "before"):
                            urls = keyframes.get(side) or []
                            if urls:
                                thumb = urls[0]
                                break
                entries.append(
                    {
                        "run_id": result.get("run_id") or path.parent.name,
                        "summary": result.get("summary") or "",
                        "kept": len(kept_claims),
                        "dropped": len(dropped_claims),
                        "cost_usd": result.get("cost_usd"),
                        "latency_s": result.get("latency_s"),
                        "thumb": thumb,
                    }
                )
            except Exception:
                continue
    return _json_safe(entries)


@app.get("/api/history/{run_id}")
async def api_history_one(run_id: str):
    # Prevent path traversal.
    if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
        return JSONResponse({"error": "run not found"}, status_code=404)
    path = ROOT / "outputs" / run_id / "result.json"
    if not path.is_file():
        return JSONResponse({"error": "run not found"}, status_code=404)
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return JSONResponse({"error": f"unreadable result: {exc}"}, status_code=500)
    return _json_safe(result)


# Static mounts (check_dir=False so missing dirs don't crash startup).
for _route, _dir in (("/web", ROOT / "web"), ("/outputs", ROOT / "outputs"), ("/data", ROOT / "data")):
    try:
        app.mount(_route, StaticFiles(directory=str(_dir), html=(_route == "/web"), check_dir=False), name=_route.strip("/"))
    except Exception as exc:  # noqa: BLE001
        log.warning("could not mount %s: %s", _route, exc)


if __name__ == "__main__":
    os.chdir(ROOT)
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    log.info("starting SplatDiff server on 127.0.0.1:%s root=%s", port, ROOT)
    uvicorn.run(app, host="127.0.0.1", port=port)
