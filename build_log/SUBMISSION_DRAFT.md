# Second Look — submission draft

**Project name:** Second Look

**Engine codename:** SplatDiff is the engine codename from the author's earlier 3D-scene research; this product uses no Gaussian splats.

**One-line tagline:** What changed in Dad's room? Two phone walkthroughs in, a change report out — every finding backed by SAM 3.1 evidence, or struck from the report.

**One-sentence pitch (both critics' best lines, merged):** Second Look compares two short phone walkthroughs of Dad's room between visits and reports what was added, removed or moved — every finding shows its SAM 3.1 boxes, frames and confidences, and every claim it can't prove is struck from the report in front of you, reason shown.

**15-second hook:** "Last month Dad's room was set up safe. This month the walker is out of reach — and nobody noticed. We filmed twice. Watch the AI claim an armchair appeared — and watch us strike it, because the evidence says it was there all along."

## Description (150 words)

Second Look is for a daughter whose dad, 82 and living alone, has just come home from hospital. On discharge day she films the OT-approved safe setup — walker next to the bed, lamp within reach, path clear. Next visit she films again. Second Look compares the walkthroughs and reports what was added, removed or moved, watchlist first, each finding triaged for risk and backed by before/after frames, SAM 3.1 boxes, frames seen and confidences. Any claim without that evidence is struck from the report, reason shown. Every HIGH finding ends in Do this next, Mark as sorted, and a re-check next visit. On our one scoreable test room (3 runs), the raw model invented claims 25–40% of the time; grounding struck every one — a smoke test, not a benchmark. Not a medical device.

## How we used Meta models

**3 run it, 2 built it.**

Three Meta models run every check:

- **`muse-spark-1.3` (reasons)** — reads 6 keyframes from each walkthrough and inventories the room's movable objects; proposes vocabulary-repair aliases when SAM returns nothing for a word; judges "moved" pairwise from the best before/after frames (position relative to surrounding furniture, since viewpoint differs); writes the risk-triaged report, including a Do this next block for HIGH findings; turns spoken care notes into care watchlist items.
- **`sam-3.1` (proves)** — text-prompted video tracking of every inventoried and watchlist object in both walkthroughs; image re-check of anything that appeared or vanished, on frames from the side where tracking said it was absent; tests Spark's alias phrasings during vocabulary repair.
- **`muse-voice-transcribe-1.0` (listens)** — transcribes spoken care notes and the optional narration recorded while filming; a 10 s note transcribed in ~2.3 s. Hands stay on the phone, filming.

Two more built it:

- **`muse-image-1.0`** — generated the scoreable synthetic test room and its edited "after" version (backpack removed, floor lamp moved, red suitcase added), which became the sample pair and ground truth, when we had no real footage to score against.
- **`muse-wonder-1.0`** — generated the codebase in ~13 reviewed generation rounds from written specs in `build_log/`, with parallel workers (pipeline, server, front-end, voice), each round reviewed and run by a human, plus this red-team critique round. Transcripts: `build_log/wonder_*.md`, critiques: `build_log/critique_wonder.md`, `build_log/critique_spark.md`.

The dependency, not just the list — two verified interactions:

- **Vocabulary repair:** SAM returned nothing for "walker"; Spark proposed "metal walking frame"; SAM found it at c=0.875, and the walker was correctly reported "still in place". Without Spark's new word, SAM is blind to the object the family cares about most.
- **Image re-check:** SAM video tracking missed the armchair in the before clip; the image re-check found it at c=0.75, and the false "armchair added" claim was struck from the report. Without SAM's re-check of its own tracker, Spark's false claim ships.

## Technical challenges

- **Grounding a reasoning model in detections.** The fix is architectural, not a better prompt: a deterministic diff computes presence from SAM tracks (present = 2+ frames at c >= 0.5), and a grounding filter keeps a claim only if SAM evidence agrees (`added`/`removed` must match the SAM label; `moved` needs `present_both` plus a pairwise moved verdict at confidence >= 0.80). Dropped claims stay visible, struck through, with reasons. On our one scoreable test room (3 runs), the raw model invented claims 25–40% of the time; grounding struck every one — a smoke test, not a benchmark.
- **Vocabulary mismatch.** SAM segments what it can name; a caregiver's word ("walker") may not be SAM's word. When tracking returns nothing, Spark proposes alias phrasings and SAM tests them — verified on "walker" → "metal walking frame" at c=0.875.
- **Tracker misses.** Video tracking missed the armchair in the before clip, which would have produced a false "added". SAM image re-checks on keyframes of the supposedly-absent side (a find at c >= 0.5, here 0.75) overturn the label before any claim is written.
- **Viewpoint change.** The two clips are handheld and never pixel-aligned, so "moved" is judged by Spark relative to surrounding furniture, and held to a 0.80 confidence threshold — it remains the weakest call (see Limitations).
- **Keeping re-runs honest and cheap.** Every Responses call is disk-cached by request hash and logged to a cost ledger (`cache/costs.jsonl`), so past checks replay free and instantly. A fresh run on the sample pair takes about 1 minute and about $0.33 (26 SAM requests / ~650 frames per run on the sample).

## Limitations

- Viewpoint differences between handheld clips make "moved" the weakest call.
- SAM recall on small objects is imperfect; a missed detection can flip a label. False negatives matter more than false positives here — a missed "walker moved" is the catastrophic error — and recall on real, cluttered rooms is untested.
- Presence is not safety: a detected object may be unreachable, blocked or not working, and object detection cannot see states or absences such as a loose rug edge or a spill.
- `not_seen` is not missing: it means we could not confirm the object in this video — check before you worry.
- Evidence is boxes, not masks (mask payload encoding is undocumented).
- Clips are capped at 30 s at 5 fps.
- English voice notes only tested.
- Consent: filming is per-visit, with the older adult's knowledge — ask together, film together. Nothing is recorded between visits.
- Not a medical device. Second Look reports room changes; it does not assess health or replace an OT/nurse assessment.
- Evaluation so far is n=1 synthetic pair (3 runs); the 0.80 moved threshold was set after looking at that pair — a smoke test, not a benchmark; real footage is pending.

## Moat

Encircle and Sortly catalog a room but do not diff two visits; fall detectors (watches, pendants, radar) act after a fall. Second Look's moat is the visit-to-visit diff where every claim is grounded in SAM evidence or struck in front of you — drift can create hazards, and the gap between visits is exactly when nobody is looking.

## Draft X post (≤280 characters)

Second Look: film Dad's room on discharge day, film again next visit. We report what drifted — every finding backed by SAM 3.1 evidence, or struck, reason shown. Not a medical device. #MetaAI

## Draft 2-tweet thread

**Tweet 1:** Last month Dad's room was set up safe. This month the walker is out of reach — and nobody noticed. 1 in 4 adults 65+ falls each year, and drift between family visits can create hazards. Second Look compares two phone walkthroughs and shows what drifted.

**Tweet 2:** Every finding carries SAM 3.1 evidence (boxes, frames, confidences) — anything without it is struck, reason shown. On our one scoreable test room (3 runs), the raw model invented claims 25–40% of the time; grounding struck every one — a smoke test, not a benchmark. 3 Meta models run it, 2 built it.
