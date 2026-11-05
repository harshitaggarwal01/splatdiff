# Visual critique by muse-spark-1.3 (8 screenshots)

**Verdict: strong concept, prototype skin.** Feels like a working demo with debug logging left on, not a shipped family product. Judges will trust the idea but ding the craft.

### What screams AI-generated / vibe-coded

**Debug text shipped as UI:**
- `sam-3.1 • 0.7s`, `muse-spark-1.3`, `muse-wonder-1.0`, `grounding filter`, `ffmpeg`, `5 fps, 640 px`
- `elapsed 15.0 s • cost $0.01 • models used: sam-3.1...`
- `Checked 12 objects • 26 SAM tracks • $0.01 • 15.8s • Bedroom`
- `24/24 Tracks`, `24 tracks finished` with cryptic icons after every object
- Bounding box labels: `["walker" 67%`, `["walker" — on your left, close.`
- Reasoning dumps: `Coaster — stayed d .9s: same spot on table...`, `Floor lamp — moved d .1s: lamp was behind...`
- `Removed: detected in 40 frames before ( best ) with 0 frames after.` / `Added: 0 frames before to 16 frames after ( best ) in right area by sofa/plant.`

**Leaked implementation as copy:**
- `Clips are sent to Meta's model API to find objects.`
- `The agent reads the words on this page — never the pictures.`
- `Notifications are blocked in this browser. The feed above still updates live.`
- `This memory lives only in the glasses session and is forgotten when you close it.`

**Repetition / sloppy copy:**
- Same insight pasted twice verbatim: `Backpack, suitcase and floor lamp changes keep being flagged in almost every bedroom check...`
- `Needs attention: 3` brown box repeats 2 screens later
- `0 people and 2 papers blurred before anything was stored` - grammar + robotic
- `Last visit: using the saved setup from Nov 4, 2026 for Bedroom. Untick above to film a new last-visit video instead.` - incomprehensible
- Helper text under inputs is questions: `Which room are you checking?` / `Who filmed today's walkthrough? Named on the family feed.`
- Dates in future: `Nov 4, 2026`, `Wed, Nov 4, 2026`
- Title cropped: `In his glasses`, `in his glasses`

**Hierarchy / density:**
- Everything is same size small gray serif. No clear H1 action. Walls of 12px explainer text under every section.
- Check log is 10+ equal-weight bullet steps with 6x identical thumbnails in a row. Looks like a terminal log, not progress.
- `What changed` vs `Do this next` vs `Care watchlist` - three systems for same finding, no visual priority. High-risk buried.

**Inconsistent components:**
- 4 button styles on one screen: solid green `Check the room ->`, white `Use the sample room`, gray `Record with this phone`, red-outline `Simulate a fall alert`
- Pills, chips, tags all different radius: `walker x`, `floor lamp x`, `What changed this week?`, `low risk`
- Alignment: two-column form with mismatched input heights, right rail `Where did I leave it?` floats disconnected.

### What’s genuinely good
- Core promise is instantly legible: 2 walkthroughs -> what changed + evidence.
- Privacy framing is excellent differentiator: `words, never pictures`, `0 people blurred`, `Film with Dad's knowledge — ideally together.`
- `Do this next: 1. Ask Dad... 2. If not... 3. Re-check next visit.` + `Mark as sorted` - actionable, non-alarming tone.
- Watchlist / Must-stay-put mental model fits families.
- Glasses simulation is a great 3-min video moment - live overlay + `Where did I leave it?`

### 8 highest-value fixes

1. **Hide all models/costs behind one disclosure.** Delete every `sam-3.1, muse-*, ffmpeg, $0.01, fps, tracks` from main UI. Replace with one collapsed line: `How we checked • 12 objects • 16 sec • Same room 90% match`
2. **Kill the brown debug box.** Change `Needs attention: 3 • Backpack — removed • Suitcase — added • Floor lamp — moved` to real card: `3 changes need a look: Backpack missing from coffee table, Suitcase new by sofa, Floor lamp moved.`
3. **Rewrite human findings, delete duplication.** Current duplicated paragraph -> one line: `Same 3 items have moved in most recent checks. Walker has stayed put until now.`
4. **Fix evidence speak.** Change `Removed: detected in 40 frames before (best) with 0 frames after.` -> `Was on the coffee table last visit. Not seen anywhere today.` Change `0 people and 2 papers blurred...` -> `People and papers blurred before review. Videos deleted after check.`
5. **Fix Visit form.** Labels above, not below. Replace helper Qs with: `Room: Bedroom` / `Filmed by: Who took this video? e.g. Maya` / Checkbox: `Compare to last visit — Bedroom, Nov 4` / Info: `Why film the same path? So we see behind chairs and along the floor. Nothing installed.`
6. **Unify buttons.** One primary only: `Check the room`. Secondary quiet: `Try sample video`. Delete `Record with this phone` as separate box - make it icon inside upload drop. Restyle `Simulate a fall alert` out of product UI for demo only.
7. **Collapse pipeline.** Don't show 10 log steps. Show 3 human steps with progress: `1. Finding key moments 2. Checking watchlist items 3. Writing findings with evidence.` Put thumbnails + `inventory` chips in expandable `Details`.
8. **Fix Family feed headline + sub.** Change `How is Dad's room? / This page shows words, never pictures...` -> `How is Dad's room? / Words only — no videos or photos are stored here. Last check: Yesterday, 3 changes to review.` Delete `The agent reads the words...`