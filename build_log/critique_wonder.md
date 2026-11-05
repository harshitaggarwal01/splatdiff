# Critique by muse-wonder-1.0

Red-teaming SplatDiff as a judge — first verifying the fall-risk claims and competitor landscape against live sources before I tear into the pitch.## 1. **Is it a real problem?**

- **Yes — falls are frequent, and the home is a legitimate intervention point.** CDC reports that more than 14 million adults 65+, about 1 in 4, fall each year. A 2023 Cochrane review found home-hazard identification/fix programmes reduced fall rates by 26%. CDC STEADI-style checklists specifically target clutter, cords, loose rugs, poor lighting, and lamps within reach of bed — so your lamp/clutter examples are not invented.
- **But your causal chain is overstated.** Falls are driven mainly by strength/balance, medications, vision, hypotension — home hazards are one factor, not *the* story. CDC STEADI itself routes home hazards to an OT evaluation. You detect *object drift*, not fall risk. Say "drift can create hazards," not "we reduce falls."
- **Who feels it, exactly:** the adult child who visits monthly/quarterly and plays detective on arrival ("why is the walker in the hallway?"). Long-distance caregivers: half live 500+ miles away; 38% visit monthly, 53% several times a year. That's your cadence problem and your user in one stat.
- **What they do today instead — and none of it is your product:**
  - *Reactive fall detection:* Apple Watch, pendants, Vayyar radar — detects the fall after it happens.
  - *Continuous cameras/sensors:* Nest, motion sensors — and the market is fleeing cameras: camera-free sensor systems are now the top recommendation precisely because bedrooms/bathrooms are off-limits to lenses. You must answer "why is your camera okay?"
  - *Static inventory apps:* Encircle (room-by-room photo/video baseline, built for insurance) and Sortly (AI photo inventory) already do "film the room, catalog objects" — but neither *diffs two visits*. That diff is your only moat. Say so.
  - *Free default:* eyeballing, phone calls, a cleaner/aide's texts, paper STEADI checklist. Your competitor is a daughter's eyes + anxiety, price $0.

## 2. **Who and when** — 3 credible users

1. **The monthly-visit daughter after a hospital discharge.** Day 0: films the bedroom/bathroom path as the "safe setup" the OT prescribed. Visit 2, three weeks later: films again. Did the walker migrate? Did clutter colonise the bed-to-bathroom path? **← Lead the pitch with her.** Concrete, emotional, matches your cadence and your watchlist mechanic.
2. **Home-care nurse / OT doing follow-up visits.** Films at intake and at each scheduled visit; the print report goes in the care record. Most *credible repeat user* — she already does STEADI home checks — but she's a Phase-2 user (procurement, liability). Mention in one line, don't lead.
3. **Siblings rotating visits / a home aide between family visits.** Aide films a 20-second walkthrough after each cleaning visit; siblings get the diff remotely. This is actually your best *retention* story (weekly data!) — but requires the parent to accept a stranger filming, so it's your expansion story, not the opener.

- **Kill the landlord/move-out angle from the pitch.** It's a different buyer, different emotional register, and it makes judges think you don't know who this is for. One line in the README "same engine applies to…" is fine. Rental inspection also already has Encircle-class tools.
- **Honest timing answer you must give before a judge asks:** nobody films two walkthroughs on day one. Value starts at visit #2. Your onboarding copy must sell the *baseline* ("Film today's safe room. Next visit, we show you what drifted").

## 3. **The name.**

- **Rename. 'SplatDiff' is actively harmful, twice over.** (a) It promises Gaussian splatting / 3D reconstruction you don't do — the first technical judge question will be "where are the splats?" and your answer ("my prior research") burns 20 seconds and credibility. (b) Worse: *splat is the sound of a person falling.* You are one judge's wince away from "they named a fall-prevention product after grandma hitting the floor." In a care-dossier, serif-and-paper brand, it's dissonant.
- **Alternatives (in order):**
  1. **Still in Place** — names the watchlist promise verbatim ("walker — still in place"). Warm, dossier-appropriate. Tagline carries the tech.
  2. **RoomDrift** — names the actual phenomenon (slow drift between visits); tech-neutral, works for rental too.
  3. **What Changed in Mom's Room** — your masthead is already your best name. Descriptive, demo-friendly, zero explanation needed.
- Keep "SplatDiff" only as the engine name in one README footnote if you're attached. Do not open a 3-minute video defending a name.

## 4. **Logic gaps**

- **Why video at all?** Your own pipeline reduces video to 6 keyframes for Spark; SAM video tracking is the only true video consumer. A judge will ask "why not 6 photos — cheaper, sharper, no 30s cap?" Your real answer: video gives SAM temporal evidence (2+ frames @ c≥0.5) and coverage without aiming. Say that, or the video looks like theatre. Your sample isn't even video — it's Ken Burns pans over Muse Image stills.
- **Why two walkthroughs vs. a fixed camera?** Fixed camera = continuous, catches drift the day it happens; yours catches it *up to a month later, after the exposure window*. Your only defences: no installed hardware, no 24/7 surveillance of a bedroom, consent per-filming. Lead with privacy-as-feature or lose this exchange. Camera-free radar (Vayyar) already occupies "private + continuous".
- **Presence ≠ safety — your deepest product flaw.** "Walker in_place" means a box appeared in 2 frames. It does not mean reachable, unblocked, brakes on, or the path to it clear. A green `in_place` badge will manufacture false reassurance. Same for lamp: present ≠ plugged in ≠ working bulb. You detect *objects*, hazards are *states and absences* (missing grab bar, loose rug edge, spill).
- **`not_seen` is doing dangerous work.** Not seen ≠ missing ≠ safe. In the report, `not_seen` next to a walker will be read as an alarm or ignored — both bad. It needs plain-language framing: "We couldn't see it in this video — check the corner by the bed."
- **What happens after HIGH? Nothing. This is the biggest gap.** No "here's what to do," no "mark as fixed," no notify-a-sibling, no re-check prompt, no escalation if it's still moved next visit. A report that ends at detection is a demo; a loop that ends at *resolution* is a product. Judges score Impact — impact lives in the fix, not the finding.
- **Consent and privacy of the older adult.** You're filming a possibly cognitively-impaired person's bedroom, sending frames to cloud APIs, storing annotated frames, and the *adult child* is the user — the filmed person may never have consented. Also visitors, aides, medication labels, documents in frame. You have zero copy on this. One judge question ends you.
- **False negatives >> false positives in harm, your framing is inverted.** Your whole pitch celebrates killing false *positives* (struck claims). But a missed "walker moved" is the catastrophic error, and your n=1 synthetic eval can't speak to recall in a real cluttered room. A struck claim is charming; a silent miss is a lawsuit.
- **Liability.** High/medium/low "fall-risk triage" *is* health advice wearing a disclaimer. "Not a medical device" in Limitations while the UI sorts grandma's hazards by risk is contradictory; a plaintiff's lawyer (or a judge) will notice.
- **Viewpoint/moved:** you admit it's the weakest call — and "moved" is 1 of your 3 ground-truth demo items. You're demoing your least reliable feature as a headline.

## 5. **Presentation gaps**

- **Your hero moment is buried at ~1:50–2:35.** The ink-strike on the false "armchair added" claim is the single most memorable, frontier-y thing you have. Move it to ~0:45. The vocabulary-repair moment (walker → "metal walking frame," c=0.875) is your second hero — pick *one* as hero (the strike; it's visual), make the other a 10-second beat.
- **Cut list:** the 55-second narrated pipeline tour (0:55–1:50) is half your runtime spent on plumbing — ffmpeg, 5fps, 26 SAM requests, 650 frames. Judges don't score plumbing live. Compress to 20 seconds of accelerating chips; spend the freed 35s on (a) the daughter story, (b) "what we told her to do about the HIGH finding."
- **The synthetic room is your credibility ceiling.** First judge thought: "Ken Burns over an AI image — does it work on a real phone video of a real messy room?" You currently answer this at 2:35 in a limitations mumble. Pre-empt it at 0:20: "This demo room is synthetic so we can score it. Here's a real room, filmed this week" — even 8 seconds of real footage inoculates you.
- **Never say "precision and recall 1.00" without the caveat in the same breath.** You do pair them — good — but "1.00" is what gets screenshotted and mocked. Say "3-for-3 on a test we built to be scor able, raw model was wrong 25–40% of the time without grounding."
- **$0.33 and cost tickers impress nobody** and invite "so it's a paid API wrapper?" Keep cost to the closing slide, one line.
- **Reading risk:** "Struck from the report" needs zero explanation — great. "Vocabulary repair," "concept chips with L/T marks," "grounding filter" all need explanation. Max 2 jargon terms in 3 minutes.

## 6. **Meta-tooling story**

- **As told, it's model-stuffing and judges can smell it.** Of your "five models": Muse Image generated *test data*, Muse Wonder wrote *code* — neither is in the product a user touches. Padding the count invites "so really it's two models and a transcription API." That damages your real story.
- **Your real story is genuinely frontier — lead with the loop, not the list:** *models checking each other.* Spark proposes → SAM verifies or vetoes → Spark teaches SAM new words when SAM is blind ("walker" → "metal walking frame") → SAM's image re-check overturns its own tracker. That's an agent-verification architecture, squarely "Push the Frontier."
- **Reframe exactly:** "Three Meta models run the check. Two more built it." Runtime: Spark (reasons), SAM 3.1 (proves), Voice Transcribe (listens). Making-of footnote: Muse Image built our scor able test room; Muse Wonder built the codebase in 11 reviewed rounds. Same facts, zero stuffing smell, and Wonder becomes a *process* flex instead of a fake runtime dependency.

## 7. **Top 8 fixes** (ranked by judging impact ÷ minutes)

1. **Shoot one real phone walkthrough pair** — your actual room, move a lamp + bag, film handheld twice. Show 10–15s in-video even if the full pipeline run uses the sample. Kills the #1 credibility objection. *~25 min, code-light (just add clip/UI sample button if time; else video-only).*
2. **Reframe the Meta story to "3 run it, 2 built it"** in README, submission, and video close. Exact copy: *"Three Meta models run every check — Spark reasons, SAM 3.1 proves, Voice listens. Two more built SplatDiff: Muse Image made our scor able test room, Muse Wonder wrote the code."* *~10 min, copy-only.*
3. **Add a "What to do next" block under every HIGH finding** + resolution state. Exact copy for walker: *"Do next: Move the walker back within arm's reach of the bed. Ask [Mom] to show you she can reach it. Then re-film this corner — we'll confirm it's back."* Add a "Mark as sorted" button if 15 min of code exists; copy-only version still lands. *~10–20 min, copy (+small code optional).*
4. **Rename to Still in Place** (or keep masthead name). Find-replace in UI/README/script; one footnote: *"Engine internally codenamed SplatDiff."* Removes the splat/fall wince and the where-are-the-splats question. *~15 min, copy-only.*
5. **Move the ink-strike hero to 0:45; cut live-pipeline narration from 55s to 20s.** New structure: hook (0:00) → real room (0:20) → watchlist voice note (0:35) → strike moment (0:45) → walker vocab repair (1:30) → HIGH finding + what-to-do (2:00) → 3+2 models + limits (2:40). *~15 min, script-only.*
6. **Add honesty/consent copy to report + UI.** Exact lines: under `not_seen`: *"Not seen in this video — not the same as missing. Check before you worry."* Under `in_place`: *"Seen where it should be. We can't check it's reachable or working."* Intake: *"Only film rooms [name] is happy to share. Videos are processed to find objects; you can delete a check anytime."* *~10 min, copy-only.*
7. **Answer "why video, why not a camera" before it's asked** — one line in video + README: *"No camera watching her sleep, no hardware to install. You film for 20 seconds when you visit; SAM uses the motion to be sure, not sure-ish."* Contrast is fair: always-on monitoring is exactly what families reject in bedrooms. *~5 min, copy-only.*
8. **Demote the landlord use case and the 1.00 scores.** Submission description: delete "same engine fits rental"; replace "precision 1.00 and recall 1.00" with *"on our one scor able test room, the raw model invented claims 25–40% of the time; grounding struck every one."* The hallucination number is the impressive one. *~5 min, copy-only.*

Total: ~80–95 min of work, but #1+#2+#3+#5 alone (~60 min) capture most of the judging upside. If forced to cut one, cut the rename (ship it in the video verbally: "Still in Place, built on our SplatDiff engine").

## 8. **One-sentence pitch** and **15-second hook**

**One-sentence pitch:** "Still in Place compares two short phone walkthroughs of your parent's room between visits and reports what was added, removed or moved — every finding backed by SAM 3.1 evidence, and every claim it can't prove struck from the report in front of you."

**15-second hook (say this verbatim, over before/after frames):** "Last month this room was safe. This month the walker has been pushed out of reach — and nobody noticed. One in four adults over 65 falls each year. Film the room when you visit; we show you exactly what drifted — and we show our evidence, or we strike the claim."
