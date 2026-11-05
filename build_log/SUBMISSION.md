# Second Look — hackathon submission (as drafted for the form)

Meta Global AI Developer Hackathon · Indie track · Push the Frontier · submitted Nov 4, 2026.

- **Repository:** https://github.com/harshitaggarwal01/splatdiff
- **Live demo:** https://harshitaggarwal01.github.io/splatdiff/
- **Demo video:** 2:27, narrated (see VIDEO_SCRIPT.md); link in the submission.

## Project description
Second Look tells a family what changed in an aging parent's room between visits — with proof.

The problem: about 1 in 4 adults over 65 falls each year (CDC), and home hazards are one factor families can actually fix. But the person who visits isn't always the person who worries, and nobody remembers exactly where the walker stood three weeks ago. A walker pushed out of reach or a bag left in the path goes unnoticed.

How it works: film a 20-second walkthrough of the room when it's set up safe (e.g. after a hospital discharge), and again on a later visit — anyone can film. Second Look blurs people and papers, inventories the room, tracks every object through both videos, and reports what was moved, added, removed or left on the floor. High-risk items come first, each with plain "Do this next" steps (ask Dad first; never ask him to move furniture alone).

Why it's trustworthy: every finding carries its evidence — SAM 3.1 boxes, frames and confidences from your own videos — and anything the reasoning model claims that the evidence doesn't support is struck from the report, in front of you, with the reason. On real phone footage of a computer lab, it caught chairs pulled into the aisle and struck a "trash bin added" claim because the first video never showed that corner.

Built for families: a care watchlist (typed or spoken); Dad's own words ("I moved the lamp to read") mark a change as his choice, not an alarm; a live words-only family feed with an agent that answers "Where was his walker last seen?"; updates written for someone nearby, far away, or Dad himself; per-room baselines and reminders; and a glasses simulation where Dad wears the camera and it remembers where he left things. Private by construction: no installed camera, blur before reasoning, raw videos deleted by default.

Honest numbers: on our one scoreable test room the raw model invented 25–40% of claims; grounding struck every one — a smoke test, not a benchmark.

## Use of Meta products
Four Meta models run every check through the Meta Model API (Responses, Files and ASR endpoints); two more helped build it.

- SAM 3.1 (sam-3.1) — the evidence layer: text-prompted video tracking of every object in both walkthroughs (Files API → input_video), image re-checks of anything that seemed to appear or vanish, detecting people and paper documents for blurring, verifying floor clutter, and per-frame detection in the glasses simulation.
- Muse Spark 1.3 (muse-spark-1.3) — the reasoner: room inventory, a coverage check between the two walkthroughs, alias suggestions when SAM doesn't know a word ("walker" → "metal walking frame", then found at 0.875), the "moved?" judge, the risk-triaged report, turning spoken notes into the watchlist, and the family agent (Q&A plus updates for nearby family, far-away family, or Dad).
- Muse Wonder 1.0 (muse-wonder-1.0) — at runtime, second opinions on borderline "moved" calls and a trend across past checks. It also generated the codebase: 30 reviewed generation rounds from written specs, up to five workers in parallel, plus red-team critiques of the idea, logic and UI (build_log/).
- Muse Voice Transcribe (muse-voice-transcribe-1.0) — spoken care notes and narration while filming, with diarization so Dad's own words count; its timestamps also cut the demo video to the voiceover.
- Muse Image 1.0 (muse-image-1.0) — generated the scoreable synthetic test room and its edited "after" version.

The public static demo calls the Meta Model API straight from the browser with the visitor's own key, kept in that tab only.

## Why Meta's models matter
The core idea — every claim proven or struck — needs a detector and a reasoner that check each other, behind one key and one API. SAM 3.1 turns any phrase into boxes and frame numbers, which makes a claim verifiable; Muse Spark reads the room and writes the report, and SAM can overrule it. The verified interactions are the product: SAM's image re-check vetoed its own tracker's false "armchair added"; Spark repaired SAM's vocabulary; Muse Wonder breaks ties on borderline calls. Practical reasons too: image, video and audio input on one API; speech-to-text with diarization; low cost (a fresh check is roughly $0.24–0.44, replays free from cache); standard (non-contributor) model IDs so family footage isn't used for training; and CORS support, so a static page can run the models with the user's own key. Next: Meta's glasses and open-weight models as the path to capture from Dad's own point of view, and to frames that never leave the home.

## Partner technologies
We didn't use Fireworks, Modal or Baseten — everything ran on the Meta Model API. Self-hosting open-weight models through them is on our privacy roadmap.

## Optional answers
- Biggest obstacle: undocumented SAM 3.1 mask encoding (we used boxes), finding the ASR endpoint (/v1/asr/transcribe, WAV only), Spark occasionally returning empty text when reasoning used the token budget, and SAM missing everyday words like "walker" — solved with Spark-suggested aliases.
- Compared with other models: SAM 3.1's text-prompted video tracking was the standout; Spark was fast (3–8 s) and cheap but sometimes needed a retry; Muse Wonder produced multi-file changes in 1–2 minutes.
- What matters most: verifiable, grounded outputs; image, video and audio on one API; cost and latency; privacy terms.
- Hardest to switch: SAM 3.1's text-prompted segmentation and tracking — the evidence-or-struck design depends on it.
- What would stop production use: clear retention and health-privacy terms for home footage, documented mask output, video rate limits and SLAs, and an on-device or self-hosted option so frames never leave the home.
