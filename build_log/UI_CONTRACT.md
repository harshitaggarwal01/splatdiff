# SplatDiff v2 — shared contract (all Muse Wonder workers follow this exactly)

Repo: Python 3.12, existing package `splatdiff/` (meta_api.py, video_io.py, spark.py, sam.py, diff.py, pipeline.py).
`pipeline.run(before, after, concepts=None, out_dir="outputs", progress=None)` exists and returns a result dict with keys:
run_id, before, after, normalized_before, normalized_after, objects, concepts, summaries, diff_table, moved_verdicts,
summary, raw_claims, claims, kept_claims, dropped, annotated_images, latency_s, cost_usd. It writes outputs/<run_id>/.

Existing claim shapes (real):
kept claim  = {"concept","change":"added|removed|moved","explanation","safety_note","source":"spark|sam",
               "evidence":{"label","original_label","recheck":{...},"frames_before","frames_after","best_box_before",
               "best_box_after","best_frame_before","best_frame_after","confidence_before","confidence_after",...}}
dropped     = {"concept","change","explanation","safety_note","reason"}
annotated image files: outputs/<run_id>/before_<concept_with_underscores>.jpg, after_<...>.jpg

## v2 additions to the result dict (pipeline worker implements, server + UI consume)
- `watchlist`: list[str] — care items the user said must stay put (e.g. "walker", "pill organizer", "phone").
- `watchlist_status`: list of {"concept", "status": "in_place|moved|missing|appeared|not_seen", "risk": "high|medium|low",
   "note": str, "images": {"before": url|null, "after": url|null}}.
- every kept claim and dropped claim gains:
   `"risk": "high|medium|low"`, `"risk_reason": str` (caregiver fall/safety lens, from Muse Spark write_claims),
   `"images": {"before": url|null, "after": url|null}` (annotated evidence frames, URL form "/outputs/<run_id>/<file>.jpg"
   using forward slashes; null when absent).
- `stats`: {"concepts": int, "sam_requests": int, "sam_frames": int, "spark_calls": int, "rechecks": int}.
- `models`: ["muse-spark-1.3", "sam-3.1"] plus any others actually called.
- `keyframes`: {"before": [url,...], "after": [url,...]} (the 6 extracted keyframes per video, URL form as above).

## Structured progress events
`pipeline.run(..., on_event=None, watchlist=None)` — new optional kwargs. `on_event(dict)` is called (thread-safe; may be
called from worker threads) with events that ALL include `"stage"`, `"status"`, `"elapsed_s"` (float), `"cost_usd"` (running
cost of this run so far, float). Stages, in order:
1. `{"stage":"normalize","status":"start"|"done"}`
2. `{"stage":"keyframes","status":"done","before":[url..],"after":[url..]}`
3. `{"stage":"inventory","status":"start"|"done","model":"muse-spark-1.3","concepts":[str],"objects":[...]}`
4. `{"stage":"track","status":"start","total":int}` then per finished SAM request
   `{"stage":"track","status":"progress","concept":str,"video":"before"|"after","frames":int,"detections":int,"done":int,"total":int}`
   then `{"stage":"track","status":"done"}`
5. `{"stage":"recheck","status":"start"|"progress"|"done", "concept":str, "found":bool, "c":float}` (progress per concept)
6. `{"stage":"judge","status":"start"|"progress"|"done","concept":str,"moved":bool,"confidence":float,"reason":str}`
7. `{"stage":"report","status":"start"|"done","model":"muse-spark-1.3","raw_claims":int}`
8. `{"stage":"filter","status":"done","kept":int,"dropped":int}`
9. `{"stage":"done","status":"done","run_id":str}`  (or `{"stage":"error","status":"error","message":str}` on exception)
The existing `progress(msg)` string callback must keep working unchanged (app.py uses it).

## HTTP server (server.py, FastAPI + uvicorn, both already installed via gradio)
- `python server.py` → uvicorn on 127.0.0.1:8000. Serves `web/index.html` at `/`, static mounts `/web` (web/),
  `/outputs` (outputs/), `/data` (data/).
- `GET /api/sample` → `{"before":"/data/sample_before.mp4","after":"/data/sample_after.mp4","watchlist":["walker","floor lamp","backpack"],"label":"Synthetic living room (Muse Image)"}`
- `POST /api/runs` multipart: `before` (file, optional if sample), `after` (file, optional if sample), `sample` ("1" to use
  the sample pair), `watchlist` (comma string, optional), `concepts` (comma string, optional) → `{"run_id": str}`.
  Saves uploads to `cache/uploads/<id>/before<ext>` / `after<ext>`. Starts `pipeline.run` in a background thread with
  `on_event` pushing into a per-run queue + history list.
- `GET /api/runs/{id}/events` → `text/event-stream`; replays all past events for the run first, then streams new ones;
  each SSE message `data: <json>\n\n`; heartbeat comment every 15 s; closes after `done`/`error`.
- `GET /api/runs/{id}` → `{"status":"running|done|error","events":[...],"result":{...}|null}`.
- `GET /api/history` → newest-first list of past runs from `outputs/*/result.json`:
  `{"run_id","summary","kept":int,"dropped":int,"cost_usd","latency_s","thumb": url|null}`; `GET /api/history/{run_id}` → full result.json.
- CORS not needed (same origin). Never log or return the API key.
