# SplatDiff — submission draft

**Project name:** SplatDiff

**One-line tagline:** What changed in this room? Two phone walkthroughs in, a change report out — every finding backed by SAM 3.1 evidence, or struck from the report.

## Description (150 words)

SplatDiff helps a family caregiver check an older parent's room between visits. You film a short walkthrough on each visit, add a care watchlist such as walker, pill organizer and phone, typed or spoken, and SplatDiff compares the two videos. It reports what was added, removed or moved, with before and after frames, SAM 3.1 boxes, frames seen and confidences as evidence. Any finding without that evidence is shown struck from the report with the reason, rather than presented as fact. Findings are ordered by the care watchlist and triaged high, medium or low through a fall-risk lens. A live view shows each stage and the running cost. In three runs on one synthetic pair, the grounded report had precision 1.00 and recall 1.00, with no hallucinated kept claims. It is a smoke test, not a benchmark; real footage is pending. Results describe this tested pair only, not broader performance.

## How we used Meta models

- **`muse-spark-1.3`** — reads 6 keyframes from each walkthrough and inventories the room's movable objects; proposes vocabulary-repair aliases when SAM returns nothing for a word; judges "moved" pairwise from the best before/after frames (position relative to surrounding furniture, since viewpoint differs); writes the risk-triaged report (high/medium/low through a fall-risk lens); turns spoken care notes into care watchlist items.
- **`sam-3.1`** — text-prompted video tracking of every inventoried and watchlist object in both walkthroughs; image re-check of anything that appeared or vanished, on frames from the side where tracking said it was absent; tests Spark's alias phrasings during vocabulary repair.
- **`muse-voice-transcribe-1.0`** — transcribes spoken care notes and the optional narration recorded while filming; a 10 s note transcribed in ~2.3 s.
- **`muse-image-1.0`** — generated the synthetic test room and its edited "after" version (backpack removed, floor lamp moved, red suitcase added), which became the sample pair and ground truth.
- **`muse-wonder-1.0`** — generated the codebase in ~11 rounds from written specs in `build_log/`, with up to 2–4 workers in parallel (pipeline, server, front-end, voice); every round was reviewed and run by a human. Transcripts: `build_log/wonder_*.md`.

Two verified interactions between the models:

- **Vocabulary repair:** SAM returned nothing for "walker"; Spark proposed "metal walking frame"; SAM found it at c=0.875, and the walker was correctly reported "still in place".
- **Image re-check:** SAM video tracking missed the armchair in the before clip; the image re-check found it at c=0.75, and the false "armchair added" claim was struck from the report.

## Technical challenges

- **Grounding a reasoning model in detections.** Muse Spark's raw claims on the synthetic pair had precision 0.60–0.75 and a 25–40% hallucinated-claim rate. The fix is architectural, not a better prompt: a deterministic diff computes presence from SAM tracks (present = 2+ frames at c >= 0.5), and a grounding filter keeps a claim only if SAM evidence agrees (`added`/`removed` must match the SAM label; `moved` needs `present_both` plus a pairwise moved verdict at confidence >= 0.80). Dropped claims stay visible, struck through, with reasons.
- **Vocabulary mismatch.** SAM segments what it can name; a caregiver's word ("walker") may not be SAM's word. When tracking returns nothing, Spark proposes alias phrasings and SAM tests them — verified on "walker" → "metal walking frame" at c=0.875.
- **Tracker misses.** Video tracking missed the armchair in the before clip, which would have produced a false "added". SAM image re-checks on keyframes of the supposedly-absent side (a find at c >= 0.5, here 0.75) overturn the label before any claim is written.
- **Viewpoint change.** The two clips are handheld and never pixel-aligned, so "moved" is judged by Spark relative to surrounding furniture, and held to a 0.80 confidence threshold — it remains the weakest call (see Limitations).
- **Keeping re-runs honest and cheap.** Every Responses call is disk-cached by request hash and logged to a cost ledger (`cache/costs.jsonl`), so past checks replay free and instantly, and the live UI can show a running cost per stage over SSE.

## Limitations

- Viewpoint differences between handheld clips make "moved" the weakest call.
- SAM recall on small objects is imperfect; a missed detection can flip a label.
- Evidence is boxes, not masks (mask payload encoding is undocumented).
- Clips are capped at 30 s at 5 fps.
- English voice notes only tested.
- Not a medical device.
- Evaluation so far is n=1 synthetic pair (3 runs); the 0.80 moved threshold was set after looking at that pair. This is a smoke test, not a benchmark; real footage is pending.

## Draft X post (≤280 characters)

SplatDiff compares two phone walkthroughs of a parent's room and reports what moved, appeared or vanished — every finding backed by SAM 3.1 evidence, or struck from the report. Built with five Meta models. A fresh sample run: ~$0.33.

## Draft 2-tweet thread

**Tweet 1:** About 1 in 4 adults 65+ falls each year, and slow drift at home — a walker pushed out of reach, clutter on the floor — goes unnoticed between family visits. SplatDiff compares two phone walkthroughs of the room and reports what was added, removed or moved.

**Tweet 2:** Every finding carries SAM 3.1 evidence (boxes, frames, confidences) — anything without it is struck from the report, reason shown. On our synthetic pair: grounded precision/recall 1.00 across 3 runs, ~$0.33 per fresh run. Built with muse-spark-1.3, sam-3.1, muse-voice-transcribe-1.0, muse-image-1.0 and muse-wonder-1.0.
