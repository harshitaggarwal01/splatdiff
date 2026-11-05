# Second Look — static (GitHub Pages) mode contract

Goal: the same pages (web/home.html, web/index.html (app), web/family.html, web/glasses.html with their css/js) run with NO
Python server on GitHub Pages at https://harshitaggarwal01.github.io/splatdiff/ (BASE = "/splatdiff"). VERIFIED today:
https://api.meta.ai/v1/responses, /v1/files and /v1/asr/transcribe answer CORS preflight with Access-Control-Allow-Origin: *,
so the browser can call Meta's API directly with the visitor's own key.

## Build output (scripts/build_static.py writes docs/)
docs/index.html (from web/home.html), docs/app/index.html (web/index.html), docs/family/index.html, docs/glasses/index.html,
docs/web/* (all css/js + assets), docs/data/sample_before.mp4 + sample_after.mp4, docs/outputs/<hero run ids>/** (images,
keyframes, result.json), docs/static/*.json (baked API data, see below), docs/.nojekyll.
Every page gets, as the FIRST thing in <head>: `<script>window.SL_STATIC=true;window.SL_BASE="/splatdiff";</script>` then
`<script src="/splatdiff/web/static-mode.js"></script>` and (app page only) `<script src="/splatdiff/web/browser-pipeline.js"></script>`.
Absolute paths in HTML/JS/JSON are rewritten: '/web/' '/outputs/' '/data/' -> BASE + same; page links "/app" "/family"
"/glasses" "/" (also with ?query) -> BASE + "/app/" etc. ("/" -> BASE + "/"). API paths ("/api/...") are NOT rewritten
(static-mode.js intercepts them; it must also accept them if prefixed with BASE).

## Baked data (docs/static/)
- sample.json  = GET /api/sample response (URLs prefixed with BASE)
- history.json = GET /api/history list; history/<run_id>.json = full result (all URLs prefixed with BASE)
- rooms.json, feed.json = GET /api/rooms, GET /api/feed
- replay.json  = {"run_id": "<pipeline run id>", "events": [ {...event, "t": seconds since start} ... ]} — a real recorded
  server run of the sample (events include the final {"stage":"result","result":{...}} with URLs prefixed)
- agent_context.json = the words-only context the family agent uses (same as splatdiff/agent.build_context()).

## web/static-mode.js (window.SL)
- `SL.base`, `SL.isStatic` from the globals. Does nothing at all if !window.SL_STATIC.
- Key: `SL.key.get()` (sessionStorage 'sl_meta_key'), `SL.key.clear()`, `SL.key.require(reason)` -> Promise<string>: if no key,
  opens an accessible <dialog> (Care dossier styling, injected CSS) titled 'Use your own Meta API key for this session'
  with text: 'Live features call Meta's models directly from this browser. Your key stays in this tab only (sessionStorage)
  and is sent only to api.meta.ai — never to us. Close the tab and it's gone.' + password input + 'Use key' / 'Cancel'
  buttons + link 'Get a key' -> https://dev.meta.ai ; validates with GET https://api.meta.ai/v1/models (Bearer); on 401
  shows 'That key didn't work.'; resolves with the key, rejects on cancel. Shows a small persistent chip 'Your key ·
  this tab only · Forget' once set.
- Meta client: `SL.meta.responses(body)` (POST /v1/responses JSON, Bearer key, 3 retries on 429/5xx), `SL.meta.text(resp)`
  (concatenate output[type=message].content[type=output_text].text), `SL.meta.json(text)` (loose JSON parse: strip fences,
  first { .. last }), `SL.meta.samImage(dataUrl, concept)` -> [{box:[x1,y1,x2,y2], c, w, h}] (sam-3.1, input_text concept
  + input_image dataUrl, metadata include_confidence 'true', mask_encoding 'one_bit'; parse output text grammar: split on
  /<(\d+)f>/, boxes via /(\d+)\s*<\|box;([^|]*)\|>/g with k=v; pairs), `SL.meta.transcribe(wavBlob)` (POST
  /v1/asr/transcribe multipart: 'request' = Blob(JSON {model:'muse-voice-transcribe-1.0',audioEncoding:'WAV',mode:'DIARIZATION'},
  {type:'application/json'}), 'audio' = wav; Accept text/plain; returns text), `SL.audio.toWav16k(blob)` (decodeAudioData ->
  OfflineAudioContext 16 kHz mono -> PCM16 WAV Blob).
- fetch shim (wrap window.fetch; match path with or without BASE prefix; everything else passes through, prefixing BASE
  for same-origin absolute paths):
  GET /api/sample, /api/history, /api/history/{id}, /api/rooms, /api/feed -> baked JSON (plus locally-created entries kept in
  memory this tab); POST /api/runs: if form has sample=1 -> {run_id:'replay'}; else require key, start
  `window.SLBrowserPipeline.run({beforeFile, afterFile, watchlist, room, filmedBy, onEvent})` and return {run_id:'local-<ts>'};
  GET /api/runs/{id} -> {status, events, result}; POST /api/ask {question} and /api/update {for,name} -> require key, call
  muse-spark-1.3 with the same rules as splatdiff/agent.py (words-only context = agent_context.json + local results; answer
  JSON {answer, source_run_ids}); POST /api/glasses/frame (FormData image, watchlist) -> require key, samImage per item
  (concurrently, max 4) + the deterministic whisper (direction by box centre thirds, distance by box height fraction
  >0.55 close, >0.25 a few steps away, else across the room) -> {detections, whisper, latency_s}; POST /api/glasses/fall ->
  add a local feed entry (no key); POST /api/voice-note (FormData audio) -> require key, toWav16k, transcribe, then Spark
  extract {items, intentional} -> {transcript, items, intentional, latency_s}; POST /api/baseline, DELETE /api/history/{id}
  -> friendly JSON {error:'Available when you run Second Look yourself — see GitHub.'} with status 501;
  /api/reminder.ics -> generate the .ics client-side and return it as text/calendar.
- EventSource shim (replace window.EventSource): '/api/runs/replay/events' -> replays replay.json events honouring their
  't' (speed x1.5) then closes; '/api/runs/local-*/events' -> streams the browser pipeline's events; '/api/feed/events' ->
  sends {type:'snapshot', entries, rooms} then {type:'entry', entry} for local entries. Implements onmessage, onerror,
  addEventListener('message'), close(), readyState.
- A slim banner at the very top of every page (injected): 'Static demo on GitHub Pages · sample checks replay a real
  recorded run · your own videos use your Meta API key in this tab only · Run it yourself →' (link to the GitHub repo).

## web/browser-pipeline.js (window.SLBrowserPipeline.run(opts) -> Promise<result>)
Keyframe-based port of splatdiff/pipeline.py (no ffmpeg, no video upload): uses SL.meta. Emits the SAME stage events and
returns the SAME result shape (see build_log/UI_CONTRACT.md + CONTRACT_V3.md) so web/app.js renders it unchanged; all image
URLs are data: URLs (JPEG 0.85) drawn on canvases.
1 keyframes: load each File in a hidden <video> (object URL, muted, playsinline), seek to 6 evenly spaced times, draw to
  640px-wide canvas -> event keyframes {before:[dataUrl], after:[...]}. Fail clearly if the browser can't decode the video.
2 privacy: samImage(kf,'person') and samImage(kf,'paper document') on all 12 keyframes (concurrency 6), blur boxes (c>=0.4,
  pad 10%) on the canvases with ctx.filter='blur(14px)' -> event privacy.
3 inventory: muse-spark-1.3 with the 12 keyframes (labelled BEFORE/AFTER i) -> JSON {objects:[{concept,...}]} max 10; prepend
  watchlist; cap 12 -> event inventory.
4 coverage: Spark JSON {score, retake_tip} from 3+3 keyframes -> event coverage (ok = score >= 0.6).
5 track (keyframe presence): samImage(kf, concept) for each concept x 12 keyframes (concurrency 6) -> per concept/side:
  frames_detected (c>=0.5), best box/conf/keyframe; events track progress per (concept, side).
6 labels: present = frames_detected >= 1 with best c >= 0.6 -> added / removed / present_both / not_found; vocabulary
  repair for not_found watchlist items (Spark aliases -> samImage tests on 3+3 keyframes) -> event repair.
7 judge: for present_both concepts (max 6, watchlist first) Spark judge_moved on the two best keyframes with the box drawn
  -> {moved, confidence, reason}; moved kept only if confidence >= 0.8 -> events judge.
8 report: Spark writes claims {summary, claims:[{concept, change, explanation, safety_note, risk, risk_reason}]} with the
  watchlist in the prompt -> event report.
9 filter: same grounded-or-dropped rules as diff.py (added needs SAM added, removed needs removed, moved needs present_both
  + verdict); build watchlist_status, kept/dropped with images {before, after} (annotated canvases: green added, red
  removed, orange moved), stats, models ['muse-spark-1.3','sam-3.1'], cost estimate (Spark tokens from usage, SAM
  images x $0.0025) -> events filter, done, result. run_id 'local-YYYYMMDD_HHMMSS'.
Never send anything anywhere except api.meta.ai. Keep the key out of logs.
