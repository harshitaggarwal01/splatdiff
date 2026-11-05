"""Record the Second Look demo at 1920x1080 in scripted scene order, logging each scene's timing.

Run with the local server up (python server.py). Output: demo/raw/*.webm, demo/demo_raw.mp4, demo/scenes.json
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent
RAW = OUT / "raw"
W, H = 1920, 1080

CURSOR_JS = """
(() => {
  const add = () => {
    if (document.getElementById('__demo_cursor')) return;
    const c = document.createElement('div'); c.id='__demo_cursor';
    c.style.cssText='position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;'+
      'background:rgba(31,85,70,.25);border:2px solid #1F5546;z-index:2147483647;pointer-events:none;'+
      'transition:transform .12s ease-out;transform:translate(960px,540px)';
    document.documentElement.appendChild(c);
    window.addEventListener('mousemove', e => { c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`; }, true);
    window.addEventListener('mousedown', () => { c.style.background='rgba(31,85,70,.55)'; }, true);
    window.addEventListener('mouseup', () => { c.style.background='rgba(31,85,70,.25)'; }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
"""

scenes = []
T0 = None
mouse_xy = [W // 2, H // 2]


def now():
    return round(time.monotonic() - T0, 2)


def scene(name):
    if scenes and "end" not in scenes[-1]:
        scenes[-1]["end"] = now()
    scenes.append({"scene": name, "start": now()})
    print(f"[{now():6.1f}s] scene: {name}", flush=True)


def pause(page, s):
    page.wait_for_timeout(int(s * 1000))


def glide(page, x, y, steps=25):
    page.mouse.move(x, y, steps=steps)
    mouse_xy[0], mouse_xy[1] = x, y


def click(page, locator, settle=0.6):
    locator.scroll_into_view_if_needed(timeout=15000)
    box = locator.bounding_box()
    if box:
        glide(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pause(page, 0.25)
    locator.click(timeout=15000)
    pause(page, settle)


def smooth_scroll_to(page, locator, offset=120, duration=1.6):
    """Scroll so the element's top sits `offset` px below the viewport top, smoothly."""
    try:
        locator.wait_for(state="attached", timeout=15000)
    except Exception:
        return
    target = page.evaluate(
        "([el, off]) => Math.max(0, el.getBoundingClientRect().top + window.scrollY - off)",
        [locator.element_handle(), offset])
    start = page.evaluate("window.scrollY")
    steps = max(10, int(duration * 30))
    for i in range(1, steps + 1):
        t = i / steps
        ease = 1 - (1 - t) ** 3
        page.evaluate(f"window.scrollTo(0, {start + (target - start) * ease})")
        page.wait_for_timeout(int(duration * 1000 / steps))


def scroll_by(page, dy, duration=1.5):
    start = page.evaluate("window.scrollY")
    steps = max(10, int(duration * 30))
    for i in range(1, steps + 1):
        t = i / steps
        page.evaluate(f"window.scrollTo(0, {start + dy * (1 - (1 - t) ** 3)})")
        page.wait_for_timeout(int(duration * 1000 / steps))


def click_evidence(page, concept):
    """Click the Evidence disclosure inside the finding whose title starts with `concept`."""
    ok = page.evaluate("""(concept) => {
      const titles = [...document.querySelectorAll('h3,h4,.finding-title')]
        .filter(h => h.textContent.trim().toLowerCase().startsWith(concept.toLowerCase()));
      for (const t of titles) {
        let n = t;
        for (let i = 0; i < 6 && n; i++, n = n.parentElement) {
          const b = [...n.querySelectorAll('button, summary')].find(x => /evidence/i.test(x.textContent));
          if (b) { b.scrollIntoView({block: 'center'}); b.setAttribute('data-demo-evidence', '1'); return true; }
        }
      }
      return false;
    }""", concept)
    if ok:
        click(page, page.locator("[data-demo-evidence='1']").first, settle=1.0)
        page.evaluate("document.querySelectorAll('[data-demo-evidence]').forEach(e=>e.removeAttribute('data-demo-evidence'))")
    return ok


def open_past_check(page, text_regex):
    click(page, page.get_by_role("button", name="Past checks").first, settle=1.2)
    item = page.get_by_text(re.compile(text_regex)).first
    click(page, item, settle=1.8)


def main():
    global T0
    RAW.mkdir(parents=True, exist_ok=True)
    for f in RAW.glob("*.webm"):
        f.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                  record_video_dir=str(RAW), record_video_size={"width": W, "height": H})
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        T0 = time.monotonic()

        # 1. Hero
        scene("1 hero — know what changed, with proof")
        page.goto(BASE + "/", wait_until="networkidle")
        pause(page, 2.5)
        glide(page, 700, 420, 30); pause(page, 2.0)
        smooth_scroll_to(page, page.get_by_text("Finds every change.").first, offset=360, duration=2.0)
        pause(page, 5.0)

        # 2. How it works
        scene("2 how it works")
        smooth_scroll_to(page, page.get_by_role("heading", name="How it works").first, offset=140, duration=2.2)
        pause(page, 7.0)

        # 3. Try it now -> sample -> Check the room
        scene("3 try it now — sample room and watchlist")
        smooth_scroll_to(page, page.locator("body"), offset=0, duration=1.2)
        click(page, page.get_by_role("link", name="Try it now").nth(1), settle=2.5)
        smooth_scroll_to(page, page.get_by_text("Must stay put").first, offset=520, duration=1.6)
        pause(page, 3.0)
        click(page, page.get_by_role("button", name="Check the room").first, settle=0.5)

        # 4. Live check
        scene("4 live check — four Meta models working")
        page.get_by_role("heading", name=re.compile("Needs attention")).first.wait_for(timeout=180000)
        pause(page, 1.0)
        how = page.get_by_role("button", name="How this was checked")
        if how.count():
            click(page, how.first, settle=1.0)
            smooth_scroll_to(page, how.first, offset=140, duration=1.2)
            pause(page, 3.0)
            scroll_by(page, 900, duration=4.0)
            pause(page, 2.0)

        # 5. Report
        scene("5 report — needs attention, evidence, do this next")
        smooth_scroll_to(page, page.get_by_role("heading", name=re.compile("Needs attention")).first, offset=140, duration=1.6)
        pause(page, 3.5)
        click_evidence(page, "Floor lamp")
        pause(page, 4.0)
        scroll_by(page, 420, duration=1.4)
        pause(page, 3.0)

        # 6. Dad's choice (7:20 PM run)
        scene("6 dad's own words — moved on purpose")
        smooth_scroll_to(page, page.locator("body"), offset=0, duration=1.0)
        open_past_check(page, r"^Backpack removed, suitcase added, and watchlist floor lamp")
        dad = page.get_by_text(re.compile(r"Dad says")).first
        try:
            smooth_scroll_to(page, dad, offset=300, duration=1.8)
        except Exception:
            pass
        pause(page, 6.0)

        # 7. Real lab footage
        scene("7 real footage — chair moved, bin struck")
        smooth_scroll_to(page, page.locator("body"), offset=0, duration=1.0)
        open_past_check(page, r"Chair moved\. 1 unproven claim struck")
        smooth_scroll_to(page, page.get_by_role("heading", name="What changed").first, offset=140, duration=1.6)
        click_evidence(page, "Chair")
        pause(page, 5.0)
        smooth_scroll_to(page, page.get_by_role("heading", name=re.compile("Struck from the report")).first, offset=160, duration=1.8)
        pause(page, 6.0)

        # 8. Family feed + agent
        scene("8 family feed — words only, ask, update for Dad")
        page.goto(BASE + "/family", wait_until="networkidle")
        pause(page, 2.0)
        box = page.get_by_placeholder(re.compile("walker last seen", re.I)).first
        click(page, box, settle=0.3)
        box.press_sequentially("Where was his walker last seen?", delay=45)
        click(page, page.get_by_role("button", name="Ask", exact=True).first, settle=0.5)
        pause(page, 9.0)
        dad_opt = page.get_by_text("Dad", exact=True).first
        click(page, dad_opt, settle=0.4)
        click(page, page.get_by_role("button", name="Write it").first, settle=0.5)
        pause(page, 8.0)
        scroll_by(page, 260, duration=1.2)
        pause(page, 4.0)

        # 9. Glasses
        scene("9 in his glasses — simulation and memory")
        page.goto(BASE + "/glasses", wait_until="networkidle")
        pause(page, 1.5)
        click(page, page.get_by_role("button", name="Start").first, settle=0.5)
        smooth_scroll_to(page, page.get_by_role("heading", name=re.compile("In his glasses")).first, offset=40, duration=1.2)
        pause(page, 8.0)
        ask = page.get_by_placeholder("walker").first
        click(page, ask, settle=0.2)
        ask.press_sequentially("walker", delay=60)
        click(page, page.get_by_role("button", name=re.compile("Ask: where is my")).first, settle=0.5)
        pause(page, 5.0)

        # 10. Close
        scene("10 close — what it will never do, take a second look")
        page.goto(BASE + "/", wait_until="networkidle")
        pause(page, 0.8)
        smooth_scroll_to(page, page.get_by_role("heading", name="What it will never do").first, offset=180, duration=3.0)
        pause(page, 4.0)
        smooth_scroll_to(page, page.get_by_role("heading", name="Take a second look").first, offset=200, duration=2.0)
        pause(page, 5.0)
        scenes[-1]["end"] = now()

        video_path = page.video.path()
        ctx.close()
        browser.close()

    (OUT / "scenes.json").write_text(json.dumps(scenes, indent=2), encoding="utf-8")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    mp4 = OUT / "demo_raw.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(video_path), "-r", "30", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    print("video:", mp4)
    print(json.dumps(scenes, indent=1))


if __name__ == "__main__":
    sys.exit(main())
