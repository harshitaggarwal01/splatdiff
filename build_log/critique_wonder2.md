# Critique by muse-wonder-1.0

Second-pass red team — I'll verify the caregiving stats, competitor claims, and “aides already send photos” premise against live sources before tearing into what's still broken.Found a direct competitor and existing aide-photo workflows that undercut the moat. Now checking the before/after inventory claim and aide-consent friction.## Second-pass verdict

**Still not convincing.** Round 1 fixed the disclaimers, but created a new problem: the product now has *three incompatible lead users* — the visiting daughter, the non-visiting worried sibling, and the aide — while the demo, onboarding, and sample still serve only the first. The most damaging issues below are ordered first.

**Fact-checks that hurt you:**
- The fall stat is real: “more than 14 million older adults, about one in four, fall every year”, and CDC lists “home hazards like broken or uneven steps and clutter” as modifiable risks. But home-hazard reduction evidence is strongest for *OT-delivered assessment + fixes*, not detection alone: Cochrane found home fall-hazard interventions reduced falls by 26%, typically after an OT home visit.
- Aides/visitors **already send photos**: Comfort Keepers’ Family Room lets caregivers share “care notes, photos, and updates with family members”; Log my Care’s family app shares “photos and video clips” in care logs. So “send the far-away child a picture” is the incumbent, free behaviour.
- Before/after diffing is not virgin territory either: Inventory Hive advertises “Side-by-side reporting. ‘Before’ and ‘After’ comparison is made easy”, and DwellSafe already offers smartphone room scans with “clinician-reviewed assessments” for fall prevention. Your moat must narrow to *grounded/struck visit-to-visit object diff for families*, not “nobody does this.”

---

## 1. Founder’s question: “If Dad already lives there and I’m the one visiting and filming, how does it help?”

### Is the current answer convincing?
- **Only the split-filmer version is strong, and it contradicts your own positioning.** PRODUCT.md calls aide/sibling filming “expansion… not the opener,” but the founder defence makes it the answer. If that’s now the wedge, the pitch, onboarding, accounts/permissions, and demo are pointed at the wrong user.
- **Change blindness is real but underspecified.** Gradual change blindness is documented — people “fail to notice changes… when they occur gradually” — but that argues for a *dated external memory*, not magic detection. A frequent visitor may still notice the walker because they use it with Dad; they are weakest on *where exactly it was last time*, not on “is something wrong today?”
- **OT baseline is your best same-person argument — and it decays.** Discharge setups are meant to change as Dad recovers, gets stronger, rejects the walker, or the OT revises the plan. A frozen “safe” baseline can flag recovery/adaptation as drift.
- **Dated record is weak as built:** local `outputs/`, “no in-app delete yet,” no signer, no tamper/audit trail, no care-team acceptance evidence. That’s a family memory aid, not a clinical record.
- **Honest residual weakness:** for the same attentive, frequent visitor, Second Look is mostly a memory prosthesis and a sharing format. It does **not** beat their eyes while they are in the room; it beats their *memory three weeks later* and their *sibling’s absence*. If they visit weekly and act immediately, value is marginal.

### Exact 2-sentence answer for the video
> “If you’re the one visiting, Second Look isn’t there to out-see you — it’s there because nobody remembers exactly where the walker stood three weeks ago. Film the OT-approved setup once, film again next visit, and we show you what drifted against that baseline, with evidence, so you can fix it or send the same receipts to the sibling who wasn’t there.”

---

## 2. Use-case holes

- **Who films is still hand-waved.** “A sibling, a neighbour, the aide” hides four different consent, access, phone-quality, and accountability problems. Who uploads? Who owns the baseline? Who sees Dad’s bedroom? Who is responsible when the report says HIGH?
- **Aide refusal is likely, not edge-case.** Aides may see filming as surveillance of *them*, extra unpaid labour, or an agency-policy/HIPAA risk. Home-care recording guidance is consent-heavy, and families online already report agencies treating photos in a patient’s home as confidentiality violations. You have no aide script, no agency mode, no “film only after I’ve left” option.
- **No filming instructions = non-comparable clips.** “Same slow pan” is not an instruction. If Clip A covers bed→door and Clip B covers door→bathroom, the system will manufacture `not_seen`, miss the path, and the moved judge loses shared landmarks. There is no coverage map, overlap score, “you missed the bed corner — retake” gate, or baseline route.
- **Lighting/night is the actual risk window, untested.** The feared trip is bed→bathroom at 2 a.m.; the demo is daytime synthetic stills. Lamp on/off, glare, dark corners, and night lighting change detections and are the hazard itself — presence of a lamp says nothing about the lit path at night.
- **Dad moving things on purpose breaks the moral logic.** It is his home. Older adults’ need for autonomy is a known design constraint in fall-risk communication, and remote monitoring can position people as “at risk” and dependent. Today the report treats Dad’s rearrangement as a defect for the daughter to reverse. There is no “Dad chose this” state.
- **Consent is stated, not operationalised.** Capacity, visitors in frame, medication labels, bathroom filming, aide likeness, voice-note audio, cloud upload, retention, withdrawal — all collapsed into “ask together, film together.” No per-room consent checklist in the intake flow.
- **Far-away child: action or anxiety amplifier?** Telecare literature finds reassurance *and* “anxiety, distrust and stress” as common psychological outcomes; a long trial of remote monitoring found no significant improvement in caregiver burden/depression outcomes. Your “Send to family” sends alarm without an owner, deadline, acknowledgement, or “I’ve handled it” loop. Expect a worried phone call to Dad, not a fixed walker.
- **Cadence economics are off.** Long-distance caregivers exist at scale — roughly 5–7 million doing it from afar — but many visit only a few times a year, which makes drift detection late; frequent local visitors need it least. The sweet spot is narrow: 2–6-week visitors plus a discharge trigger.

---

## 3. Feature holes: theatre vs value

**Theatre / judge-bait**
- **Live pipeline view:** SSE stages, filmstrips, L/T chips — plumbing as entertainment. It exposes latency and failures live; the script even advises replaying a cached run “so the ink-strike always appears on cue,” which a judge will read as staged.
- **Vocabulary repair (“Learning the family’s words”):** one verified anecdote, elevated to a named stage. It can also *create* risk: SAM finding “metal walking frame” does not prove it found *Dad’s walker*, in the right place, usable.
- **Voice notes:** solves typing three words. Adds transcription error, accent/English-only risk, and ambient-audio privacy for a watchlist a daughter already knows.
- **Risk triage:** the most legally sensitive feature presented as sorting. Lamp vs walker vs cushion ranking is health-adjacent judgement with no OT rule source shown.
- **`Mark as sorted`:** self-attestation with no verification until next visit, no persistence story across phones/no-account model, no “who sorted it.”
- **`Send to family` / copy summary:** plain text strips away the boxes — i.e. it deletes the moat at the exact moment of sharing. The recipient gets the claim, not the receipts.
- **`Past checks`:** cache replay is a demo convenience dressed as retention. No longitudinal trend view (“walker moved 3 visits running”) which would be real value.

**Real value, under-built**
- **Evidence board + struck claims:** still the product. Protect it.
- **Print:** genuinely fits OT/care-folder behaviour — but needs date, baseline date, filmer, room, and “unverified family report” provenance.

**Missing first, before any of the theatre**
1. Guided filming checklist + coverage/overlap gate with retake prompts (“film this corner”).
2. Baseline locking **and** baseline updating: “new OT plan / Dad chose this / item replaced.”
3. Multi-room route: bedroom→hall→bathroom is the story; single-room diff cannot check the path you keep citing.
4. Intentional-change button and Dad-agreed watchlist (“we agreed the lamp lives here now”).
5. Reminders tied to visits, recipient acknowledgement/escalation, and a longitudinal drift timeline.
6. Delete/consent controls in-app, person/face and document blurring, low-light warning.

---

## 4. Story / pitch holes

- **NEWLY BROKEN: the hero copy shipped malformed.** `home.html` has a nested, unclosed `<p class="hero-sub">` and a literal `mdash;` — the round-1 founder answer was pasted in and visibly collides with the old sentence. A judge opening DevTools or reading closely sees a rushed patch, not a product.
- **The hook still lies about the demo.** Video opens “the walker is out of reach,” but the scoreable sample changes are backpack removed, lamp moved, suitcase added — and the *walker is reported in place*. You are narrating the finding you wish you had.
- **“Real footage works the same way” is unverifiable and still in the script,** while the real-footage beat is literally `[PLACEHOLDER: user's real clips]`. That is the single easiest judge kill-shot remaining.
- **PRODUCT vs page vs app disagree on the person.** Lead story: Dad/daughter. App masthead: “What changed in **Mom’s** room.” Page aside: rental move-outs. Three audiences in three surfaces.
- **“Alerts that lead to action” overclaims:** the page itself admits “there are no push notifications.” A banner inside a report the user must choose to run is not an alert.
- **“Three steps, one minute”** conflates runtime with a two-visit, weeks-apart behaviour. “Works with any phone video” sits next to a 30-second, 640px, 5fps cap in the README.
- **Patronising register remains:** Dad is filmed, set up, checked, and asked “to show you he can reach it” — a compliance test. He never speaks, chooses the watchlist, or disagrees in any copy. For a product about his home, he is a prop.
- **Privacy copy overreaches:** “not the contributor mode that permits training,” “no tracking scripts,” “anyone can check” — none of this is evidenced in the materials a judge can verify during Q&A. One request to show the data-handling proof ends the exchange.

---

## 5. Technical holes for Q&A

- **Synthetic Ken Burns is not video evidence.** A pan/zoom over a still has no parallax, occlusion change, hand shake, motion blur, people, or clutter dynamics. SAM “tracking” across near-duplicate frames is the easy case; it cannot support “real footage works the same way.”
- **The moved call is the headline and the weakest link.** Boxes-not-masks + different viewpoints + “relative to surrounding furniture” fails exactly when furniture also moves, the room is re-shot from the other door, or the lamp moves along the same wall. The 0.80 threshold was set after seeing the same n=1 pair it is evaluated on — textbook overfit, already confessed but still fatal to the 1.00 table.
- **Presence = 2 frames at c≥0.5 is gameable by the pan itself.** One slow pass can give a partly occluded object 2 lucky frames; a fast pass can give a present object 0. No coverage denominator = confidences are not comparable between visits.
- **Confidence theatre:** 0.875 / 0.75 are repeated as if calibrated probabilities. They are detector scores on one synthetic room; a judge will ask what 0.75 means for a real walker behind bedding. You have no answer.
- **The re-check only rescues added/removed.** It does not rescue the catastrophic case you yourselves name: a *missed moved walker* (`present_both` but judge says no, or one side under-covered). Your safety story is asymmetric in the wrong direction.
- **Clutter — your headline hazard — is not an object.** “Clutter colonised the path” is a set/absence-of-clear-space property. A max-12 movable-object inventory cannot measure path clearance, rug edges, cords, spills, or reach distance. You detect nouns; hazards are relationships.
- **Cost scales against the story:** $0.33 is one synthetic room, ~26 SAM requests. Multi-room route + watchlist + aliases + re-checks multiplies requests; “about $0.33 per check” on the homepage is a sample-pair number wearing a product claim.
- **No person handling:** a real walkthrough will capture Dad, the aide, mirrors, photos, documents. No detection/redaction/consent gate is described. “Frames go to cloud APIs” plus “no in-app delete yet” is the Q&A trap.

---

## 6. TOP 6 FIXES — 20 minutes total, copy-only

**1. (3 min) Fix the broken hero and answer the founder on the homepage.**  
*Where:* `web/home.html`, replace both malformed `hero-sub` paragraphs with:  
> “The person who visits isn’t always the person who worries — and nobody remembers exactly where the walker stood last month. Film the room the day it’s set up safe; next visit, anyone can film it again, and Second Look shows what drifted, with evidence, or strikes the claim.”

**2. (3 min) Stop narrating a walker finding you don’t have.**  
*Where:* `VIDEO_SCRIPT.md` 0:00–0:15, replace hook with:  
> “Last month this lamp stood by the sofa. This month it’s across the room — and nobody noticed. We filmed twice; watch what drifted, and watch one claim get struck because the evidence wasn’t there.”

**3. (4 min) Add the filming checklist that makes two clips comparable.**  
*Where:* app intake, above the drop zones:  
> “Film the same route both times: start at the door, pan slowly to the bed, then along the path to the bathroom door. Keep the light on, keep each watchlist item in view for two seconds, and re-film any corner the report marks ‘not seen’.”

**4. (4 min) Give Dad agency and fix the false-drift problem.**  
*Where:* report, under every finding, add:  
> “Moved on purpose? If Dad chose this — or the OT changed the plan — tap ‘This is the new setup’ and today becomes the new baseline. Second Look flags change; your family decides what’s unsafe.”

**5. (3 min) Make sharing actionable instead of anxiety-forwarding.**  
*Where:* `Send to family` / copy summary, prepend:  
> “Second Look check, [date], filmed by [name]. Needs one owner: please reply ‘I’ll do it’ or ‘I can’t’. Do this next: [step]. Not a medical assessment — if this worries you, put the item back and ask the OT or nurse.”

**6. (3 min) Correct the two unverifiable claims before a judge does.**  
*Where:* video 0:45 label + homepage “Honest numbers,” replace “real footage works the same way” with:  
> “Scored on one synthetic test room so we know the right answer. Real, cluttered rooms are the next test — recall there is untested, and a missed walker matters more than a false alarm.”

---

## 7. Single best line for the last 10 seconds

> **“Film it the day it’s safe — next visit, don’t trust your memory: we’ll show you what drifted, with receipts, or we’ll strike it.”**
