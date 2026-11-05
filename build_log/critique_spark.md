# Critique by muse-spark-1.3

Red-teaming this as your OT + daughter duo — checking what's real, what's shaky, and what to fix before the deadline.1. **Is it a real problem?**
- **Yes, falls + drift are real, routine filming is not.** More than 1 in 4 adults 65+ falls each year, most falls happen at home and >30% are caused by environmental hazards like rugs, cords, dim stairs. OT view: the killers are unglamorous — cluttered walkways, poor lighting, furniture blocking walker clearance, walker fit, lighting, clutterกลับ.
- **Who feels it acutely:** daughter visiting every other weekend who gets the 9pm “Dad’s fine” phone call and has no way to know if walker migrated, lamp moved from bedside, clutter built up. AARP research: most adult children living within 100 miles visit only every 4-6 weeks; 63M Americans now serve as family caregivers — gap between visits is the anxiety window.
- **Against — frequency mismatch:** Your primary says “weekly or less.” Real behavior at that cadence is *look while I’m there*, not *film two 30s systematic pans*. No daughter films her 82-year-old dad’s bedroom twice a month unprompted. Filming feels like surveillance.
- **What they do today instead:** OT home safety assessment is gold standard because it evaluates function, not just floor plans — OT does room-by-room checklist, grab bars, lighting, rearrange furniture to prevent falls. Family version: photos to siblings on WhatsApp, phone check-ins, sticky-note “leave walker here!”, cheap Wyze camera, or nothing until a fall/post-discharge scare forces action.
- **OT verdict:** Don’t pitch “routine monitoring.” Pitch “answer after a scare / discharge / new walker.” That’s when a family will actually pull out a phone.

2. **Who and when — 3 most credible users**
- **1. Worried daughter after a near-miss [LEAD THE PITCH]:** Dad 82, lives alone, had a wobble getting to bathroom at night. Hospital OT said “walker must stay next to bed, lamp within reach, path clear.” Daughter films 20s baseline on discharge day, films again 2 weeks later when she visits. She has a watchlist in her head already. Concrete, emotional, explains why *two* videos exist. Wins Impact 30% + Demo 25%.
- **2. Sibling-accountability filmer:** Brother in Seattle, sister local every other weekend. Local films to prove “look, I checked” and sends print report + copy summary. Past-checks replay matters here. Use-case: monthly, not weekly. Second slide, not lead.
- **3. Move-out inspector / landlord:** Actually films move-in vs move-out already as norm. Backpack removed / suitcase added / lamp moved maps perfectly. Most natural filming behavior, but kills frontier-care story and Impact. Keep as “same engine, second market” one-liner only.
- **When would someone *actually* film two walkthroughs?** Only with a trigger: post-fall, post-hospital, new aid, or hired aide starts. Nobody does ambient bi-weekly pans. Rewrite copy from “every visit” to “baseline + re-check.”

3. **The name. Is ‘SplatDiff’ right?**
- **No for product, yes as engine codename.** Product does zero splats; SAM 3 is text-prompted detection/segmentation/tracking, not Gaussian splats. Name promises 3D tech you explicitly disclaim as “no code/data/figures used.” Judges in Push the Frontier will ask “where’s the splat?” and you burn 30s explaining history.
- **Tone clash:** UI is “warm, careful family record: paper, ink, serif.” SplatDiff sounds neon AI dashboard. Daughter would never trust/print “SplatDiff report” for Dad. OT would never chart it.
- **Verdict: Rename product, keep SplatDiff as engine in README/footnote.** Copy-only fix.
- 3 alternatives, all plain-language + trust:
  - **StayPut** — `StayPut — is the walker still where it should be?` Matches your best feature: must-stay-put watchlist.
  - **Second Look** — `Second Look — what changed since last visit, with receipts.` Calm, family, explains two videos.
  - **Room Receipt** — `Room Receipt — before/after frames, boxes, confidences. Grounded or dropped.` Leans into your “show receipts” principle.

4. **Logic gaps**
- **Why video not 2 photos?** You never justify 5fps / 150 frames / 26 SAM requests. Daughter ask: why can’t I snap bedside + doorway? You need one line: pan catches occlusions walker behind chair, clutter on floor. Otherwise video looks like cost-bloat.
- **Why not a $30 fixed camera?** If worry is continuous, fixed camera wins. Your answer must be: no install, no surveillance feeling, consent per visit, works for distant families. Say it.
- **Consent / privacy of older adult:** Zero mention. Filming Dad’s bedroom every visit without his agency is creepy and a judge red flag. Where’s “ask Dad, film together, delete after”? Add consent line or lose trust.
- **What happens after HIGH?** Walker out of reach = HIGH — then what? No next step, no “call, move back, OT referral,” no escalation. Calm over alarm fails if you alarm with no action. Add “Do this next: 1-2-3.”
- **Viewpoint change makes “moved” shaky:** You admit moved is weakest, judged relative to furniture not pixels. But then you sell moved lamp as core finding. OT: lamp 6 inches vs camera 2 feet left look identical. Threshold 0.80 set after seeing n=1 pair = overfit.
- **False negatives > false positives:** Struck section celebrates killing false alarms, but miss (walker gone, SAM misses small/pill organizer) can mean fall. You report `not_seen` but daughter reads that as safe. Need “we didn’t see it, not it’s fine.”
- **Liability / medical device:** You have “Not a medical device” buried. Front it. OT never delegates safety to boxes, not masks, 30s cap, English-only voice.
- **Inventory vs watchlist confusion:** If watchlist is “always tracked even if inventory misses,” why have inventory at all? Why 12 objects max? Explains hallucinated-claim rate 25-40% raw — Spark invents, SAM vetoes.

5. **Presentation gaps — 3-min video**
- **Lead with synthetic room = instant distrust:** Muse Image stills + Ken-Burns pan is visibly fake. If first 20s is fake living room, judge thinks fake results. Must label “synthetic test — real phone footage pending” on screen, not just in caveats.
- **Don’t open with hook + stats + ground truth puzzle:** 0:15-0:35 “remember 3 changes + watch for 4th claim” is a memory test. Cut. Start with struck armchair payoff.
- **Hero moment (make this 0:00-0:30):** Ink-strike animation crossing out “armchair added” + voiceover “video tracking missed it, image re-check found it at 0.75.” That *is* grounded-or-dropped. Then walker alias “walker → metal walking frame at 0.875.” Two verified model interactions beat 5-model list.
- **Cut that will bore/confuse:** live SSE cost ticking, “26 requests / 650 frames,” L/T marks, “vocabulary repair,” ledger of models/cost, Past checks drawer tour, Gradio fallback mention. Judges don’t care cost ledger ticks up. Show final $0.33 once.
- **Confusing copy:** Masthead ‘What changed in Mom’s room’ — assumes Mom, assumes gender, infantilizing for 82-yr-old father. ‘Learning family’s words’ — jargon. ‘Struck from report’ — sounds punished. Rename “Checked and cleared.”
- **Eval slide danger:** “precision/recall 1.00, 0% hallucination” on n=1 synthetic pair screams overclaim. Say “smoke test on 1 pair, 3 runs” in same breath, on screen.

6. **Meta-tooling story — 5 models or stuffing?**
- **Today looks like stuffing:** SAM 3 text-prompted tracking all instances at once and Spark reasoning are core. Voice transcribe (10s in 2.3s) is nice hands-free-while-filming. But Image only made fake test data, Wonder only wrote code — every team can claim those. Listing 5 equally invites “2 are scaffolding.”
- **Reframe as 3+2, not 5 equal:**
  - Copy to use: *“3 models do the check, 2 made the check possible.”*
  - Working loop: Spark proposes → SAM 3.1 grounds → Spark judges risk; Voice feeds watchlist because hands are holding phone filming.
  - Scaffolding, disclosed: Image built synthetic ground-truth pair when we had no real footage; Wonder generated ~11 reviewed rounds, transcripts in build_log.
- **Make it convincing:** Show dependency, not list. Walker fails without alias, armchair fails without re-check. That proves need-each-other. Cost/log + disk-cache by request hash is engineering, not Meta-tooling — move to Technical depth 20%, not Meta 25%.

7. **Top 8 fixes, ranked by judging impact / minutes**

- **1. Re-cut first 30s to struck-claim hero [copy-only, 15 min]:** Change VIDEO_SCRIPT 0:00-0:15 to: *“The AI said the armchair appeared. It didn’t. Watch it get struck.”* Show ink-strike first, then explain. Impact: Demo + Trust. Minutes: 15 rewrite, no code.
- **2. Add honesty chyron + say smoke test aloud [copy-only, 5 min]:** On-screen text for sample pair: *“Synthetic test room (Muse Image). Real home footage pending. n=1 pair, 3 runs.”* New voice line at 2:20: *“That 1.00 is a smoke test, not a benchmark.”* Defuses judge attack. Copy-only.
- **3. Rename surface, keep engine [copy-only, 10 min]:** Masthead change: `What changed in Mom's room since your last visit?` → `Second Look — is Dad's room still set up safe? Powered by SplatDiff engine`. README title: `Second Look (SplatDiff engine)`. Fixes trust + name gap. Copy-only.
- **4. Add consent + next-step + not-medical footer [copy-only, 10 min]:** Exact copy for report footer + UI under intake: *“Filmed with Dad’s knowledge. Ask together, keep together. Not a medical device — if HIGH risk, 1) move item back 2) call family 3) ask OT/nurse. We report changes, not health.”* Fixes privacy/liability. Copy-only.
- **5. Fix `not_seen` language [small code/copy, 15 min]:** Change status legend: `not_seen` → `not_seen — we couldn’t confirm, not safe`. In report template one line. Prevents dangerous misread. Code: string replace.
- **6. Kill live cost ticker, keep final cost [small code, 15 min]:** Hide per-stage `$` SSE tick; show end card only: *“Fresh check ~1 min, ~$0.33. Replay free.”* Judges remember cheap, not 26 requests. Code: comment out ticker div.
- **7. Add one-line “Why video?” [copy-only, 5 min]:** Under drop zones add: *“Why a short pan not photos? Catches walker behind chair + floor clutter photos miss. No camera to install, nothing recorded between visits.”* Kills fixed-camera objection. Copy-only.
- **8. Demote Image/Wonder to “How built” [copy-only, 10 min]:** Submission “How we used Meta models” reorder: lead Spark + SAM 3.1 + Voice with 2 verified moments; move Image + Wonder to last with label *“Scaffolding.”* Exact header: *“3 models do the check, 2 made it possible.”* Strengthens Meta 25%. Copy-only.

8. **One-sentence pitch and 15-second hook**
- **One-sentence pitch:** *Second Look compares two short phone pans of Dad’s room and tells you if the walker, lamp and clutter drifted — every finding shows its SAM boxes and frames, or it’s struck out, reason shown.*
- **15-second hook (open video with this over ink-strike):** *“Last month this room was fine. This month the walker’s out of reach — and nobody noticed. We filmed twice. Watch the AI claim an armchair appeared — and watch us strike it, because the evidence says it was there all along.”*

