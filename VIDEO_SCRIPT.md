# SplatDiff — 3-minute demo script

**0:00–0:20 — Problem.** "You leave your elderly parent's home and wonder: did anything change? Is the walker still within reach? SplatDiff answers 'what changed in this room?' from two phone videos — and it refuses to hallucinate."

**0:20–0:50 — Clips.** Show the BEFORE and AFTER sample clips side by side. Point out: blue backpack gone, floor lamp moved next to the armchair, red suitcase appeared. "A vision-language model alone would happily invent changes too. We don't let it."

**0:50–1:50 — Live run.** Open the Gradio UI, click *Load sample pair*, then *Run SplatDiff*. Narrate the pipeline as progress messages appear: ffmpeg normalisation caps each clip at 150 frames; Muse Spark 1.3 (`muse-spark-1.3`) inventories up to 12 movable objects from 6 keyframes per video; SAM 3.1 (`sam-3.1`) tracks every concept in both videos concurrently; a deterministic diff computes presence (≥2 frames at confidence ≥0.5); Spark then judges 'moved' relative to surrounding furniture, since the camera viewpoint differs.

**1:50–2:30 — Dropped claim + eval.** Show the report: kept claims with SAM frames/boxes/confidences, annotated frames (green added, red removed, orange moved) — and a dropped claim struck through with its reason. "Grounded-or-dropped: if SAM doesn't back it, you see it dropped." Show `outputs/eval.md`: precision/recall/F1 for raw Spark claims vs grounded kept claims, and the hallucinated-claim rate falling after the filter.

**2:30–3:00 — Stack, cost, limits.** "Meta-specific stack: Muse Spark 1.3 for reasoning, SAM 3.1 for grounding, Muse Image 1.0 (`muse-image-1.0`) for the synthetic sample. A run costs roughly fifty cents to a dollar, every call is logged to `cache/costs.jsonl`, and caching makes re-runs free. Honest limits: viewpoint change, small-object recall, boxes not masks, 30-second cap. SplatDiff: every claim grounded — or dropped."
