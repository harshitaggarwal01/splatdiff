# Submission draft — final

## Name

**Second Look**

## Tagline

What changed in Dad's room? Two phone walkthroughs in, a grounded change report out — every finding backed by SAM 3.1 evidence, or struck, reason shown.

## Description (150 words)

Second Look helps families notice what changed in an older parent's room between visits. A daughter films a safe baseline — walker by the bed, lamp within reach, floor path clear — then films again next visit. Muse Spark reasons about the room, SAM 3.1 proves each finding with boxes, frames and confidences, Muse Voice Transcribe listens to spoken watchlists and Dad's own words, and Muse Wonder gives second opinions on borderline calls. Unsupported claims are struck, reason shown. Findings include watchlist status, floor clutter, coverage gaps, privacy blurring, and a plain next step. Words-only updates reach family live, without pictures. A simulated glasses view shows Dad's point of view and honest last-seen memory. It is not a medical device, fall detector, or replacement for professional assessment. If we cannot show where we saw it, we do not say it to family or Dad. That rule always protects trust during every check.

## The product

- **Care dossier app (`/app`)** — rooms, who filmed it, a saved baseline per room, "This is the new setup" re-baselining, record-with-this-phone capture, watchlist typed or spoken, Needs-attention banner, Do this next (ask Dad first), Mark as sorted, Send to family, Print, Past checks, delete a check, `.ics` re-film reminders. Raw videos deleted by default.
- **Privacy first** — people and paper documents blurred by SAM before any frame is stored, shown, or sent to Muse Spark (2 documents blurred on the sample). Muse Voice Transcribe with diarization means Dad's own words ("I moved the lamp so I can read by my chair") mark a finding as his choice, low risk.
- **Grounded checks** — coverage score with retake tip (0.9 on the sample), grounded floor-clutter check, SAM vocabulary repair (walker → "metal walking frame", c 0.875), image re-check strikes (armchair found in BEFORE at c 0.75), Muse Wonder second opinions on borderline "moved" calls, and a cross-visit trend sentence.
- **Family feed (`/family`)** — words only, never pictures; live over SSE within a minute; opt-in browser notifications; "Ask about Dad's room" agent grounded in the feed with citations and "seen where it was" language; "Write an update for" nearby / far away / Dad — written to him, not about him.
- **Glasses simulation (`/glasses`)** — "Dad's point of view": a working simulation, not a Meta product integration. Real SAM 3.1 calls per frame (~0.9 s), a whisper ("Walker — on your left, close."), and a tab-only "Where did I leave it?" last-seen memory that answers "last seen … not seen since." Live glasses streaming via Meta's Wearables Device Access Toolkit is **roadmap**.
- **Falls** — a fall alert from any sensor (watch, pendant, radar or glasses) can land on the family feed after an "Are you OK?" check-in. Glasses are a poor fall sensor (night/bathroom, charging, head motion ≠ body impact); fall detection is partner territory and is simulated in the demo. Second Look does not detect falls.
- Product page at `/` with Try it now. Run with `python server.py`.

## Models — 4 run it, 2 built it

**Run it:** `muse-spark-1.3` reasons (inventory, coverage, moved judgements, report, feed wording); `sam-3.1` proves (video tracking, image re-checks, privacy blur, floor clutter, glasses-simulation frames); `muse-voice-transcribe-1.0` listens (spoken watchlists, diarized care notes, Dad's own words); `muse-wonder-1.0` gives runtime second opinions on borderline "moved" calls and writes the cross-visit trend sentence.

**Built it:** `muse-image-1.0` generated the synthetic test room; `muse-wonder-1.0` wrote the code — ~25 reviewed generation rounds with up to 5 parallel workers, plus 3 red-team critique rounds by Muse Wonder and Muse Spark in `build_log/`, one of which forced the glasses-as-simulation positioning.

## Challenges

- **Grounding, not prompting.** A deterministic diff (present = 2+ frames at c ≥ 0.5) plus a filter that strikes any Spark claim SAM evidence doesn't support — added/removed must match the SAM label; "moved" needs present-in-both plus a moved verdict, with a Wonder second opinion when borderline. Struck claims stay visible with reasons.
- **Vocabulary mismatch.** SAM segments what it can name; "walker" returned nothing until Spark proposed "metal walking frame" (c 0.875).
- **Tracker misses.** Video tracking missed the armchair in BEFORE; SAM's image re-check found it (c 0.75) and struck a false "added" claim.
- **Consent and privacy by architecture.** Per-visit filming, blur-before-storage, delete-by-default video, words-only family feed — surveillance-shaped features were cut, not policy-patched.
- **Honesty under demo pressure.** The glasses pivot critique (`build_log/critique_pivot_glasses.md`) killed a five-feature glasses pitch; what survived is a labelled simulation, a roadmap line, and falls handed to partners.

## Limitations

One synthetic room, 3+ runs — a smoke test, not a benchmark. The raw model invented 25–40% of claims; grounding struck every one, but real cluttered rooms are untested and recall there (a missed "walker moved" is the catastrophic error) is unknown. "Moved" is the weakest call under viewpoint change. Presence is not safety; last-seen is not current location; nothing here detects falls, assesses health, or replaces an OT assessment. The glasses experience is simulated; live Wearables Device Access Toolkit streaming is roadmap. A fresh sample check takes ~1–1.5 min and ~$0.24–0.33; replays are cached, free and instant.

## X post (≤280 characters)

Second Look: film Dad's room this visit, film again next visit. We report what drifted — every finding backed by SAM 3.1 evidence, or struck, reason shown. If we can't show where we saw it, we don't say it. Not a medical device.

## 2-tweet thread

**1/** The person who visits isn't always the person who worries. Second Look compares two phone walkthroughs of Dad's room and reports what was added, removed or moved — watchlist first, floor checked, papers and people blurred before anything is stored or shared.

**2/** Every claim carries SAM 3.1 boxes, frames and confidences, or it's struck in front of you. On one synthetic room (3+ runs) the raw model invented 25–40% of claims; grounding struck every one — smoke test, not a benchmark. 4 Meta models run it, 2 built it.
