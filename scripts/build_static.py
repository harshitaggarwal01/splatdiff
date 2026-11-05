#!/usr/bin/env python3
"""Build the static (GitHub Pages) site into docs/.

Implements the 'Build output' and 'Baked data' sections of
build_log/STATIC_CONTRACT.md.

Prerequisites:
  * The local server must be running, e.g. ``python server.py``
    (default http://127.0.0.1:8000, override with env SL_SERVER).
  * build_log/replay_events.json must already be recorded:
    {"run_id": ..., "events": [{..., "t": seconds}, ...]}

Usage:
  python scripts/build_static.py

It deletes and recreates docs/ on every run, bakes API data from the
live server, prefixes baked URLs with BASE, copies web assets / sample
videos / history-run images, rewrites absolute paths in the copied
HTML/JS/CSS, injects the static-mode head scripts, and prints a summary.
No API key is needed and nothing is sent anywhere except the local server.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "/splatdiff"
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SERVER = os.environ.get("SL_SERVER", "http://127.0.0.1:8000").rstrip("/")

# String values starting with one of these get BASE prefixed in baked JSON.
URL_PREFIXES = ("/outputs/", "/data/", "/web/")

# web source page -> destination (relative to docs/)
PAGES = [
    ("home.html", Path("index.html"), False),
    ("index.html", Path("app") / "index.html", True),
    ("family.html", Path("family") / "index.html", False),
    ("glasses.html", Path("glasses") / "index.html", False),
]

NAV_PAGES = ("app", "family", "glasses")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[build_static] {msg}", flush=True)


def prefix_urls(obj):
    """Recursively prefix BASE on string values starting with a URL prefix."""
    if isinstance(obj, str):
        if obj.startswith(BASE + "/"):
            return obj
        for prefix in URL_PREFIXES:
            if obj.startswith(prefix):
                return BASE + obj
        return obj
    if isinstance(obj, dict):
        return {k: prefix_urls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [prefix_urls(v) for v in obj]
    if isinstance(obj, tuple):
        return [prefix_urls(v) for v in obj]
    return obj


def fetch_json(path: str):
    """GET JSON from the local server; fail clearly if it is not up."""
    url = SERVER + path
    log(f"GET {url}")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:500]
        except Exception:
            pass
        raise SystemExit(
            f"error: GET {url} returned HTTP {exc.code}. {detail}\n"
            f"Is the local server running? Start it with: python server.py"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - connection refused etc.
        raise SystemExit(
            f"error: could not reach {url} ({exc}).\n"
            f"Is the local server running? Start it with: python server.py "
            f"(or set SL_SERVER to its base URL)."
        ) from exc
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"error: GET {url} did not return JSON: {exc}") from exc


def write_json(dest: Path, data) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    log(f"wrote {dest.relative_to(ROOT)}")


def build_agent_context(feed, rooms):
    """Words-only context via splatdiff.agent.build_context().

    The repo root is put on sys.path so ``import splatdiff...`` works no
    matter where this script is invoked from. Defensive about the exact
    call signature and about glasses feed entries whose run_id is None
    (mirroring server._agent_context()).
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from splatdiff import agent as agent_mod  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log(f"WARNING: could not import splatdiff.agent ({exc}); "
            "writing minimal agent_context.json from baked feed/rooms")
        return {"feed": feed or [], "rooms": rooms or []}

    # Sanitise None run_ids (glasses entries) like the server does.
    safe_feed = []
    for entry in feed if isinstance(feed, list) else []:
        if isinstance(entry, dict) and entry.get("run_id") is None:
            copied = dict(entry)
            copied["run_id"] = copied.get("id") or "glasses"
            safe_feed.append(copied)
        else:
            safe_feed.append(entry)

    attempts = [
        lambda: agent_mod.build_context(),
        lambda: agent_mod.build_context(feed_entries=safe_feed, rooms=rooms),
        lambda: agent_mod.build_context(safe_feed, rooms),
        lambda: agent_mod.build_context(feed_entries=safe_feed),
        lambda: agent_mod.build_context(safe_feed),
    ]
    last_exc = None
    for attempt in attempts:
        try:
            result = attempt()
            if isinstance(result, dict):
                return result
            return {"context": result}
        except TypeError as exc:
            last_exc = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log(f"WARNING: build_context() attempt failed ({exc}); trying another signature")
            continue
    log(f"WARNING: splatdiff.agent.build_context() failed ({last_exc}); "
        "writing minimal agent_context.json from baked feed/rooms")
    return {"feed": safe_feed, "rooms": rooms or []}


# --------------------------------------------------------------------------
# path rewriting
# --------------------------------------------------------------------------

def _rewrite_prefixed_paths(text: str) -> str:
    """'/web/' '/outputs/' '/data/' (after ", ' or () -> BASE + same."""
    for prefix in URL_PREFIXES:
        for opener in ('"', "'", "("):
            needle = f"{opener}{prefix}"
            # Already-BASE-prefixed occurrences begin with e.g. "/splatdiff/web/"
            # so the bare needle (quote + '/web/') cannot match them.
            text = text.replace(needle, f"{opener}{BASE}{prefix}")
    return text


def _nav_target(page: str, rest: str) -> str:
    """'/app' + rest -> '/splatdiff/app/' + rest ('?q' gets the slash before it)."""
    rest = rest or ""
    if rest in ("", "/"):
        return f"{BASE}/{page}/"
    if rest.startswith("?"):
        return f"{BASE}/{page}/{rest}"
    if rest.startswith("/"):
        return f"{BASE}/{page}{rest}"
    return f"{BASE}/{page}/{rest}"


_HREF_RE = re.compile(
    r"(href\s*=\s*)([\"'])(/(?:app|family|glasses)(?:/[^\s\"']*|\?[^\s\"']*)?|/(?:\?[^\s\"']*)?)\2"
)
_NAV_LITERAL_RE = re.compile(
    r"([\"'])/(app|family|glasses)((?:\?[^\"']*)?|/[^\s\"']*?)?\1"
)
_ROOT_LITERAL_RE = re.compile(r"([\"'])/\1")


def _rewrite_hrefs(text: str) -> str:
    def repl(m: "re.Match") -> str:
        prefix, quote, path = m.group(1), m.group(2), m.group(3)
        if path == "/" or path.startswith("/?"):
            rest = path[1:]  # '' or '?query'
            new = f"{BASE}/{rest}" if rest else f"{BASE}/"
            return f"{prefix}{quote}{new}{quote}"
        # /app, /app/, /app?query, /app/sub...
        body = path[1:]  # e.g. 'app?sample=1'
        page = body.split("/", 1)[0].split("?", 1)[0]
        rest = body[len(page):]
        return f"{prefix}{quote}{_nav_target(page, rest)}{quote}"

    return _HREF_RE.sub(repl, text)


def _rewrite_nav_literals(text: str) -> str:
    """JS string literals '/app', '/app?sample=1', '/family', '/glasses', '/'.

    Careful: never touches '/api/' (the patterns only match the exact
    navigation names above, or a bare '/').
    """
    def repl(m: "re.Match") -> str:
        quote, page, rest = m.group(1), m.group(2), m.group(3) or ""
        return f"{quote}{_nav_target(page, rest)}{quote}"

    text = _NAV_LITERAL_RE.sub(repl, text)
    # Bare '/' string literal -> BASE + '/'. Quoted only, so division etc.
    # in code is untouched; '/splatdiff/...' does not match either.
    text = _ROOT_LITERAL_RE.sub(lambda m: f"{m.group(1)}{BASE}/{m.group(1)}", text)
    return text


def rewrite_html(text: str) -> str:
    text = _rewrite_prefixed_paths(text)
    text = _rewrite_hrefs(text)
    text = _rewrite_nav_literals(text)
    return text


def rewrite_js_css(text: str) -> str:
    text = _rewrite_prefixed_paths(text)
    text = _rewrite_hrefs(text)
    text = _rewrite_nav_literals(text)
    return text


def inject_head(html: str, is_app: bool) -> str:
    """Insert the static-mode scripts as the FIRST thing in <head>."""
    scripts = (
        f'<script>window.SL_STATIC=true;window.SL_BASE="{BASE}";</script>'
        f'<script src="{BASE}/web/static-mode.js"></script>'
    )
    if is_app:
        scripts += f'<script src="{BASE}/web/browser-pipeline.js"></script>'
    m = re.search(r"<head\b[^>]*>", html, flags=re.IGNORECASE)
    if m:
        return html[: m.end()] + scripts + html[m.end():]
    m = re.search(r"<html\b[^>]*>", html, flags=re.IGNORECASE)
    if m:
        return html[: m.end()] + f"<head>{scripts}</head>" + html[m.end():]
    return f"<head>{scripts}</head>" + html


# --------------------------------------------------------------------------
# main build
# --------------------------------------------------------------------------

def main() -> int:
    log(f"BASE={BASE} server={SERVER} repo={ROOT}")

    # Delete and recreate docs/ each run.
    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True)
    log("recreated docs/")

    static_dir = DOCS / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    # ---- Baked data ------------------------------------------------------
    sample = prefix_urls(fetch_json("/api/sample"))
    history = prefix_urls(fetch_json("/api/history"))
    rooms = prefix_urls(fetch_json("/api/rooms"))
    feed = prefix_urls(fetch_json("/api/feed"))

    if not isinstance(history, list):
        log("WARNING: /api/history did not return a list; treating as empty")
        history = []

    write_json(static_dir / "sample.json", sample)
    write_json(static_dir / "history.json", history)
    write_json(static_dir / "rooms.json", rooms)
    write_json(static_dir / "feed.json", feed)

    run_ids = []
    for entry in history:
        if isinstance(entry, dict) and entry.get("run_id"):
            run_id = str(entry["run_id"])
            if "/" in run_id or "\\" in run_id or ".." in run_id:
                log(f"WARNING: skipping suspicious run_id {run_id!r}")
                continue
            run_ids.append(run_id)
    # De-dupe, preserve order.
    seen = set()
    run_ids = [r for r in run_ids if not (r in seen or seen.add(r))]

    for run_id in run_ids:
        full = prefix_urls(fetch_json(f"/api/history/{urllib.parse.quote(run_id, safe='')}"))
        write_json(static_dir / "history" / f"{run_id}.json", full)

    # replay.json from the already-recorded server run.
    replay_src = ROOT / "build_log" / "replay_events.json"
    if replay_src.is_file():
        try:
            replay = json.loads(replay_src.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log(f"WARNING: could not parse {replay_src}: {exc}; writing empty replay.json")
            replay = {"run_id": None, "events": []}
    else:
        log(f"WARNING: {replay_src} not found; writing empty replay.json")
        replay = {"run_id": None, "events": []}
    # Same shape the contract describes; URLs inside (incl. the final
    # result event) get BASE-prefixed like every other baked file.
    replay = prefix_urls(replay)
    write_json(static_dir / "replay.json", replay)

    # agent_context.json (words-only) via splatdiff.agent.build_context().
    agent_context = prefix_urls(build_agent_context(feed, rooms))
    write_json(static_dir / "agent_context.json", agent_context)

    # ---- Copy web assets --------------------------------------------------
    web_src = ROOT / "web"
    web_dst = DOCS / "web"
    web_dst.mkdir(parents=True, exist_ok=True)
    web_files = 0
    if web_src.is_dir():
        for pattern in ("*.css", "*.js"):
            for src in sorted(web_src.glob(pattern)):
                if src.is_file():
                    shutil.copyfile(src, web_dst / src.name)
                    web_files += 1
        assets_src = web_src / "assets"
        if assets_src.is_dir():
            for src in sorted(assets_src.rglob("*")):
                if src.is_file():
                    dest = web_dst / "assets" / src.relative_to(assets_src)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
                    web_files += 1
    else:
        log("WARNING: web/ not found; no web assets copied")
    log(f"copied {web_files} web asset file(s) to docs/web/")

    # Rewrite absolute paths in the copied JS/CSS.
    rewritten_assets = 0
    for pattern in ("*.js", "*.css"):
        for path in sorted(web_dst.glob(pattern)):
            original = path.read_text(encoding="utf-8", errors="replace")
            rewritten = rewrite_js_css(original)
            if rewritten != original:
                path.write_text(rewritten, encoding="utf-8")
                rewritten_assets += 1
    log(f"rewrote absolute paths in {rewritten_assets} docs/web/*.js/*.css file(s)")

    # ---- Copy sample videos ----------------------------------------------
    data_dst = DOCS / "data"
    data_dst.mkdir(parents=True, exist_ok=True)
    videos = 0
    for name in ("sample_before.mp4", "sample_after.mp4"):
        src = ROOT / "data" / name
        if src.is_file():
            shutil.copyfile(src, data_dst / name)
            videos += 1
        else:
            log(f"WARNING: data/{name} not found; skipping")
    log(f"copied {videos} sample video(s) to docs/data/")

    # ---- Copy history-run outputs (only .jpg/.json) ----------------------
    run_files = 0
    for run_id in run_ids:
        src_dir = ROOT / "outputs" / run_id
        if not src_dir.is_dir():
            log(f"WARNING: outputs/{run_id}/ not found; skipping its files")
            continue
        count = 0
        for src in sorted(src_dir.rglob("*")):
            if src.is_file() and src.suffix.lower() in (".jpg", ".json"):
                dest = DOCS / "outputs" / run_id / src.relative_to(src_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                count += 1
        run_files += count
        log(f"copied {count} file(s) for run {run_id} to docs/outputs/{run_id}/")
    log(f"copied {run_files} history-run file(s) total")

    # ---- Pages -------------------------------------------------------------
    pages_written = 0
    for src_name, rel_dest, is_app in PAGES:
        src = web_src / src_name
        dest = DOCS / rel_dest
        if not src.is_file():
            log(f"WARNING: web/{src_name} not found; skipping page {rel_dest}")
            continue
        html = src.read_text(encoding="utf-8", errors="replace")
        html = rewrite_html(html)
        html = inject_head(html, is_app=is_app)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        pages_written += 1
        log(f"page web/{src_name} -> docs/{rel_dest.as_posix()}"
            + (" (+ browser-pipeline.js)" if is_app else ""))

    # ---- .nojekyll + 404 ---------------------------------------------------
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    not_found = (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Second Look</title>"
        f'<meta http-equiv="refresh" content="0; url={BASE}/">'
        f'<script>window.location.replace("{BASE}/");</script>'
        "</head><body>"
        f'<p>Redirecting to <a href="{BASE}/">Second Look</a>&hellip;</p>'
        "</body></html>\n"
    )
    (DOCS / "404.html").write_text(not_found, encoding="utf-8")
    log("wrote docs/.nojekyll and docs/404.html")

    # ---- Summary ------------------------------------------------------------
    total_files = sum(1 for p in DOCS.rglob("*") if p.is_file())
    total_bytes = sum(p.stat().st_size for p in DOCS.rglob("*") if p.is_file())
    print()
    print("=== SplatDiff static build summary ===")
    print(f"BASE:            {BASE}")
    print(f"Server:          {SERVER}")
    print(f"Output:          {DOCS}")
    print(f"Pages:           {pages_written} written")
    print(f"Baked JSON:      docs/static/sample.json, history.json "
          f"(+{len(run_ids)} run file(s)), rooms.json, feed.json, "
          f"replay.json, agent_context.json")
    print(f"History runs:    {', '.join(run_ids) if run_ids else '(none)'}")
    print(f"Web assets:      {web_files} copied, {rewritten_assets} rewritten")
    print(f"Sample videos:   {videos} copied")
    print(f"Run output files:{run_files} (.jpg/.json only)")
    print(f"Total:           {total_files} files, {total_bytes / 1_000_000:.2f} MB in docs/")
    print(f"Preview locally: cd docs && python -m http.server 8080 "
          f"(then open http://127.0.0.1:8080{BASE}/ — note paths are absolute under {BASE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
