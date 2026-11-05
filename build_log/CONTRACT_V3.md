# Second Look v3 — shared contract (all Muse Wonder workers follow this exactly)

Builds on build_log/UI_CONTRACT.md (v2 result keys, SSE events, endpoints stay as they are). v3 closes the red-team holes:
coverage, re-baselining, multi-room, reminders, delete, people/document blurring, floor clutter, and adds a privacy-safe
live family feed. Product name: Second Look. Parent: Dad.

## Pipeline (splatdiff/pipeline.py, new splatdiff/privacy.py)
`pipeline.run(before, after, concepts=None, out_dir="outputs", progress=None, on_event=None, watchlist=None,
room=None, filmed_by=None)` — new kwargs `room` (default "Bedroom") and `filmed_by` (str|None) copied into the result.

New stages (each emits start/progress/done events with elapsed_s + cost_usd like all others):
1. `privacy` — right after keyframes are extracted and BEFORE any keyframe is sent to Muse Spark: run
   `sam.segment_image(kf, "person")` and `sam.segment_image(kf, "paper document")` on all keyframes (concurrently) and
   Gaussian-blur every detected box (c >= 0.4, padded 10%) IN PLACE in the keyframe JPGs. Annotated evidence images
   saved later must also be redacted: before drawing a claim box on a frame, run the same two SAM image checks on that
   frame and blur. Event `{"stage":"privacy","status":"done","people_blurred":int,"documents_blurred":int,"frames_checked":int}`.
   Result `privacy` = same fields + `"note": "People and paper documents were blurred before any frame was stored, shown or sent to the reasoning model."`
   (Be precise: SAM 3.1 itself sees raw frames because it is the detector.)
2. `coverage` — after inventory, before tracking: Muse Spark gets 3 BEFORE + 3 AFTER keyframes and returns strict JSON
   `{"score":0..1,"missing_in_after":[area str],"missing_in_before":[area str],"retake_tip":str}` judging whether both
   walkthroughs cover the same parts of the room. After tracking, also compute deterministic anchor overlap: anchors =
   concepts detected (present) in either video whose names contain a large-furniture word (bed, sofa, couch, armchair,
   chair, table, dresser, wardrobe, cabinet, desk, bookshelf, nightstand); `anchor_overlap` = |present in both| / |present in either|
   (1.0 if no anchors). Final `coverage.score` = min(spark score, anchor_overlap); `coverage.ok` = score >= 0.6.
   Result `coverage` = {score, ok, anchor_overlap, spark_score, shared_anchors, only_before, only_after, missing_in_after,
   missing_in_before, retake_tip}. Grounding filter addition: if coverage.ok is false, an `added` or `removed` claim
   whose concept is a large-furniture anchor is DROPPED with reason "Not covered by both walkthroughs — re-film {area or
   'that corner'} before trusting this." Event `{"stage":"coverage","status":"done","score":..,"ok":..,"retake_tip":..}`.
3. `floor` — clutter check, grounded: after tracking, Muse Spark looks at the AFTER keyframes and proposes up to 6
   specific objects lying ON THE FLOOR in a walking path (strict JSON {"items":[{"concept": short noun phrase,
   "where": str}]}); each is verified with `sam.segment_image` on the AFTER keyframes: KEPT only if some detection has
   c >= 0.5 AND box bottom y2 >= 0.6 * frame height (it is on the floor); else dropped with reason. Save a redacted,
   annotated image per kept item (`floor_<concept>.jpg`, box in brick red, label "on the floor"). Result `floor_check`
   = {"items":[{"concept","where","c","image": url}], "dropped":[{"concept","reason"}]}. Kept floor items are ALSO added
   to kept_claims as change "on_floor" with risk "high" if near the bed/path else "medium", explanation from `where`,
   images {before:null, after:url}, source "spark+sam". Event `{"stage":"floor","status":"done","kept":int,"dropped":int}`.
Stats: add `privacy_checks`, `coverage_calls`, `floor_checks`. Keep every existing behaviour, key and event.

## Server (server.py)
- `POST /api/runs` new optional form fields: `room` (default "Bedroom"), `filmed_by`, `baseline` ("1" = use the saved
  baseline video for `room` as the BEFORE video; 400 JSON error if none saved), `keep_media` ("1" keeps uploaded raw
  videos; DEFAULT deletes `cache/uploads/<id>/` and the run's normalized videos after the run finishes — log it).
  Pass room/filmed_by to pipeline.run.
- `POST /api/baseline` JSON `{"run_id": <pipeline result run_id>, "room": str}` → copy that run's normalized AFTER video
  to `data/baselines/<room_slug>.mp4` (+ `<room_slug>.json` meta {room, date ISO, from_run, watchlist}); if the
  normalized video was deleted, use the original after file if still present else 409 JSON error "Videos were deleted
  after the check; film a fresh baseline." Returns meta. `POST /api/baseline/upload` multipart `video` + `room` → saves
  directly as baseline (normalized via splatdiff.video_io.normalize_video).
- `GET /api/rooms` → list of {room, slug, baseline: meta|null, last_check: {date, status, run_id}|null, days_since: int|null,
  due: bool} for every room that has a baseline or a check (due = no check yet, or days_since >= 14).
- `DELETE /api/history/{run_id}` → delete `outputs/<run_id>/` (only if the folder name matches ^\d{8}_\d{6}$),
  remove its feed entry, return {"deleted": run_id}.
- Family feed (text only, no images, no transcripts): persisted to `cache/feed.jsonl`; on startup if missing, rebuild
  from outputs/*/result.json. Entry = {"id","ts" ISO,"room","filmed_by","status":"all_clear"|"needs_attention"|"coverage_gap",
  "headline": str, "items":[{"concept","change","risk","next_step"}], "run_id"}. status = coverage_gap if coverage.ok is
  false, else needs_attention if any kept claim risk high or watchlist status in (moved, missing, not_seen), else
  all_clear. headline examples: "Bedroom — all watched items seen where they were", "Bedroom — needs attention: floor
  lamp moved". next_step = a short plain sentence (generate simply server-side). Append when a run finishes.
  `GET /api/feed` → newest first. `GET /api/feed/events` → SSE that first sends {"type":"snapshot","entries":[...],"rooms":[...]}
  then {"type":"entry","entry":{...}} live for every new entry, and {"type":"due","rooms":[...]} every 60 s; ping every 15 s.
- `GET /api/reminder.ics?room=Bedroom&every=14` → text/calendar (attachment) with one VEVENT starting tomorrow 10:00 local,
  RRULE:FREQ=DAILY;INTERVAL={every}, SUMMARY "Second Look: re-film Dad's {room}", DESCRIPTION "Same route: door → bed →
  bathroom door. Lights on. 15–30 seconds." No personal data in the file.
- `GET /family` → FileResponse web/family.html.

## Front-end /app (web/index.html, web/app.js, web/app.css)
- Intake gains: Room select/input (datalist Bedroom, Hallway, Bathroom, Kitchen, Living room; default Bedroom), "Filmed
  by" input, and for the room: if a baseline exists (GET /api/rooms) show "Compare with the saved setup from {date}"
  checkbox (default on) which hides the Last-visit drop zone and sends baseline=1. "Keep the videos after the check"
  checkbox (default OFF) with helper "Off: the raw videos are deleted as soon as the check is done."
- "Record with this phone" button on each drop zone: getUserMedia({video:{facingMode:'environment'},audio:false}) +
  MediaRecorder, live preview with a route overlay text "Door → bed → bathroom door · lights on", 20 s auto-stop, stop
  button, result becomes that slot's file (webm/mp4 blob as File). Handle permission denied clearly.
- Live check: render new stages `privacy` ("Blurring people and papers" · sam-3.1 · "2 people blurred"), `coverage`
  ("Checking both walkthroughs cover the same room" · muse-spark-1.3 · "82% · re-film: bathroom door"), `floor`
  ("Checking the floor and walking path" · muse-spark-1.3 + sam-3.1 · "1 on the floor").
- Report: a coverage line at the top (ok → "Both walkthroughs covered the same room (82%)."; not ok → brick panel
  "These two walkthroughs don't cover the same corners — {retake_tip}" with findings still shown); a privacy line
  ("{n} people and {m} papers blurred before anything was stored or reasoned over · raw videos deleted"); floor-check
  findings render like other findings (title "Shoes — on the floor"). Each finding with change moved/added/removed gets a
  button "This is the new setup" → POST /api/baseline {run_id, room} → confirmation "Saved as Dad's new setup for {room}".
  Report actions add "Delete this check" (inline confirm, DELETE /api/history/{run_id}, then clear report and refresh
  history) and "Remind me to re-film" (link to /api/reminder.ics?room=..&every=14). Past checks drawer gains a delete
  control per row and shows room names. Link "Family feed" in the top bar → /family.

## Family feed page (web/family.html + web/family.css + web/family.js) — the privacy-safe "way to know"
Text only. Shows per-room status rows (room, last check date, status in words, "due" if due) and a live timeline of
feed entries from `/api/feed/events` (new entries slide in, document.title count of needs_attention since load,
optional browser Notification ONLY after the user clicks "Notify me on this device" and grants permission — notification
text is the headline only). No images, no video, no transcripts anywhere on this page. Explain at the top: "This page
shows words, never pictures: each check's result, as soon as it finishes. The videos stay where they were filmed and
are deleted after the check unless someone chose to keep them." Links: "Open full report" (→ /app, past check) and
"Add a re-film reminder" (.ics). Same Care dossier tokens: link /web/app.css first then /web/family.css.
