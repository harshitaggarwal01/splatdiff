# Critique by muse-spark-1.3

Voices first, then the red-team takedown — digging up receipts to back every cut.## Three honest voices

### (a) Dad, 82 — the man in the room

> Leave my room alone.
>
> I came home from hospital and the girl from the hospital told me where to put things. Fine. Then my daughter comes with her phone and walks round my bedroom in a circle. Says "it's for safety, Dad." I smiled because she drove four hours.
>
> But it's *my* bedroom. If I moved the lamp next to my chair, I moved it because that's where I read. If the walker is by the window, maybe I left it there because I was tired. I don't want to ask permission in my own house.
>
> And don't put me on some report with HIGH RISK in red letters. I'm not a risk. I'm your father. Ask me. Don't film me. If you think something's wrong, say it to my face while you're here — don't go home and read about me on a computer.

What he's telling you: consent isn't a checkbox. Filming feels like surveillance when you live there. Autonomy — moving his own lamp — reads as "drift" to you.

### (b) The weekly aide — the woman you'd ask to film

> Honey, I clean and I check his pills and I have 45 minutes.
>
> You want me to do a slow pan of the bedroom? Which corner? Do I move the laundry basket? What if he's in the bathroom? What if he's asleep? I'm not filming a man in his bedroom without him saying yes, clear as day, every time. And in what language? He nods sometimes just to be polite.
>
> And then what? If your app says I missed something and he falls — is that on me? I don't want my name on that. I already text the family "he's fine, ate well." You want me to be your cameraman, but you don't pay me extra, you don't give me instructions, and his daughter gets the report and I get the blame.
>
> No. Give me a one-page sheet: stand here, point there, 15 seconds, press this one button. Tell him what it is. And don't make me explain your HIGH finding to him. That's your job.

What she's telling you: "anyone can film" is fantasy. Without a script, lighting guidance, time-box, and liability cover, she will refuse — reasonably.

### (c) The son, 4 hours away — the man who reads the report

> I got the printout. "Floor lamp — MOVED. High." With two photos and a box.
>
> Okay. Now what? Do I drive Friday night? Do I call Dad and tell him to move his lamp — he'll tell me to mind my own business. Do I call my sister who was just there? She said the place looked fine.
>
> "Not seen — not the same as missing. Check before you worry." So... should I worry or not? I *already* worry. That's why I opened this.
>
> Worst part: last month it said walker "seen where it should be." I felt good for a week. Then I realized — does that mean he can reach it? Is it plugged in? Is anything blocking it? No. It just means it was in the video twice.
>
> Give me something I can actually do from 200 miles away besides feeling guilty.

What he's telling you: a report that can't be acted on remotely just exports anxiety.

---

### Product critic summary

Second Look has one real moment — the struck claim — buried in a product that solves the filmer's memory problem by creating three new problems: a consent problem with Dad, a labor problem with the aide, and an action problem with the son. You pitch "calm answer," you ship "more to worry about, with boxes." Until filming is guided, baselines are locked, and HIGH means *who does what by when from far away*, this is a demo with a dossier font.

---

## 1. Is the founder's question answered convincingly?

No. Current answer — "it helps when filmer ≠ worrier + change blindness + OT baseline + dated record" — is directionally right but evasive.

**Strongest honest version:**
1. In-person you remember gist, not position. You were being a son/daughter, not a surveyor. A 20-sec pan + locked OT baseline beats "I think the lamp was over there?"
2. The value isn't for you in the room, it's for you *after* you leave: provable, shareable, re-checkable — so siblings and the nurse see the same thing, not your memory of it.

Falls are common — more than 1 in 4 adults 65+ falls each year — and home-hazard work can cut fall rates by ~26%. But drift is only one factor among strength, meds, vision, etc. Memory aid ≠ prevention.

**Honest residual weakness:** if the same attentive person visits often, talks to Dad, and Dad explains why he moved things, the product adds ~zero. It only pays when (a) visits are sparse, (b) filmer and worrier are different people, or (c) you need proof for others. Say that.

**Exact 2-sentence answer for the video — say verbatim:**

> You came to see Dad, not to memorize where his walker stood — three weeks later you won't remember if it drifted. Film the safe setup once, film the same pan next visit, and we show you what moved with proof you can send family, or we strike the claim in front of you.

## 2. Use-case holes

Most damaging first:

* **Who films, exactly?** "Sibling / neighbour / aide" is three different consent, training, and phone-quality regimes hand-waved as "anyone." Aide filming a bedroom is paid surveillance work. Neighbour filming is weird. Sibling filming requires a second visit to exist.
* **How often?** Discharge + 3 weeks later is credible. "Every visit" is not. No one does systematic pans unprompted — trigger is scare/discharge/new aid, not routine. Copy still implies routine.
* **With what instructions?** No framing guide, no "stand in doorway, pan left-to-right, lights on, 15 sec." Two clips covering different corners = `not_seen` spam, not insight.
* **Different coverage kills you:** if clip 1 misses bathroom path and clip 2 catches it, everything is "added." User learns not to trust you after one sloppy pan.
* **Lighting / night:** real risk is 2 a.m. bathroom trip. Daytime pan says nothing about dim bulb, glare, shadows. Lamp present ≠ lit.
* **Dad moves things on purpose:** it's his home. Walker by window because he was tired. Lamp by chair because he reads there. You label autonomy as drift. No "Ask Dad why" step before HIGH.
* **Aide refusal is the default:** time, pay, privacy, liability, language, "am I in the video?", meds/labels in frame. No aide workflow = no retention story.
* **Consent per visit is a sentence, not a flow:** where is the "Ask together, film together" screen? Verbal script? Delete button? No in-app delete yet per your own README.
* **Does far-away child act or just worry more?** HIGH with "move it back" assumes someone local. From 4 hours away, actions are: call, guilt-trip, drive, or nothing. No "send to sibling," no "call OT," no escalation if still moved next visit.
* **Baseline rot:** OT setup day 0 is safe. By week 6 Dad has legitimately rearranged. When do you re-lock baseline vs. flag drift? Currently never — everything old is "correct" forever.

## 3. Feature holes: theatre vs. value

**Theatre (impressive in demo, near-zero for family):**

* **Live pipeline view + filmstrips + L/T chips:** plumbing as show. Family wants answer, not "normalising, keyframes, inventory..." Compress to progress bar.
* **Ledger of models/cost ticking:** "26 SAM requests / 650 frames" invites "paid wrapper?" Show `$0.33` once at end.
* **Vocabulary repair as UI section:** "Learning the family's words" needs explanation. Valuable underneath, theatre on screen. Should be invisible: just find the walker.
* **Evidence board tables (frames seen, confidences):** judges like, families glaze. Keep one before/after image pair, hide table behind "details."
* **Past checks drawer as retention:** replay free is engineering, not a reason to return. Return reason is reminder + "re-film this corner."

**Real value (keep, strengthen):**

* **Risk triage + Do this next + Mark as sorted:** only loop-closing feature. But currently one generic walker script.
* **Watchlist typed/spoken + voice notes:** genuinely hands-free while holding phone. Keep, but need confirmation: "Heard: walker — must stay by bed. Right?"
* **Send to family / print / copy summary:** this *is* the remote-son use case. Under-built.

**Missing — what a real family needs first:**

* Guided filming checklist + overlay: stand here, pan this way, lights on, 15 sec, cover bed-to-bathroom.
* `Film this corner` re-take prompt when `not_seen` — not a shrug.
* Baseline locking + re-baseline: "Lock discharge setup as safe? [Yes] / Update baseline after agreed move."
* Multi-room (bedroom + path to bathroom minimum) — falls happen *between* rooms.
* Reminders: "It's been 3 weeks since baseline — re-film?"
* Delete run + "rooms Dad is happy to share" picker.
* "Ask Dad why" field before HIGH ships: moved-on-purpose vs. drift.

## 4. Story / pitch holes in product page + video

* **Unverifiable / overreaching:**
  * "Works with any phone video" — tested on 1 synthetic pair, not real cluttered rooms. Strike it.
  * "A different angle is fine" — moved is admitted weakest across viewpoints. Can't promise this.
  * "Private by design... standard model IDs — not contributor mode" — judge can't verify; sounds like privacy-washing while frames go to cloud API.
  * "Drift can create hazards. We show you the drift" — okay, but adjacent "Needs attention" + red HIGH still reads as health advice despite "not a medical device."
  * Cost/time "about a minute and about $0.33" — true *on sample pair only*. Real 30-sec phone clips will differ. Qualify.
* **Still demo, not product:**
  * Hero images are synthetic test room, captioned as "real SAM boxes." True but misleading — boxes on fake images.
  * Broken hero copy in `home.html`: duplicated `<p class="hero-sub">` + stray `.mdash;` text shows unreviewed ship.
  * Masthead flip-flops Mom vs. Dad ("What changed in Mom's room?" UI vs. Dad everywhere else). Feels template-y.
  * "Three steps, one minute" — check alone is ~1 min, filming + upload + review is 10.
  * Tip "replay armchair run from Past checks so strike appears on cue" = admission live runs are flaky.
* **Patronising toward older adults:**
  * "Ask Dad to show you he can reach it" — in front of aide? Infantilizing without "with his permission, together."
  * "Dad is 82, he lives alone" as hook + fall stat = frailty framing. Dad hears: I am a hazard.
  * "Mark as sorted" about his room, without him. Where is his voice?
  * No "Dad's view" section. Privacy section is addressed to daughter, not him.

Competitor framing is fair: Encircle was built for insurance room-by-room photo/video baselines, Sortly is visual inventory with photos — neither diffs two visits. Keep that moat line, drop "gold standard" talk.

## 5. Technical holes a judge will attack

* **Synthetic Ken-Burns sample:** pans over Muse Image stills, not video. No motion blur, no occlusion dynamics, no exposure changes. Your 1.00 precision/recall is on data you generated to be scoreable.
* **n=1, 3 runs + threshold overfit:** 0.80 moved threshold "set after looking at it." Textbook overfit. Say "tuned on demo, will fail elsewhere" before they say it.
* **Moved across viewpoints:** judging position "relative to surrounding furniture" by VLM is vibes, not geometry. 6 inches vs. 2 feet camera shift look identical. Yet lamp-moved is headline finding.
* **30s cap @5fps, 6 keyframes for inventory:** why 6? Why 12 objects max? Smells arbitrary. Small clutter (cord, pill organizer, spill, rug edge) — the actual killers — will be missed, and boxes can't see states/absences anyway.
* **Boxes, not masks:** "mask payload undocumented" is honest but weak — SAM 3.1 *is* a mask model. You settled for boxes.
* **Presence = 2+ frames @c≥0.5:** why 2? Why 0.5? No ablation. Tracker flicker flips added/removed.
* **Image re-check overturns tracker:** good, but re-check at c≥0.5 on keyframes is same model checking itself with looser temporal evidence — correlated failure, not independent proof.
* **Hallucination rate 25-40% raw:** you celebrate striking all, but that means base reasoner is unreliable and filter does all work. What if filter misses? Recall untested is the catastrophic side.
* **Cost claims:** 26 requests / ~650 frames / $0.33 is sample-specific. Real pair + watchlist + re-checks will cost more. Cached "free" is just disk cache.
* **English voice only, no real-room eval:** fine for hackathon, fatal if pitched as deployable safety tool.

## 6. TOP 6 FIXES — 20 minutes total, copy-only

**Fix 1 — Product page hero [home.html hero-sub, 3 min]:**
Replace broken duplicate paragraph (including stray `Film the room...mdash;`) with:
> Film the discharge-day safe setup once. Next visit — you, a sibling, or the aide — film the same slow pan. We show what drifted, with proof, or strike the claim in front of you.

**Fix 2 — Product page Steps step 2 [home.html steps, 2 min]:**
Replace `The same slow pan, a few weeks later. A different angle is fine — the comparison allows for a changed viewpoint.` with:
> The same slow pan from the doorway, lights on, bed-to-bathroom path included. Same corner matters more than same angle — if we can't see it, we say not seen, not missing.

**Fix 3 — Product page FAQ + Report footer [home.html FAQ + app report template, 4 min]:**
Add new FAQ at top + footer line everywhere:
> Who should move it back? Only someone there, with Dad. If you're far away, send the report to someone local or call the care team — don't tell Dad to move furniture alone at night. Not a medical device.

**Fix 4 — App intake consent + filming guide [app intake under drop zones, 4 min]:**
Replace `Works with any phone video` with:
> Only film rooms Dad is happy to share — ask together, film together. 15–20 sec, doorway to window, include bed-to-bathroom path, lights on. Delete a check anytime by deleting its folder in outputs/. Clips go to Meta API to find objects.

**Fix 5 — README + video honesty label [README Results first line + VIDEO_SCRIPT 0:15 chyron, 3 min]:**
Replace any `Precision 1.00 / Recall 1.00` headline with:
> On our one synthetic test room (3 runs), raw model invented 25–40%; grounding struck every one — smoke test, not a benchmark. Recall in real cluttered rooms untested. Sample pair is Ken-Burns pans over AI stills.

**Fix 6 — Video HIGH + not_seen language [VIDEO_SCRIPT 1:45–2:25, 4 min]:**
Replace narration of HIGH with exact:
> High doesn't mean emergency — it means look first. If you're far, don't phone Dad to move it alone. Send this to someone local. And not seen never means missing — it means we couldn't confirm it, check that corner in person.

All copy-paste, no code rebuild, no re-record — chyron over existing footage.

## 7. Single best line for last 10 seconds

> We don't watch Dad — we remember the room for you, so you can be his son again, not his surveyor.

