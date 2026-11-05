# Second Look — product context

_Written from the hackathon brief and the user's choices on 2026-11-04 (aging-parent story, Care dossier look), revised after the red-team critiques in `build_log/critique_wonder.md` and `build_log/critique_spark.md`. Assumptions are marked._

## What it is
A room-change checker for families caring for an older adult at home. Film the parent's room on two visits with a phone. Second Look compares the walkthroughs and reports what was added, removed or moved. Every finding is backed by Meta SAM 3.1 detections, and a finding without evidence is struck from the report, with the reason shown.

SplatDiff is the engine codename from the author's earlier 3D-scene research; this product uses no Gaussian splats.

## Who it is for
- **Primary (lead the pitch with her):** the daughter of Dad, 82, who lives alone, after a hospital discharge or a near-miss. The hospital OT said "walker must stay next to the bed, lamp within reach, path clear." She films that OT-approved safe setup as a baseline on discharge day, then re-films on her next visit, a few weeks later. Did the walker migrate? Did clutter colonise the bed-to-bathroom path? She has the watchlist in her head already.
- **Credible repeat user (Phase 2, one line):** home-care nurse / OT doing follow-up visits — films at intake and at each scheduled visit; the print report goes in the care record. She already does home-safety checks, but procurement and liability make her a Phase-2 user.
- **Expansion:** siblings rotating visits, and a home aide between family visits who films a short walkthrough so siblings get the diff remotely — the best retention story, but it requires Dad to accept someone else filming, so it is not the opener.
- The same engine applies to rental move-out inspections in one line only; it is a different buyer and is not the pitch.

Nobody films two walkthroughs on day one, and nobody does routine ambient filming unprompted. The trigger is a scare, a discharge, or a new aid. Value starts at visit #2, so onboarding sells the baseline: "Film today's safe room. Next visit, we show you what changed."

## Why it matters
Falls are common among older adults (CDC: about 1 in 4 adults over 65 fall each year), and home hazards are a modifiable risk factor. Slow changes go unnoticed: a walker pushed out of reach, clutter on the floor, a lamp moved away from the bed. Those changes can create hazards — we do not claim we reduce falls. Falls are driven mainly by strength and balance, medications, vision and blood pressure; home hazards are one factor, and an OT assessment remains the gold standard. Families need a calm, honest answer, not an AI guess.

What families do today: eyeballing on arrival, phone calls, a cleaner's texts, photos to siblings, a paper checklist — or reactive fall detection (watches, pendants, radar) that acts after a fall. Encircle and Sortly catalog a room but do not diff two visits; that visit-to-visit diff, grounded or struck, is the moat.

## Principles
- **Trust over cleverness:** grounded or dropped. Show the receipts.
- **Calm over alarm:** findings are triaged by risk in plain language, and every HIGH finding ends in a next step, not just an alarm.
- **The family's words:** a care watchlist, typed or spoken, decides what matters most.
- **Presence is not safety:** "seen where it should be" never claims reachable, unblocked or working. `not_seen` means "we couldn't confirm it in this video — check before you worry," never missing and never safe.
- **False negatives matter more than false positives:** a struck false claim is charming; a silent missed "walker moved" is the catastrophic error. Recall on real cluttered rooms is not yet measured (one real pair so far), and we say so.
- **Consent per visit:** ask together, film together. No installed camera, nothing recording between visits. Only film rooms Dad is happy to share.

## The loop after a finding
A report that ends at detection is a demo; the loop ends at resolution. Every HIGH finding carries:
1. **Do this next** — plain steps, e.g. for the walker: "Move the walker back within arm's reach of the bed. Ask Dad to show you he can reach it. Then re-film this corner — we'll confirm it's back."
2. **Mark as sorted** — once the family has done it.
3. **Re-check next visit** — the item is watched again on the next walkthrough; if it is still moved, it surfaces again.

Second Look is not a medical device. It reports room changes; it does not assess a person's health or replace a professional safety assessment.

## Meta models — 4 run it, 2 built it
- **Run it:** `muse-spark-1.3` reasons (inventory, aliases, moved judge, report), `sam-3.1` proves (video tracking, image re-check), `muse-voice-transcribe-1.0` listens (spoken care notes with diarization, ~2.3 s for a 10 s note), `muse-wonder-1.0` gives second opinions on borderline "moved" calls and a trend across visits.
- **Built it:** `muse-image-1.0` made the scoreable synthetic test room (backpack removed, floor lamp moved, red suitcase added); `muse-wonder-1.0` generated the codebase over 30 reviewed generation rounds with up to 5 parallel workers; Muse Wonder and Muse Spark wrote 6 red-team critiques (`build_log/`).
- **Verified dependencies:** SAM returned nothing for "walker"; Spark's alias "metal walking frame" let SAM find it at c=0.875. SAM video tracking missed the armchair in the before clip; its image re-check found it at c=0.75 and the false "armchair added" claim was struck.

## Honest evidence position
On our one scoreable test room (3 runs), the raw model invented claims 25–40% of the time; grounding struck every one — a smoke test, not a benchmark. A fresh run on the sample pair takes about 1 minute and about $0.33; past checks replay free from cache.

## Surfaces
- Web demo (`web/`, served by `server.py`). Mode: Operate (a task: check the room), with a Read-quality report. Buttons: *Use the sample room*, *Check the room*, *Past checks*, *Speak your care notes*.
- Gradio fallback (`app.py`).

## Brand tone
A warm, careful family record: paper, ink, serif headlines. Never a neon AI dashboard.
