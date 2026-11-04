"""Evaluate SplatDiff against ground truth."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def _tokens(s: str) -> set:
    return set(str(s).lower().replace("-", " ").split())

def _match(claim, gt_list, used):
    best, best_score = None, 0.0
    ct = _tokens(claim.get("concept", ""))
    for i, g in enumerate(gt_list):
        if i in used or g.get("change") != claim.get("change"):
            continue
        gt_t = _tokens(g.get("concept", ""))
        overlap = len(ct & gt_t) / max(1, len(gt_t)) if gt_t else 0
        if ct and (ct <= gt_t or gt_t <= ct):
            overlap = 1.0
        if overlap > best_score:
            best, best_score = i, overlap
    return best if best_score >= 0.5 else None

def _score(claims, gt):
    used, tp = set(), 0
    for c in claims or []:
        m = _match(c, gt, used)
        if m is not None:
            tp += 1; used.add(m)
    fp, fn = len(claims or []) - tp, len(gt) - tp
    p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return tp, fp, fn, p, r, f1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True); ap.add_argument("--result", default=None)
    ap.add_argument("--run", nargs=2, metavar=("BEFORE", "AFTER"), default=None)
    ap.add_argument("--concepts", default=None)
    args = ap.parse_args()
    gt = json.loads(Path(args.gt).read_text(encoding="utf-8"))
    if isinstance(gt, dict) and "gt" in gt:
        gt = gt["gt"]
    if args.run:
        from splatdiff.pipeline import run
        concepts = [c.strip() for c in args.concepts.split(",")] if args.concepts else None
        result = run(args.run[0], args.run[1], concepts=concepts)
    else:
        if not args.result:
            ap.error("--result is required unless --run is used")
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    raw = result.get("raw_claims", []); kept = result.get("claims", result.get("kept_claims", []))
    rows = []
    for name, claims in (("Raw Spark claims", raw), ("Grounded kept claims", kept)):
        tp, fp, fn, p, r, f1 = _score(claims, gt)
        hall = fp / len(claims) if claims else 0.0
        rows.append((name, len(claims), tp, fp, fn, p, r, f1, hall))
    md = ["# SplatDiff evaluation", "", "| System | Claims | TP | FP | FN | Precision | Recall | F1 | Hallucinated-claim rate |",
          "|---|---|---|---|---|---|---|---|---|"]
    for n, ncl, tp, fp, fn, p, r, f1, hall in rows:
        md.append(f"| {n} | {ncl} | {tp} | {fp} | {fn} | {p:.3f} | {r:.3f} | {f1:.3f} | {hall:.3f} |")
    md += ["", f"Total cost: ${result.get('cost_usd', 0):.4f} · Latency: {result.get('latency_s', 0):.1f}s",
           "", "_Hallucinated-claim rate = raw/kept claims not in ground truth (FP / claims)._"]
    out = Path("outputs"); out.mkdir(exist_ok=True)
    (out / "eval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md)); print("\nWrote outputs/eval.md")

if __name__ == "__main__":
    main()
