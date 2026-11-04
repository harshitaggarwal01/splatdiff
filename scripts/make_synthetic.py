"""Generate synthetic sample pair with Muse Image + Ken-Burns pan videos."""
from __future__ import annotations
import io, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from splatdiff.meta_api import image_generate, image_edit
from splatdiff.video_io import pan_video_from_image

BEFORE_PROMPT = ("Photorealistic living room, wide shot: sofa, armchair, floor lamp in a corner, coffee table, "
                 "a blue backpack on the floor near the sofa, rug, bookshelf, natural light. No people, no text.")
AFTER_PROMPT = ("Edit this exact living room photo, same viewpoint and furniture: remove the blue backpack entirely, "
                "move the floor lamp to next to the armchair, add a red suitcase standing by the sofa. "
                "Keep everything else unchanged. No people, no text.")

def _save_jpg(raw: bytes, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(raw)).convert("RGB").save(path, "JPEG", quality=92)

def _png_bytes(path: Path) -> bytes:
    buf = io.BytesIO(); Image.open(path).convert("RGB").save(buf, "PNG"); return buf.getvalue()

def main():
    data = Path("data"); data.mkdir(exist_ok=True)
    before_jpg, after_jpg = data / "before.jpg", data / "after.jpg"
    if before_jpg.exists() and after_jpg.exists():
        print("Images already exist, skipping Muse Image generation.")
    else:
        print("Generating BEFORE image with muse-image-1.0…")
        _save_jpg(image_generate(BEFORE_PROMPT), before_jpg)
        print("Editing into AFTER image…")
        _save_jpg(image_edit(AFTER_PROMPT, _png_bytes(before_jpg)), after_jpg)
    print("Making pan videos…")
    pan_video_from_image(str(before_jpg), str(data / "sample_before.mp4"))
    pan_video_from_image(str(after_jpg), str(data / "sample_after.mp4"))
    gt = [{"concept": "blue backpack", "change": "removed"},
          {"concept": "backpack", "change": "removed"},
          {"concept": "floor lamp", "change": "moved"},
          {"concept": "red suitcase", "change": "added"}]
    # De-duplicate concept variants: keep canonical three used for eval
    gt = [{"concept": "backpack", "change": "removed"}, {"concept": "floor lamp", "change": "moved"},
          {"concept": "red suitcase", "change": "added"}]
    (data / "sample_gt.json").write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print("Wrote data/sample_before.mp4, data/sample_after.mp4, data/sample_gt.json")

if __name__ == "__main__":
    main()
