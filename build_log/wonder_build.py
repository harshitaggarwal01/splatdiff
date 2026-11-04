"""Generate the SplatDiff codebase with Muse Wonder (muse-wonder-1.0) on the Meta Model API.

Usage: python build_log/wonder_build.py [--fix "error text" --files a.py,b.py]
Streams the response, saves the raw transcript to build_log/, and writes every
=== FILE: path === block to disk.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
URL = "https://api.meta.ai/v1/responses"


def call_wonder(prompt: str, effort: str = "high") -> str:
    headers = {
        "Authorization": f"Bearer {os.environ['MODEL_API_KEY']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": "muse-wonder-1.0",
        "input": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_output_tokens": 64000,
        "reasoning": {"effort": effort},
    }
    t0 = time.time()
    r = requests.post(URL, headers=headers, json=payload, stream=True, timeout=1800)
    if r.status_code != 200:
        print(r.status_code, r.text[:2000])
        sys.exit(1)
    out, usage = [], None
    for line in r.iter_lines():
        if not line:
            continue
        s = line.decode("utf-8", "replace")
        if not s.startswith("data: "):
            continue
        data = s[6:]
        if data.strip() == "[DONE]":
            break
        try:
            ev = json.loads(data)
        except json.JSONDecodeError:
            continue
        t = ev.get("type", "")
        if t == "response.output_text.delta":
            out.append(ev.get("delta", ""))
            if len(out) % 200 == 0:
                print(f"  ... {sum(map(len, out))} chars, {time.time()-t0:.0f}s", flush=True)
        elif t == "response.completed":
            usage = ev.get("response", {}).get("usage")
        elif t in ("error", "response.failed"):
            print("ERROR EVENT:", data[:2000])
    text = "".join(out)
    print(f"done in {time.time()-t0:.0f}s, {len(text)} chars, usage={usage}")
    return text


def write_files(text: str) -> list:
    written = []
    for m in re.finditer(r"=== FILE: (.+?) ===\n(.*?)\n=== END FILE ===", text, re.S):
        rel, body = m.group(1).strip(), m.group(2)
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.rstrip() + "\n", encoding="utf-8")
        written.append(rel)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", help="error/feedback text for a repair round")
    ap.add_argument("--files", default="", help="comma list of files to include for the repair round")
    ap.add_argument("--effort", default="high")
    a = ap.parse_args()
    spec = (ROOT / "build_log" / "SPEC.md").read_text(encoding="utf-8")
    if a.fix:
        ctx = []
        for f in [x for x in a.files.split(",") if x]:
            ctx.append(f"=== FILE: {f} ===\n{(ROOT / f).read_text(encoding='utf-8')}\n=== END FILE ===")
        prompt = (
            f"{spec}\n\n# REPAIR ROUND\nThe repo was generated from the spec above. Fix the problem below. "
            f"Output ONLY the files you change, complete, in the same FILE block format.\n\n## Problem\n{a.fix}\n\n"
            f"## Current files\n" + "\n".join(ctx)
        )
        tag = f"fix_{int(time.time())}"
    else:
        prompt = spec
        tag = "initial"
    text = call_wonder(prompt, a.effort)
    (ROOT / "build_log" / f"wonder_{tag}.md").write_text(text, encoding="utf-8")
    files = write_files(text)
    print("wrote:", *files, sep="\n  ")


if __name__ == "__main__":
    main()
