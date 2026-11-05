"""Build the final demo video from demo_raw.mp4 + scenes.json.

  python make_video.py captions            -> demo_captioned.mp4 (narration burned in as captions, raw timing)
  python make_video.py voice <audio_file>  -> demo_final.mp4 (each scene cut/held to fit the voice, voice muxed,
                                              captions kept on screen)
Voice is split into one segment per scene at its longest pauses (silencedetect).
"""
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

D = Path(__file__).resolve().parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1920, 1080
SCENES = json.loads((D / "scenes.json").read_text(encoding="utf-8"))
LINES = json.loads((D / "narration.json").read_text(encoding="utf-8"))
WORK = D / "work"
WORK.mkdir(exist_ok=True)


def run(args):
    subprocess.run([FF, "-y", "-loglevel", "error", *args], check=True)


def caption_png(text, path):
    """A calm bottom caption bar (paper on ink), transparent elsewhere."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 38)
    except OSError:
        font = ImageFont.load_default()
    lines = textwrap.wrap(text, width=78)[:4]
    lh = 50
    box_h = lh * len(lines) + 40
    y0 = H - box_h - 48
    d.rounded_rectangle([140, y0, W - 140, y0 + box_h], radius=18, fill=(30, 26, 22, 205))
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=font)
        d.text(((W - tw) / 2, y0 + 20 + i * lh), ln, font=font, fill=(251, 248, 242, 255))
    img.save(path)


def scene_clip(i, start, end, target, out):
    """Cut scene i from the raw video and fit it to `target` seconds (speed up to 1.6x, else trim; hold last frame if short)."""
    length = end - start
    factor = target / length if length > 0 else 1.0
    vf = []
    if factor < 1.0:
        speed = min(1.6, 1.0 / factor)
        vf.append(f"setpts=PTS/{speed:.4f}")
    else:
        speed = 1.0
    played = length / speed
    if played < target:
        vf.append(f"tpad=stop_mode=clone:stop_duration={target - played + 0.05:.3f}")
    vf.append("fps=30")
    run(["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(D / "demo_raw.mp4"),
         "-vf", ",".join(vf), "-t", f"{target:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "19", "-pix_fmt", "yuv420p", str(out)])


def overlay_captions(video_in, starts, durs, out, audio=None):
    pngs = []
    for i, text in enumerate(LINES[:len(starts)]):
        p = WORK / f"cap_{i}.png"
        caption_png(text, p)
        pngs.append(p)
    args = ["-i", str(video_in)]
    for p in pngs:
        args += ["-i", str(p)]
    if audio:
        args += ["-i", str(audio)]
    chain, last = [], "[0:v]"
    for i, (s, dur) in enumerate(zip(starts, durs)):
        nxt = f"[v{i}]"
        chain.append(f"{last}[{i + 1}:v]overlay=0:0:enable='between(t,{s:.2f},{s + dur - 0.15:.2f})'{nxt}")
        last = nxt
    args += ["-filter_complex", ";".join(chain), "-map", last]
    if audio:
        args += ["-map", f"{len(pngs) + 1}:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", str(out)]
    run(args)


def captions_only():
    starts = [s["start"] for s in SCENES]
    durs = [s["end"] - s["start"] for s in SCENES]
    overlay_captions(D / "demo_raw.mp4", starts, durs, D / "demo_captioned.mp4")
    print("wrote", D / "demo_captioned.mp4")


def voice_segments(wav, n):
    """Split the voice into n contiguous segments, cutting at the n-1 longest pauses."""
    p = subprocess.run([FF, "-i", str(wav), "-af", "silencedetect=noise=-35dB:d=0.7", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    total = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    gaps = [(e - s, (s + e) / 2) for s, e in zip(starts, ends) if s > 0.5 and e < total - 0.5]
    cuts = sorted(mid for _, mid in sorted(gaps, reverse=True)[:n - 1])
    if len(cuts) < n - 1:  # not enough pauses: split proportionally to the scripted line lengths
        weights = [len(t) for t in LINES[:n]]
        acc, cuts = 0, []
        for w in weights[:-1]:
            acc += w
            cuts.append(total * acc / sum(weights))
    bounds = [0.0] + cuts + [total]
    return [(bounds[i], bounds[i + 1]) for i in range(n)], total


def with_voice(audio):
    wav = WORK / "voice.wav"
    run(["-i", str(audio), "-ac", "1", "-ar", "48000", str(wav)])
    segs, total = voice_segments(wav, len(SCENES))
    clips, starts, t = [], [], 0.0
    for i, (sc, (a, b)) in enumerate(zip(SCENES, segs)):
        target = max(1.0, b - a)
        out = WORK / f"scene_{i:02d}.mp4"
        scene_clip(i, sc["start"], sc["end"], target, out)
        clips.append(out)
        starts.append(t)
        t += target
    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(WORK / "video_fit.mp4")])
    overlay_captions(WORK / "video_fit.mp4", starts, [b - a for a, b in segs], D / "demo_final.mp4", audio=wav)
    print("wrote", D / "demo_final.mp4", f"({total:.1f}s)")
    for i, ((a, b), sc) in enumerate(zip(segs, SCENES)):
        print(f"scene {i + 1}: voice {a:6.1f}-{b:6.1f}s ({b - a:4.1f}s) <- video {sc['end'] - sc['start']:4.1f}s")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "voice":
        with_voice(Path(sys.argv[2]))
    else:
        captions_only()
