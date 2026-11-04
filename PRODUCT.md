# SplatDiff — product context

_Written from the hackathon brief and the user's choices on 2026-11-04 (aging-parent story, Care dossier look). Assumptions are marked._

## What it is
A room-change checker for families caring for an older adult at home. Film the parent's room on each visit with a phone. SplatDiff compares the two walkthroughs and reports what was added, removed or moved. Every finding is backed by Meta SAM 3.1 detections, and a finding without evidence is struck from the report, with the reason shown.

## Who it is for
- **Primary:** adult children and family caregivers who visit a parent periodically (assumption: weekly or less) and worry about home hazards between visits.
- **Secondary:** home-care nurses, and landlords or tenants doing move-out inspections, using the same engine.

## Why it matters
Falls are common among older adults (CDC: about 1 in 4 adults over 65 fall each year), and home hazards are a modifiable risk factor. Slow drift goes unnoticed: a walker pushed out of reach, clutter on the floor, a lamp moved away from the bed. Families need a calm, honest answer, not an AI guess.

## Principles
- **Trust over cleverness:** grounded or dropped. Show the receipts.
- **Calm over alarm:** findings are triaged by risk in plain language.
- **The family's words:** a care watchlist, typed or spoken, decides what matters most.

## Surfaces
- Web demo (`web/`, served by `server.py`). Mode: Operate (a task: check the room), with a Read-quality report.
- Gradio fallback (`app.py`).

## Brand tone
A warm, careful family record: paper, ink, serif headlines. Never a neon AI dashboard.
