# SplatDiff front-end brief — "Care dossier"

Build `web/index.html`, `web/app.css`, `web/app.js` (vanilla JS, no build step, no framework). Served by server.py at `/`
(same origin; API per build_log/UI_CONTRACT.md plus the voice endpoint below). This is the demo judges see in a 3-minute
video for the Meta Global AI Developer Hackathon. It must look authored, calm and trustworthy — a family's care record,
not an AI dashboard.

## Who / where / why (use scene)
An adult child, evening, at a laptop after (or before) visiting an aging parent. Slightly anxious, wants a calm, honest
answer to: "What changed in Mom's room since last time — and is anything unsafe?" They filmed two 30-second walkthroughs
on their phone. Trust is everything: every finding shows its evidence; findings the system could not prove are visibly
struck out. Light, warm "paper" world chosen from this scene (reviewing a document at home), not from AI-category habit.

## Visual world
- Paper `#F4EFE6` page, `#FBF8F2` raised sheet, rules `#DDD3C2`, ink `#1E1A16`, secondary ink `#5B5147` (warm, never
  gray), faint ink `#8A7F72` only for large text. Evidence accent (links, focus, primary button) deep green ink `#1F5546`.
  Risk: high `#A3312A` (brick), medium `#9A6410` (ochre), low `#4E6A3B` (moss). Change verbs use the same hues as the SAM
  boxes already drawn on evidence images: added = moss/green, removed = brick/red, moved = ochre/orange.
- Type (Google Fonts, one <link>): display **Fraunces** (opsz, weights 400/600; headlines, summary sentence, finding
  titles), UI/body **Public Sans** (400/500/600), data **IBM Plex Mono** 400/500 ONLY for measurements: costs, seconds,
  frame counts, confidences, model IDs. `font-variant-numeric: tabular-nums` on all numbers.
- Theme the browser surfaces: `::selection` (green ink on pale green), caret-color, focus-visible ring 2px green ink with
  2px offset, thin warm scrollbars, link underline-offset 3px.
- Icons: inline SVG drawn in one consistent 1.5px stroke style (camera, microphone, play, check, x, arrow, printer,
  clock, eye). NO emoji, NO unicode glyph icons.
- BANNED: eyebrow/kicker labels above headings, section numbers, card grids of icon+heading+text, gradient text,
  glassmorphism, colored border-left accents >1px, hard offset shadows, progress rings, sparklines, modals.
  Depth = soft offset shadows (`0 1px 2px rgba(30,26,22,.06), 0 8px 24px -12px rgba(30,26,22,.18)`) on the sheet only.

## Layout — one long document, centered sheet max-width 1080px, 16px side gutters on phones, no horizontal scroll
1. **Masthead.** Wordmark "SplatDiff" (Fraunces 600) + small "Room check" + today's date at right in mono. One-line
   promise as the H1 (Fraunces, ~3rem desktop): "What changed in Mom's room since your last visit?" Sub (Public Sans,
   secondary ink, ≤70ch): "Film the room on each visit. SplatDiff compares the two walkthroughs with Meta's SAM 3.1 and
   Muse Spark, and every finding comes with evidence — or it is struck from the report." Right side / below: a "Past
   checks" button that opens an inline drawer (not a modal) listing `/api/history` items (summary, kept/dropped counts,
   cost, date from run_id `YYYYMMDD_HHMMSS`); clicking one loads `/api/history/{run_id}` and renders the report instantly.
2. **The visit (intake).** Two side-by-side drop zones (stack on mobile): "Last visit" and "Today" — accept video files
   (click or drag), show a `<video>` preview with controls once chosen. Below: "Must stay put" — a tag input for the care
   watchlist (Enter or comma adds a tag; × removes; default empty). Next to it a "Speak your care notes" button:
   MediaRecorder records mic audio (show live elapsed seconds + a stop button; handle permission denied with a clear
   message), POST it as multipart field `audio` to `/api/voice-note`, show the returned transcript in an italic serif
   quote ("Heard: …") and merge returned `items` into the tags with a brief highlight. A checkbox "Also listen to what I
   said while filming" sends `narration=1`. Actions: primary "Check the room" (disabled until both videos chosen OR the
   sample is loaded) and secondary "Use the sample room" (GET /api/sample → set preview videos from the returned URLs,
   prefill watchlist tags, mark sample mode so POST sends `sample=1` instead of files).
3. **The check, as it happens** (appears when a run starts; consume `/api/runs/{id}/events` with EventSource). A vertical
   list of stages, each a row with: status dot (pending/active pulsing/done), a plain-language title, the Meta model in
   mono, and a live detail line:
   - voice (only if a 'voice' event arrives): "Listening to your notes" · muse-voice-transcribe-1.0 · quote of transcript
   - normalize: "Preparing both walkthroughs" · ffmpeg · "5 fps, 640 px"
   - keyframes: show two filmstrips (6 thumbnails each, labeled Last visit / Today) as soon as the event arrives
   - inventory: "Taking inventory of the room" · muse-spark-1.3 · then the concepts as a row of chips
   - track: "Tracking every object in both videos" · sam-3.1 · each concept chip gains two small marks (L for last visit, T for
     today) that fill as each `track/progress` event arrives (filled ink if detections>0, hollow if 0), plus "17/24 tracks"
   - recheck: "Double-checking anything that appeared or vanished" · sam-3.1 · per concept "found in last visit (c 0.75)"
     or "confirmed absent"
   - judge: "Deciding what actually moved" · muse-spark-1.3 · per concept "moved 0.90" / "stayed 0.85"
   - report: "Writing the findings" · muse-spark-1.3
   - filter: "Holding every claim to its evidence" · grounding filter · "3 kept · 1 struck"
   A running ledger line under the list in mono: "elapsed 41.2 s · cost $0.21 · models used: …" updated from every
   event's elapsed_s / cost_usd. On `error`, show the message in brick ink with a "Try again" action.
4. **The report** (render from the `result` event, or from history). Order:
   a. Summary sentence (Fraunces, large) + a line "Checked {stats.concepts} objects · {stats.sam_requests} SAM tracks ·
      {cost} · {latency}".
   b. "Care watchlist" (only if watchlist_status non-empty): one row per item — item name, status in words
      ("still in place", "moved", "missing", "appeared", "not seen"), risk tag, note; tiny before/after thumbs if images.
   c. "What changed" — findings sorted high→medium→low risk. Each finding is a full-width row on the sheet (NOT a card
      grid): risk tag (word + colored dot), title like "Floor lamp — moved" (Fraunces), explanation, safety_note /
      risk_reason in secondary ink, and an "Evidence" disclosure. Expanded evidence board: the before and after annotated
      plates side by side (img from `images.before` / `images.after`, captions "Last visit · frame 10" / "Today · frame
      8"), and a compact mono evidence table: frames seen last visit / today, confidence last visit / today, SAM re-check
      result (checked? found? where?), source (spark|sam). Missing image → a quiet placeholder "not in frame".
   d. "Struck from the report" — dropped claims. Each title is drawn with an INK STRIKE: an SVG hand-drawn wavy line
      over the text animated with stroke-dashoffset (~600 ms, ease-out, staggered 120 ms) when the report first
      renders — THIS IS THE ONE SIGNATURE MOTION MOMENT of the page; everything else is quiet. Below each, the reason in
      brick ink: e.g. "SAM re-check found the armchair in last visit's keyframe 1 (c 0.75) — it did not appear." Evidence
      disclosure here too.
   e. Ledger footer: models used (mono chips from result.models), Spark calls, SAM requests & frames, re-checks, cost,
      latency, run id. Buttons: "Print for family" (window.print()) and "Copy summary" (clipboard text of summary +
      findings + struck items).
5. **Print stylesheet** (`@media print`): hide masthead buttons, intake, live check, drawer; show a family letter header
   "Room check — {date}" and the report only, black ink on white, evidence images at 45% width side by side, page-break
   avoidance per finding.

## Behaviour details
- Upload: POST /api/runs as FormData {before, after, watchlist (comma), narration ('1'|''), sample ('1' in sample mode)}.
- While running: disable "Check the room", show stage list; scroll it into view smoothly once.
- prefers-reduced-motion: no strike animation (lines drawn), no pulsing.
- Responsive: ≥900px two-column intake and side-by-side plates; <900px everything stacks; test copy at 375px.
- Empty state for history ("No checks yet — try the sample room").
- All text real; no lorem; no placeholder metrics.
- Keep JS readable: small render functions (renderStage, renderReport, renderFinding, renderStruck, renderHistory),
  `escapeHtml` for every server string.

## Voice endpoint (server side, built separately)
`POST /api/voice-note` multipart `audio` (browser webm/ogg/wav) → `{"transcript": str, "items": [str], "latency_s": float}`.
`POST /api/runs` accepts `narration=1` → server transcribes the Last-visit video's audio and emits
`{"stage":"voice","status":"done","model":"muse-voice-transcribe-1.0","transcript":str,"items":[str]}` before pipeline events.
