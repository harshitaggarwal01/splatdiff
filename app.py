"""SplatDiff Gradio 6 UI."""
from __future__ import annotations
from pathlib import Path
import gradio as gr
from splatdiff.pipeline import run, build_report

def _fmt_report(result: dict) -> str:
    md = build_report(result)
    md += "\n\n### Dropped (struck through above) — grounded-or-dropped rule\nEvery kept claim is backed by SAM 3.1 boxes/frames/confidences in the JSON below."
    return md

def run_ui(before, after, concepts_text, progress=gr.Progress()):
    if not before or not after:
        return "Please provide both videos.", [], {}, "No run yet."
    def prog(msg):
        progress(0.5, desc=msg)
    concepts = [c.strip() for c in concepts_text.split(",") if c.strip()] if concepts_text and concepts_text.strip() else None
    result = run(before, after, concepts=concepts, progress=prog)
    gallery = [(p, Path(p).name) for p in result.get("annotated_images", [])]
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
    sample_btn.click(load_sample, outputs=[before_in, after_in, status])
    run_btn.click(run_ui, inputs=[before_in, after_in, concepts_in], outputs=[report_out, gallery_out, json_out, status])

if __name__ == "__main__":
    demo.launch()
