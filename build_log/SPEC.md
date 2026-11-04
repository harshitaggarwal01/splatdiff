# SplatDiff — build spec (given to Muse Wonder)

You are writing a complete, working Python 3.12 repository called **SplatDiff** for the Meta Global AI
Developer Hackathon (Indie track, "Push the Frontier"). Deadline is in under 3 hours, so the code must run
correctly the FIRST time. Prefer simple, defensive, well-logged code over cleverness. No placeholders, no TODOs.

## Product
"What changed in this room?" Input: two short phone videos of the same room (BEFORE and AFTER).
Output: a grounded change report — which objects were ADDED, REMOVED, or MOVED — where every claim is backed by
SAM 3.1 detections (boxes, frame ids, confidences), and any claim the reasoning model makes that SAM evidence does
not support is DROPPED and shown as dropped ("grounded-or-dropped"). Use-case framing: caregiver safety check of an
elderly parent's room ("the walker was moved out of reach"), rental move-out inspection.

## Pipeline
1. `normalize_video(in_path) -> out_path`: transcode with the ffmpeg binary from `imageio_ffmpeg.get_ffmpeg_exe()`
   to H.264 MP4, `-vf fps=5,scale=640:-2`, max 30 s (`-t 30`), `-pix_fmt yuv420p -an`. That caps SAM at <=150 frames
   per clip. Cache by input file sha256 into `cache/`.
2. Keyframes: extract K=6 evenly spaced frames per normalized video with OpenCV (JPEG, for Spark + UI).
3. **Muse Spark 1.3 object inventory** (`muse-spark-1.3`): send keyframes of BOTH videos (as `input_image` base64 data
   URLs, labeled in text "BEFORE frame i" / "AFTER frame i") and ask for strict JSON:
   `{"objects": [{"concept": "<short singular noun phrase SAM can segment, e.g. 'floor lamp'>", "where_before": str, "where_after": str, "suspected_change": "added|removed|moved|unchanged"}]}`
   max 12 objects, prioritise movable household objects. Parse JSON robustly (strip ``` fences, find first `{`..last `}`).
   Allow a `--concepts` override (comma list) to hand-seed concepts.
4. **SAM 3.1 tracking** (`sam-3.1`): for each concept x each video, upload video once via Files API (cache file_id per
   sha256) and run a concept-prompt video segmentation request. Run requests concurrently (ThreadPoolExecutor, 6 workers).
   Parse output into `{frame_idx: [{"obj": int, "box": [x1,y1,x2,y2], "c": float, "w": int, "h": int}]}`.
5. **Diff** (pure Python, deterministic): per concept compute for each video: `frames_detected`, `max_instances`,
   `mean_conf`, `best_frame` (highest c), `best_box`. Presence = detected in >= 2 frames with c >= 0.5 (constants at top).
   SAM-evidence change label: present only in AFTER -> `added`; only in BEFORE -> `removed`; in both -> `present_both`
   (candidate for moved/unchanged); in neither -> `not_found`. Also flag count changes (max_instances differs).
6. **Muse Spark 1.3 grounded report**: for every concept with `present_both`, send Spark the BEFORE best frame and AFTER
   best frame with the SAM box drawn (and a context crop), ask strict JSON `{"moved": bool, "confidence": 0..1, "reason": str}`
   judging position relative to surrounding furniture (camera viewpoint differs between videos — say so in the prompt).
   Then one final Spark call gets the full diff table (JSON) and writes claims:
   `{"summary": str, "claims": [{"concept": str, "change": "added|removed|moved", "explanation": str, "safety_note": str|null}]}`.
7. **Grounding filter**: a claim is KEPT only if SAM evidence agrees: `added` needs SAM label added; `removed` needs
   removed; `moved` needs present_both AND the pairwise moved-verdict true. Everything else -> `dropped` with a reason
   string. Also add any SAM-only added/removed changes that Spark failed to mention as kept claims with
   `source: "sam"`. Each kept claim carries evidence: concept, label, frames, best boxes, confidences.
8. Save `outputs/<run_id>/result.json`, annotated keyframes (`before_<concept>.jpg`, `after_<concept>.jpg` with
   coloured boxes + label: green added, red removed, orange moved), and `report.md`.

## Meta Model API facts (verified by hand today — follow exactly)
- Base URL `https://api.meta.ai/v1`, header `Authorization: Bearer $MODEL_API_KEY`. Load env with `python-dotenv`
  (`load_dotenv()` at import). Never print the key.
- All model calls: `POST /v1/responses` with JSON. Use `requests` (not the OpenAI SDK) for everything, non-streaming,
  timeout 300 s, 3 retries with backoff on 429/5xx/timeouts, never retry 400 (print the error body).
- Text extraction from a response: iterate `resp["output"]`, take items with `type == "message"`, concatenate
  `content[*].text` for parts with `type == "output_text"`.
- Image input part: `{"type": "input_image", "image_url": "data:image/jpeg;base64,<b64>"}`. Text part:
  `{"type": "input_text", "text": "..."}`. Message: `{"type": "message", "role": "user", "content": [...]}` inside `input` list.
- Muse Spark request: `{"model": "muse-spark-1.3", "input": [message], "reasoning": {"effort": "low"}, "max_output_tokens": 4000}`.
- Files API: `POST /v1/files` multipart, form field `purpose=user_data`, file field `file` (filename, bytes, "video/mp4").
  Response JSON has `id` like `file-...`. Synchronous.
- SAM 3.1 video request body:
  ```json
  {"model": "sam-3.1",
   "input": [{"type": "message", "role": "user", "content": [
      {"type": "input_text", "text": "floor lamp"},
      {"type": "input_video", "file_id": "file-..."}]}],
   "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
   "store": false}
  ```
  For images use `{"type": "input_image", "image_url": "data:image/jpeg;base64,..."}` instead of input_video.
- SAM output is TEXT (in the normal output_text) in a token grammar, NOT JSON. Real example (image, one object):
  ```
  <0f>0<|box;x1=0;y1=265;x2=233;y2=638;w=640;h=640;c=0.9452055096626282|><|mask;x=0;y=0;c=0.94;data=374,234,!!!!$TD)5Ov...|>
  ```
  `<Nf>` = frame index marker; the integer right after a marker or after a `,` separator = object ordinal; then a box
  record then a mask record. Multiple objects in a frame are comma separated. Video = one line per frame (`\n`), frames
  may arrive out of order — key by the marker. Box coords are pixels, inclusive. A concept with no match returns
  empty text. Mask payload encoding is undocumented — IGNORE masks, use boxes only. Parse with regexes:
  split on `<(\d+)f>`, then within a frame segment find `(\d+)\s*<\|box;([^|]*)\|>` and parse `k=v;` pairs.
  SAM tracks at most 16 objects per frame.
- Pricing (for the cost ledger): Spark $1.25/M input tokens, $4.25/M output tokens (read `usage.input_tokens`,
  `usage.output_tokens` from response); SAM $0.20 per 1000 video frames (min 50 frames/request), $2.50 per 1000 images;
  Muse Image $0.01/image. Append every call to `cache/costs.jsonl` (model, kind, est_usd, latency_s, ts).
- Disk cache: every Responses call is cached in `cache/responses/<sha256 of request json>.json`; return cached result
  if present (makes demo re-runs free and instant). Env `SPLATDIFF_NO_CACHE=1` disables.
- Muse Image (`muse-image-1.0`): `POST /v1/images/generations` JSON `{"model","prompt","size":"1024x1024","n":1}` returns
  `data[0].b64_json` (WEBP bytes). Edits: `POST /v1/images/edits` multipart with fields `model`, `prompt`, file field
  `image` (png bytes); same response shape. Decode with Pillow, save JPEG.

## Files to produce (exact paths)
- `splatdiff/__init__.py`
- `splatdiff/meta_api.py` — session, retries, cache, cost ledger, `responses(body)`, `extract_text(resp)`,
  `upload_file(path)`, `image_part(path_or_ndarray)`, `parse_json_loose(text)`.
- `splatdiff/video_io.py` — normalize_video, extract_keyframes, read_frame(video, idx), draw_box, `pan_video_from_image(img_path, out_mp4, seconds=8, fps=10)`
  (Ken-Burns pan across a still using OpenCV to make a synthetic handheld clip, then normalize to H.264 via ffmpeg).
- `splatdiff/spark.py` — list_objects, judge_moved, write_claims.
- `splatdiff/sam.py` — parse_sam_text, track_concept(video_path, concept), segment_image(img, concept).
- `splatdiff/diff.py` — summarize_tracks, sam_labels, grounding_filter. Pure functions, no API calls.
- `splatdiff/pipeline.py` — `run(before, after, concepts=None, out_dir="outputs") -> dict`, with progress callback
  `progress(msg: str)`; CLI: `python -m splatdiff.pipeline before.mp4 after.mp4 [--concepts a,b]`; prints a table.
- `app.py` — Gradio 6 Blocks UI: two `gr.Video` inputs side by side, optional concepts textbox, "Run SplatDiff" button,
  "Load sample pair" button (uses data/sample_before.mp4/data/sample_after.mp4 if present), outputs: markdown report
  (kept claims with evidence, dropped claims struck through with reason), `gr.Gallery` of annotated before/after
  keyframes, `gr.JSON` of raw result, and cost/latency line. Use `demo.launch()`; no deprecated args.
- `eval.py` — `python eval.py --gt data/gt.json --result outputs/<run>/result.json` (or `--run before after`);
  gt format `[{"concept": "backpack", "change": "removed"}, ...]`; fuzzy concept match (lowercase, token overlap);
  report precision/recall/F1 for (a) raw Spark claims and (b) grounded kept claims, hallucinated-claim rate
  (raw claims not in gt) before/after filter, total cost, latency; write `outputs/eval.md` markdown table.
- `scripts/make_synthetic.py` — Muse Image: generate a living-room "before" image, edit it into "after" (remove the
  blue backpack, move the floor lamp next to the armchair, add a red suitcase by the sofa), then make pan videos
  `data/sample_before.mp4`, `data/sample_after.mp4` and `data/sample_gt.json`. Skip generation if images already exist
  at `data/before.jpg` / `data/after.jpg`.
- `requirements.txt` (gradio, opencv-python-headless, numpy, requests, python-dotenv, imageio-ffmpeg, pillow),
  `.env.example` (`MODEL_API_KEY=`), `LICENSE` (MIT, 2026, Harshit Aggarwal).
- `README.md` — pitch, architecture diagram (mermaid), exact model IDs used (muse-spark-1.3, sam-3.1, muse-image-1.0,
  and that the codebase itself was generated with muse-wonder-1.0 via `build_log/wonder_build.py`), setup
  (`pip install -r requirements.txt`, `.env`), usage (CLI, UI, eval), the grounded-or-dropped rule, cost per run,
  honest limitations (handheld viewpoint changes, SAM recall on small objects, boxes not masks, 30 s cap), and a
  **"Prior work disclosure"** section: the author's earlier research on object-change detection in 3D scenes
  motivated this idea; no code, data, or figures from it are used — everything in this repo was written during the
  hackathon (Nov 4, 2026). Do not mention any paper title or venue.
- `VIDEO_SCRIPT.md` — 3-minute demo script with timestamps (problem 0:00-0:20, clips 0:20-0:50, live run
  0:50-1:50, dropped-claim + eval table 1:50-2:30, Meta-specific stack + cost + limits 2:30-3:00).

## Output format (STRICT)
Output every file as:
```
=== FILE: relative/path.ext ===
<full file content>
=== END FILE ===
```
No other prose outside file blocks except an optional one-paragraph note at the very end. Do not wrap file contents in
markdown fences inside the blocks. Every Python file must be importable and complete.
