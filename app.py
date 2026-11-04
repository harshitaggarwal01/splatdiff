"""SplatDiff Gradio 6 UI."""
from __future__ import annotations
from pathlib import Path
import gradio as gr
from splatdiff.pipeline import run, build_report

def _fmt_report(result: dict) -> str:
    md = build_report(result)
    md += "\n\n### Dropped (struck through above) — grounded-or-dropped rule\nEvery kept claim is backed by SAM 3.1 boxes/frames/confidences in the JSON below."
    return md

def _gallery(result: dict) -> list:
    """Annotated images only for claimed concepts: kept first, then dropped.

    Files are named ``before_<concept_with_underscores>.jpg`` /
    ``after_<concept_with_underscores>.jpg`` in ``result['annotated_images']``.
    """
    annotated = [str(p) for p in (result.get("annotated_images", []) or [])]
    gallery, seen = [], set()

    def files_for(concept: str) -> list:
        slug = str(concept).strip().lower().replace(" ", "_")
        wanted = {f"before_{slug}.jpg", f"after_{slug}.jpg"}
        return [p for p in annotated if Path(p).name.lower() in wanted]

    for claim in result.get("kept_claims", []) or []:
        concept = str(claim.get("concept", "")).strip()
        if not concept:
            continue
        change = str(claim.get("change", "")).strip()
        caption = f"{concept} - {change.upper()} (kept)" if change else f"{concept} (kept)"
        for p in files_for(concept):
            if p not in seen:
                seen.add(p); gallery.append((p, caption))
    for claim in result.get("dropped", []) or []:
        concept = str(claim.get("concept", "")).strip()
        if not concept:
            continue
        change = str(claim.get("change", "")).strip()
        reason = str(claim.get("reason", "")).strip()
        caption = f"{concept} - {change} (DROPPED: {reason})" if reason else f"{concept} - {change} (DROPPED)"
        for p in files_for(concept):
            if p not in seen:
                seen.add(p); gallery.append((p, caption))
    return gallery

def run_ui(before, after, concepts_text, progress=gr.Progress()):
    if not before or not after:
        return "Please provide both videos.", [], {}, "No run yet."
    def prog(msg):
        progress(0.5, desc=msg)
    concepts = [c.strip() for c in concepts_text.split(",") if c.strip()] if concepts_text and concepts_text.strip() else None
    result = run(before, after, concepts=concepts, progress=prog)
    gallery = _gallery(result)
    line = f"Cost (this run, ledger delta): ${result.get('cost_usd',0):.4f} · Latency: {result.get('latency_s',0):.1f}s · Run: {result.get('run_id','')}"
    return _fmt_report(result), gallery, result, line

def load_sample():
    b, a = "data/sample_before.mp4", "data/sample_after.mp4"
    if Path(b).exists() and Path(a).exists():
        return b, a, "Sample pair loaded."
    return None, None, "Sample pair not found — run: python scripts/make_synthetic.py"

with gr.Blocks(title="SplatDiff") as demo:
    gr.Markdown("# SplatDiff — What changed in this room?\nGrounded-or-dropped change reports from SAM 3.1 + Muse Spark 1.3.")
    with gr.Row():
        before_in = gr.Video(label="BEFORE video")
        after_in = gr.Video(label="AFTER video")
    concepts_in = gr.Textbox(label="Concepts override (optional, comma-separated)", placeholder="floor lamp, backpack, red suitcase")
    with gr.Row():
        run_btn = gr.Button("Run SplatDiff", variant="primary")
        sample_btn = gr.Button("Load sample pair")
    status = gr.Textbox(label="Status / cost & latency", interactive=False)
    report_out = gr.Markdown(label="Report")
    gallery_out = gr.Gallery(label="Annotated keyframes", columns=3)
    json_out = gr.JSON(label="Raw result")
    gr.Markdown("Grounded-or-dropped: every kept claim has SAM 3.1 evidence; Spark claims without it are struck through.")
    sample_btn.click(load_sample, outputs=[before_in, after_in, status])
    run_btn.click(run_ui, inputs=[before_in, after_in, concepts_in], outputs=[report_out, gallery_out, json_out, status])

if __name__ == "__main__":
    demo.launch()
