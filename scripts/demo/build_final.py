"""Final cut: scenes fitted to the narration (boundaries from Muse Voice Transcribe turn timestamps), voice muxed, captions."""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_video as mv  # noqa: E402

D = mv.D
W = mv.WORK
SC = json.loads((D / "scenes.json").read_text(encoding="utf-8"))
L = mv.LINES
B = [0.0, 17.5, 28.3, 39.3, 60.8, 73.5, 83.3, 101.8, 117.9, 134.1, 147.29]
MAX_SPEED = 2.1

CAPTIONS = [(0.3, 6.0, "Hi, my name is Harshit, and this is my submission for the hackathon.")]
texts = list(L)
texts[5] = ("And Dad has a say. When he said he moved the lamp to read by his chair, "
            "it was marked as his choice, not an alarm.")
for i, t in enumerate(texts):
    s = 6.3 if i == 0 else B[i] + 0.2
    e = B[i + 1] - 0.2
    if len(t) > 150:
        sents = re.split(r"(?<=[.!?])\s+", t)
        best, cut = None, 1
        for k in range(1, len(sents)):
            d = abs(len(" ".join(sents[:k])) - len(t) / 2)
            if best is None or d < best:
                best, cut = d, k
        a, b = " ".join(sents[:cut]), " ".join(sents[cut:])
        mid = s + (e - s) * len(a) / max(1, len(a) + len(b))
        CAPTIONS += [(s, mid, a), (mid, e, b)]
    else:
        CAPTIONS.append((s, e, t))


def fit(i, start, end, target, out):
    length = end - start
    speed, vf = 1.0, []
    if target < length:
        speed = min(MAX_SPEED, length / target)
        vf.append(f"setpts=PTS/{speed:.4f}")
    played = length / speed
    if played < target:
        vf.append(f"tpad=stop_mode=clone:stop_duration={target - played + 0.05:.3f}")
    vf.append("fps=30")
    mv.run(["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(D / "demo_raw.mp4"), "-vf", ",".join(vf),
            "-t", f"{target:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", str(out)])
    return speed


def still(png, target, out):
    frames = int(round(target * 30))
    mv.run(["-loop", "1", "-i", str(png), "-vf",
            f"scale=2112:1188,zoompan=z='min(zoom+0.0006,1.06)':d={frames}:x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30", "-frames:v", str(frames), "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out)])


clips = []
for i, sc in enumerate(SC):
    target = B[i + 1] - B[i]
    out = W / f"final_{i:02d}.mp4"
    if i == 5:
        still(W / "scene6_dad.png", target, out)
        print(f"scene {i + 1}: still {target:.1f}s")
    else:
        sp = fit(i, sc["start"], sc["end"], target, out)
        print(f"scene {i + 1}: {sc['end'] - sc['start']:.1f}s -> {target:.1f}s ({sp:.2f}x)")
    clips.append(out)

lst = W / "final_concat.txt"
lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
mv.run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(W / "final_video.mp4")])

pngs = []
for k, (_, _, t) in enumerate(CAPTIONS):
    p = W / f"fcap_{k}.png"
    mv.caption_png(t, p)
    pngs.append(p)
args = ["-i", str(W / "final_video.mp4")] + sum([["-i", str(p)] for p in pngs], []) + ["-i", str(D / "voice.m4a")]
chain, last = [], "[0:v]"
for k, (s, e, _) in enumerate(CAPTIONS):
    nxt = f"[c{k}]"
    chain.append(f"{last}[{k + 1}:v]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})'{nxt}")
    last = nxt
args += ["-filter_complex", ";".join(chain), "-map", last, "-map", f"{len(pngs) + 1}:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-shortest", "-movflags", "+faststart", str(D / "Second_Look_demo_final.mp4")]
mv.run(args)
e = subprocess.run([mv.FF, "-i", str(D / "Second_Look_demo_final.mp4")], capture_output=True, text=True).stderr
print("final:", re.search(r"Duration: ([\d:.]+)", e).group(1))
