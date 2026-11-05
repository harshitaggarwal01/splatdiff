/* SplatDiff / Second Look - browser pipeline.
 * Keyframe-based port of splatdiff/pipeline.py for static (GitHub Pages)
 * mode. No ffmpeg and no video upload: keyframes are drawn on canvases and
 * every model call goes through window.SL.meta (visitor's own key, this tab
 * only, api.meta.ai only). Plain ES2019, IIFE, no dependencies.
 *
 * window.SLBrowserPipeline.run(opts) -> Promise<result>
 *   opts = { beforeFile, afterFile, watchlist, room, filmedBy, onEvent }
 *          (before/after / before_file/after_file / progress also accepted)
 * The result shape mirrors the Python pipeline result (UI_CONTRACT /
 * CONTRACT_V3): summary, kept_claims, dropped_claims, raw_claims,
 * watchlist_status, summaries, coverage, privacy, floor_check, stats,
 * models, cost_usd, elapsed_s, run_id, room, filmed_by. All image URLs are
 * data: URLs (JPEG 0.85). Every event carries elapsed_s and cost_usd.
 */
(function () {
  "use strict";

  var SPARK_MODEL = "muse-spark-1.3";
  var SAM_MODEL = "sam-3.1";
  var MODELS = ["muse-spark-1.3", "sam-3.1"];
  var SAM_IMAGE_USD = 0.0025; /* $2.50 per 1000 images */
  var SPARK_INPUT_PER_TOKEN = 1.25 / 1000000;
  var SPARK_OUTPUT_PER_TOKEN = 4.25 / 1000000;
  var CONCURRENCY = 6;
  var KEYFRAMES = 6;
  var FRAME_WIDTH = 640;

  /* Presence / grounding constants. Browser keyframe tracking uses the
   * STATIC_CONTRACT thresholds (frames_detected counts c >= 0.5 on a
   * keyframe; present = frames_detected >= 1 AND best c >= 0.6), while the
   * grounding filter ports splatdiff/diff.py (MOVED_MIN_CONF = 0.8). */
  var TRACK_CONF = 0.5;
  var PRESENT_BEST_CONF = 0.6;
  var PRIVACY_CONF = 0.4;
  var MOVED_MIN_CONF = 0.8;

  var ANCHOR_WORDS = ["bed", "sofa", "couch", "armchair", "chair", "table",
    "dresser", "wardrobe", "cabinet", "desk", "bookshelf", "nightstand"];

  function norm(s) {
    return String(s == null ? "" : s).toLowerCase().replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "");
  }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function runId() {
    var d = new Date();
    return "local-" + d.getFullYear() + pad2(d.getMonth() + 1) + pad2(d.getDate()) +
      "_" + pad2(d.getHours()) + pad2(d.getMinutes()) + pad2(d.getSeconds());
  }
  function isAnchor(concept) {
    var n = norm(concept);
    for (var i = 0; i < ANCHOR_WORDS.length; i++) if (n.indexOf(ANCHOR_WORDS[i]) !== -1) return true;
    return false;
  }
  function cleanList(v) {
    var arr = [];
    if (!v) return arr;
    if (typeof v === "string") arr = v.split(",");
    else if (Object.prototype.toString.call(v) === "[object Array]") arr = v;
    else arr = [v];
    var out = [], seen = {};
    for (var i = 0; i < arr.length; i++) {
      var c = norm(arr[i]);
      if (c && !seen[c]) { seen[c] = true; out.push(c); }
    }
    return out;
  }
  function cleanRisk(v) {
    var r = norm(v);
    return (r === "high" || r === "medium" || r === "low") ? r : null;
  }
  function isWatchlist(concept, watchNorm) {
    var n = norm(concept);
    if (!n || !watchNorm.length) return false;
    if (watchNorm.indexOf(n) !== -1) return true;
    var nt = n.split(" ");
    for (var i = 0; i < watchNorm.length; i++) {
      var wt = watchNorm[i].split(" ");
      for (var j = 0; j < nt.length; j++) if (wt.indexOf(nt[j]) !== -1) return true;
    }
    return false;
  }

  /* ---------------- concurrency helper (limit 6) ---------------- */
  function mapLimit(items, limit, fn) {
    return new Promise(function (resolve, reject) {
      var results = new Array(items.length);
      var next = 0, active = 0, done = false;
      if (!items.length) { resolve(results); return; }
      function launch() {
        while (!done && active < limit && next < items.length) {
          (function (idx) {
            active++;
            Promise.resolve().then(function () { return fn(items[idx], idx); }).then(function (v) {
              results[idx] = v; active--;
              if (next >= items.length && active === 0) { done = true; resolve(results); }
              else launch();
            }, function (e) {
              if (!done) { done = true; reject(e); }
            });
          })(next++);
        }
      }
      launch();
    });
  }

  /* ---------------- canvas helpers ---------------- */
  function canvasToUrl(c) { return c.toDataURL("image/jpeg", 0.85); }
  function cloneCanvas(src) {
    var c = document.createElement("canvas");
    c.width = src.width; c.height = src.height;
    c.getContext("2d").drawImage(src, 0, 0);
    return c;
  }
  function blurBox(canvas, box) {
    if (!box || box.length < 4) return;
    var w = canvas.width, h = canvas.height;
    var bw = Math.max(1, box[2] - box[0]), bh = Math.max(1, box[3] - box[1]);
    var px = bw * 0.10, py = bh * 0.10;
    var x1 = Math.max(0, Math.floor(box[0] - px)), y1 = Math.max(0, Math.floor(box[1] - py));
    var x2 = Math.min(w, Math.ceil(box[2] + px)), y2 = Math.min(h, Math.ceil(box[3] + py));
    if (x2 <= x1 || y2 <= y1) return;
    var tmp = document.createElement("canvas");
    tmp.width = x2 - x1; tmp.height = y2 - y1;
    tmp.getContext("2d").drawImage(canvas, x1, y1, tmp.width, tmp.height, 0, 0, tmp.width, tmp.height);
    var ctx = canvas.getContext("2d");
    ctx.save();
    try { ctx.filter = "blur(14px)"; } catch (e) { /* filter unsupported: still overdraw scaled */ }
    /* Draw slightly enlarged so blurred edges do not leak the original. */
    ctx.drawImage(tmp, x1 - 7, y1 - 7, tmp.width + 14, tmp.height + 14);
    ctx.restore();
    try { ctx.filter = "none"; } catch (e2) {}
  }
  function drawBox(canvas, box, label, color) {
    var out = cloneCanvas(canvas);
    if (!box || box.length < 4) return out;
    var ctx = out.getContext("2d");
    var x1 = box[0], y1 = box[1], x2 = box[2], y2 = box[3];
    ctx.strokeStyle = color; ctx.lineWidth = Math.max(3, out.width / 160);
    ctx.strokeRect(x1, y1, Math.max(1, x2 - x1), Math.max(1, y2 - y1));
    if (label) {
      var text = String(label);
      ctx.font = "bold " + Math.max(14, Math.round(out.width / 28)) + "px sans-serif";
      var tw = ctx.measureText(text).width + 14, th = Math.max(22, Math.round(out.width / 22));
      var ty = Math.max(0, y1 - th);
      ctx.fillStyle = color; ctx.fillRect(x1, ty, tw, th);
      ctx.fillStyle = "#ffffff"; ctx.textBaseline = "middle";
      ctx.fillText(text, x1 + 7, ty + th / 2);
    }
    return out;
  }
  function cropDataUrl(canvas, box) {
    if (!box || box.length < 4) return null;
    var w = canvas.width, h = canvas.height;
    var bw = Math.max(1, box[2] - box[0]), bh = Math.max(1, box[3] - box[1]);
    var px = Math.round(0.6 * bw), py = Math.round(0.6 * bh);
    var x1 = Math.max(0, box[0] - px), y1 = Math.max(0, box[1] - py);
    var x2 = Math.min(w, box[2] + px), y2 = Math.min(h, box[3] + py);
    if (x2 <= x1 || y2 <= y1) return null;
    var c = document.createElement("canvas");
    c.width = x2 - x1; c.height = y2 - y1;
    c.getContext("2d").drawImage(canvas, x1, y1, c.width, c.height, 0, 0, c.width, c.height);
    return canvasToUrl(c);
  }
  var CHANGE_COLORS = { added: "#1a9e4b", removed: "#d43a2f", moved: "#ef8b0c", on_floor: "#b03a2e" };

  /* ---------------- video keyframes ---------------- */
  function loadVideo(file, label) {
    return new Promise(function (resolve, reject) {
      if (!file) { reject(new Error("No " + label + " video was provided.")); return; }
      var url = (typeof file === "string") ? file : URL.createObjectURL(file);
      var video = document.createElement("video");
      video.muted = true; video.playsInline = true; video.preload = "auto";
      video.style.display = "none";
      document.body.appendChild(video);
      var settled = false;
      var timer = setTimeout(function () {
        if (!settled) { settled = true; cleanup(); reject(new Error("The browser could not decode the " + label + " video (timed out). Try an MP4/H.264 clip.")); }
      }, 60000);
      function cleanup() {
        clearTimeout(timer);
        try { video.pause(); } catch (e) {}
        if (video.parentNode) video.parentNode.removeChild(video);
        if (typeof file !== "string") { try { URL.revokeObjectURL(url); } catch (e2) {} }
      }
      video.onerror = function () {
        if (!settled) { settled = true; cleanup(); reject(new Error("The browser could not decode the " + label + " video. Try an MP4/H.264 clip.")); }
      };
      video.onloadedmetadata = function () {
        if (settled) return;
        if (!isFinite(video.duration) || video.duration <= 0 || !video.videoWidth) {
          settled = true; cleanup();
          reject(new Error("The browser could not read the " + label + " video. Try an MP4/H.264 clip."));
          return;
        }
        settled = true;
        resolve({ video: video, url: url, cleanup: cleanup, isObjectUrl: typeof file !== "string" });
      };
      video.src = url;
    });
  }
  function seekTo(video, t) {
    return new Promise(function (resolve, reject) {
      var done = false;
      var timer = setTimeout(function () { if (!done) { done = true; reject(new Error("Seeking in the video timed out.")); } }, 20000);
      function onSeeked() {
        if (done) return; done = true; clearTimeout(timer);
        video.removeEventListener("seeked", onSeeked);
        resolve();
      }
      video.addEventListener("seeked", onSeeked);
      try { video.currentTime = t; } catch (e) { clearTimeout(timer); reject(e); }
    });
  }
  function extractKeyframes(file, label) {
    var handle = null;
    return loadVideo(file, label).then(function (h) {
      handle = h;
      var video = h.video;
      var scale = FRAME_WIDTH / video.videoWidth;
      var cw = FRAME_WIDTH, ch = Math.max(2, Math.round(video.videoHeight * scale));
      if (ch % 2 === 1) ch += 1;
      var frames = [];
      var chain = Promise.resolve();
      var i;
      function step(idx) {
        return function () {
          var t = (idx + 0.5) * video.duration / KEYFRAMES;
          t = Math.min(Math.max(t, 0), Math.max(0, video.duration - 0.05));
          return seekTo(video, t).then(function () {
            var c = document.createElement("canvas");
            c.width = cw; c.height = ch;
            c.getContext("2d").drawImage(video, 0, 0, cw, ch);
            frames.push({ canvas: c, dataUrl: canvasToUrl(c), w: cw, h: ch, index: idx });
          });
        };
      }
      for (i = 0; i < KEYFRAMES; i++) chain = chain.then(step(i));
      return chain.then(function () { return frames; });
    }).then(function (frames) {
      if (handle) handle.cleanup();
      if (!frames || frames.length !== KEYFRAMES) throw new Error("Could not extract keyframes from the " + label + " video.");
      return frames;
    }, function (err) {
      if (handle) handle.cleanup();
      throw err;
    });
  }

  /* ---------------- run ---------------- */
  function run(opts) {
    opts = opts || {};
    if (!window.SL || !window.SL.meta) {
      return Promise.reject(new Error("window.SL.meta is not available; browser pipeline cannot run."));
    }
    var meta = window.SL.meta;
    var beforeFile = opts.beforeFile || opts.before_file || opts.before || null;
    var afterFile = opts.afterFile || opts.after_file || opts.after || null;
    var watchlist = cleanList(opts.watchlist || opts.concepts || null);
    var room = String(opts.room || "Bedroom");
    var filmedBy = opts.filmedBy || opts.filmed_by || null;
    var onEvent = (typeof opts.onEvent === "function") ? opts.onEvent
      : (typeof opts.progress === "function") ? opts.progress : null;

    var started = Date.now();
    var costUsd = 0;
    var sparkCalls = 0, samCalls = 0, sparkInputTokens = 0, sparkOutputTokens = 0;
    var privacyChecks = 0, coverageCalls = 0;
    var id = runId();

    function elapsed() { return Math.round(((Date.now() - started) / 1000) * 1000) / 1000; }
    function emit(stage, status, extra) {
      var ev = { stage: stage, status: status, elapsed_s: elapsed(), cost_usd: Math.round(costUsd * 10000) / 10000, run_id: id };
      if (extra) for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) ev[k] = extra[k];
      if (onEvent) { try { onEvent(ev); } catch (e) { /* listener errors must not kill the run */ } }
      return ev;
    }

    /* --- SAM wrapper: every call counted at $0.0025/image --- */
    function samImage(dataUrl, concept) {
      samCalls++;
      costUsd += SAM_IMAGE_USD;
      return meta.samImage(dataUrl, concept).then(function (dets) {
        return (dets || []).filter(function (d) { return d && d.box && d.box.length >= 4; });
      });
    }

    /* --- Spark wrapper: strict JSON, retry once on non-JSON/empty --- */
    function textPart(text) { return { type: "input_text", text: text }; }
    function imagePart(url) { return { type: "input_image", image_url: url }; }
    function sparkJson(content, maxTokens, what) {
      var lastErr = null;
      function attempt(retry) {
        sparkCalls++;
        var body = {
          model: SPARK_MODEL,
          input: [{ type: "message", role: "user", content: content }],
          reasoning: { effort: "low" },
          max_output_tokens: retry ? 8000 : (maxTokens || 4000)
        };
        if (retry) body.metadata = { retry: "1" };
        return meta.responses(body).then(function (resp) {
          var usage = (resp && resp.usage) || {};
          var inTok = Number(usage.input_tokens || 0) || 0;
          var outTok = Number(usage.output_tokens || 0) || 0;
          sparkInputTokens += inTok; sparkOutputTokens += outTok;
          costUsd += inTok * SPARK_INPUT_PER_TOKEN + outTok * SPARK_OUTPUT_PER_TOKEN;
          var text = meta.text(resp);
          if (!text || !String(text).replace(/\s+/g, "")) throw new Error("empty text, cannot parse JSON");
          var data = meta.json(text);
          if (data == null || typeof data !== "object") throw new Error("Spark returned non-JSON for " + what);
          return data;
        });
      }
      return attempt(false).catch(function (e) {
        lastErr = e;
        return attempt(true);
      }).catch(function () { throw lastErr || new Error("Spark call failed: " + what); });
    }

    /* --- prompts ported from splatdiff/spark.py --- */
    function inventoryContent(before, after) {
      var content = [textPart(
        "You are inventorying a room from phone-video keyframes. Images are labelled BEFORE frame i and AFTER frame i; " +
        "camera viewpoint may differ. List at most 10 movable household objects visible in either set. Prioritise movable " +
        "household objects (lamp, chair, backpack, suitcase, walker, plant, box, book, cushion, etc.), short singular noun " +
        "phrases SAM can segment. Return STRICT JSON only, no markdown: " +
        '{"objects": [{"concept": "floor lamp", "where_before": "str", "where_after": "str", ' +
        '"suspected_change": "added|removed|moved|unchanged"}]}')];
      var i;
      for (i = 0; i < before.length; i++) { content.push(textPart("BEFORE frame " + i)); content.push(imagePart(before[i].dataUrl)); }
      for (i = 0; i < after.length; i++) { content.push(textPart("AFTER frame " + i)); content.push(imagePart(after[i].dataUrl)); }
      return content;
    }
    function coverageContent(before, after) {
      var content = [textPart(
        "You are checking whether two phone walkthroughs of the same room cover the same parts of the room. " +
        "Images are labelled BEFORE frame i and AFTER frame i; camera viewpoints and order may differ. " +
        "Judge which areas/corners/landmarks (e.g. 'bathroom door corner', 'window wall', 'bedside') are visible " +
        "in one walkthrough but not the other. Return STRICT JSON only, no markdown: " +
        '{"score": 0.0, "missing_in_after": ["area str"], "missing_in_before": ["area str"], "retake_tip": "str"} ' +
        "with score in 0..1 (1 = both walkthroughs cover essentially the same parts of the room, 0 = almost no " +
        "overlap). retake_tip is one short plain sentence telling the filmer what to re-film if coverage differs, " +
        "or an empty string if coverage is good.")];
      var i;
      for (i = 0; i < Math.min(3, before.length); i++) { content.push(textPart("BEFORE frame " + i)); content.push(imagePart(before[i].dataUrl)); }
      for (i = 0; i < Math.min(3, after.length); i++) { content.push(textPart("AFTER frame " + i)); content.push(imagePart(after[i].dataUrl)); }
      return content;
    }
    function aliasesContent(concept, before, after) {
      var content = [textPart(
        "The object '" + concept + "' was not found by a text-prompted segmentation model (SAM) " +
        "under that name in these room photos. Give up to 3 alternative short visual noun phrases a " +
        "text-prompted segmentation model would recognise for this object as it appears in these photos " +
        "(e.g. walker -> 'walking frame', 'metal walker'). Use short singular visual noun phrases that " +
        "describe what the object looks like, not its function alone. Do not repeat the original concept. " +
        'Return STRICT JSON only, no markdown: {"aliases": ["...", "..."]}')];
      var i;
      for (i = 0; i < Math.min(2, before.length); i++) { content.push(textPart("BEFORE frame " + i)); content.push(imagePart(before[i].dataUrl)); }
      for (i = 0; i < Math.min(2, after.length); i++) { content.push(textPart("AFTER frame " + i)); content.push(imagePart(after[i].dataUrl)); }
      return content;
    }
    function judgeContent(concept, beforeFrame, afterFrame, bBox, aBox) {
      var bAnn = canvasToUrl(drawBox(beforeFrame.canvas, bBox, concept, "#ef8b0c"));
      var aAnn = canvasToUrl(drawBox(afterFrame.canvas, aBox, concept, "#ef8b0c"));
      var content = [textPart(
        "The orange box marks '" + concept + "' in the BEFORE frame and the AFTER frame of the same room. " +
        "Camera viewpoint differs between videos, so do NOT judge by raw pixel position. Judge position relative to " +
        "surrounding furniture and room landmarks. Also shown are context crops. Return STRICT JSON only: " +
        '{"moved": true, "confidence": 0.0, "reason": "short reason"} with confidence in 0..1.'),
        textPart("BEFORE full frame"), imagePart(bAnn),
        textPart("AFTER full frame"), imagePart(aAnn)];
      var bc = cropDataUrl(drawBox(beforeFrame.canvas, bBox, concept, "#ef8b0c"), bBox);
      var ac = cropDataUrl(drawBox(afterFrame.canvas, aBox, concept, "#ef8b0c"), aBox);
      if (bc) { content.push(textPart("BEFORE crop")); content.push(imagePart(bc)); }
      if (ac) { content.push(textPart("AFTER crop")); content.push(imagePart(ac)); }
      return content;
    }
    function claimsContent(diffTable, movedVerdicts) {
      var watchText = "The caregiver WATCHLIST (items that must stay put and matter most): " +
        (watchlist.length ? watchlist.join(", ") : "(none)") +
        ". Changes to watchlist items should normally be high risk unless " +
        "the evidence clearly shows the item remains safely within reach. ";
      var payload = { diff_table: diffTable, moved_verdicts: movedVerdicts, watchlist: watchlist };
      return [textPart(
        "You are writing a grounded room-change report (caregiver safety / rental inspection). Below is SAM 3.1 evidence " +
        "per concept: presence, frames detected, boxes, confidences, SAM label (added/removed/present_both/not_found) and " +
        "pairwise moved verdicts. Write claims ONLY for real changes (added/removed/moved). Do not invent objects. " +
        watchText +
        "For EVERY claim also judge 'risk' (\"high\"|\"medium\"|\"low\") and 'risk_reason' (short str) through a caregiver " +
        "fall/safety lens for an older adult living alone: HIGH = trip hazards on the floor, or mobility aids (walker, " +
        "cane), medication, or a phone moved out of reach / missing, or anything blocking a walkway to the bed, chair, " +
        "bathroom or exit; MEDIUM = changes that could plausibly affect safety, reach, lighting or daily routine but are " +
        "not an immediate fall/reach hazard; LOW = cosmetic or safety-irrelevant changes (decor, cushions, books). " +
        "Return STRICT JSON only: {\"summary\": \"str\", \"claims\": [{\"concept\": \"str\", " +
        "\"change\": \"added|removed|moved\", \"explanation\": \"str\", \"safety_note\": \"str or null\", " +
        "\"risk\": \"high|medium|low\", \"risk_reason\": \"str\"}]}. " +
        "safety_note: a short caregiver/rental-relevant note or null.\nDATA:\n" + JSON.stringify(payload))];
    }

    /* --- tracking summaries (port of diff.summarize_track scoring) --- */
    function summarizeSide(perFrame) {
      var frames = 0, confs = [], maxInst = 0;
      var bestFrame = null, bestBox = null, bestC = 0, bestScore = -1;
      perFrame.forEach(function (dets, idx) {
        var good = (dets || []).filter(function (d) { return Number(d.c || 0) >= TRACK_CONF; });
        if (!good.length) return;
        frames++; maxInst = Math.max(maxInst, good.length);
        good.forEach(function (d) {
          var c = Number(d.c || 0); confs.push(c);
          var box = d.box, centrality = 1.0, areaFrac = 0;
          var w = Number(d.w || 0), h = Number(d.h || 0);
          if (box && box.length >= 4 && w > 0 && h > 0) {
            var touches = box[0] < 2 || box[1] < 2 || box[2] > w - 2 || box[3] > h - 2;
            centrality = touches ? 0.5 : 1.0;
            areaFrac = Math.max(0, (box[2] - box[0]) * (box[3] - box[1])) / (w * h);
          }
          var score = c * centrality * (0.75 + 0.25 * Math.min(1, areaFrac * 8));
          if (score > bestScore) { bestScore = score; bestC = c; bestFrame = idx; bestBox = box ? box.slice() : null; }
        });
      });
      var present = frames >= 1 && bestC >= PRESENT_BEST_CONF;
      return {
        frames_detected: frames, max_instances: maxInst,
        mean_conf: confs.length ? confs.reduce(function (a, b) { return a + b; }, 0) / confs.length : 0,
        best_frame: bestFrame, best_box: bestBox, best_conf: bestC, present: present
      };
    }
    function labelOf(b, a) {
      if (a.present && !b.present) return "added";
      if (b.present && !a.present) return "removed";
      if (b.present && a.present) return "present_both";
      return "not_found";
    }
    function trackConcept(frames, concept) {
      return mapLimit(frames, CONCURRENCY, function (f) {
        return samImage(f.dataUrl, concept).catch(function () { return []; });
      }).then(summarizeSide);
    }

    /* --- grounding filter (port of diff.grounding_filter) --- */
    function evidence(key, s) {
      return {
        concept: key, label: s.label, original_label: s.original_label || s.label, recheck: s.recheck || null,
        frames_before: s.before.frames_detected, frames_after: s.after.frames_detected,
        best_box_before: s.before.best_box, best_box_after: s.after.best_box,
        best_frame_before: s.before.best_frame, best_frame_after: s.after.best_frame,
        confidence_before: s.before.best_conf, confidence_after: s.after.best_conf,
        mean_conf_before: s.before.mean_conf, mean_conf_after: s.after.mean_conf,
        max_instances_before: s.before.max_instances, max_instances_after: s.after.max_instances
      };
    }
    function findConcept(raw, summaries) {
      var n = norm(raw);
      if (summaries[n]) return { key: n, s: summaries[n] };
      var bestKey = null, bestS = null, bestOverlap = 0;
      Object.keys(summaries).forEach(function (k) {
        var kt = norm(k).split(" "), nt = n.split(" "), ov = 0;
        kt.forEach(function (t) { if (nt.indexOf(t) !== -1) ov++; });
        if (ov > bestOverlap) { bestOverlap = ov; bestKey = k; bestS = summaries[k]; }
      });
      return bestKey ? { key: bestKey, s: bestS } : { key: null, s: null };
    }
    function claimRisk(claim, concept) {
      var r = cleanRisk(claim.risk);
      if (r) return { risk: r, risk_reason: String(claim.risk_reason || "") };
      if (isWatchlist(concept, watchlist)) {
        return { risk: "high", risk_reason: String(claim.risk_reason || "") || ("'" + concept + "' is on the caregiver watchlist, so any change to it is treated as high risk.") };
      }
      return { risk: "medium", risk_reason: String(claim.risk_reason || "") };
    }
    function samOnlyRisk(concept, change) {
      if (isWatchlist(concept, watchlist)) {
        return { risk: "high", risk_reason: "'" + concept + "' is on the caregiver watchlist and SAM detected it as " + change + "; check it is within reach and not a trip hazard." };
      }
      return { risk: "medium", risk_reason: "SAM detected '" + concept + "' as " + change + " but Spark did not assess it; defaulting to medium risk pending a caregiver check." };
    }
    function coverageDropReason(change, coverage) {
      var area = "";
      var ordered = [];
      if (coverage) {
        if (change === "removed") ordered = (coverage.missing_in_after || []).concat(coverage.missing_in_before || []);
        else if (change === "added") ordered = (coverage.missing_in_before || []).concat(coverage.missing_in_after || []);
        else ordered = (coverage.missing_in_after || []).concat(coverage.missing_in_before || []);
        for (var i = 0; i < ordered.length; i++) if (String(ordered[i]).replace(/\s+/g, "")) { area = String(ordered[i]); break; }
        if (!area && coverage.retake_tip && String(coverage.retake_tip).length <= 60) area = String(coverage.retake_tip);
      }
      return "Not covered by both walkthroughs \u2014 re-film " + (area || "that corner") + " before trusting this.";
    }
    function groundingFilter(rawClaims, summaries, movedVerdicts, coverage) {
      var kept = [], dropped = [], keptConcepts = {};
      var coverageBad = !!(coverage && coverage.ok === false);
      (rawClaims || []).forEach(function (claim) {
        if (!claim || typeof claim !== "object") {
          dropped.push({ concept: String(claim), change: null, explanation: "", safety_note: null, risk: "medium", risk_reason: "", reason: "malformed claim (not an object)" });
          return;
        }
        var conceptRaw = String(claim.concept || ""), change = claim.change;
        var found = findConcept(conceptRaw, summaries);
        var rr = claimRisk(claim, found.key || conceptRaw);
        if (!found.s) {
          var d0 = {}; for (var k0 in claim) d0[k0] = claim[k0];
          d0.concept = conceptRaw; d0.risk = rr.risk; d0.risk_reason = rr.risk_reason;
          d0.reason = "no SAM evidence: concept '" + conceptRaw + "' was not tracked";
          dropped.push(d0); return;
        }
        var key = found.key, s = found.s, label = s.label, ok = false, reason = "";
        if (change === "added") { ok = label === "added"; reason = "SAM label is '" + label + "', not 'added' for '" + key + "'"; }
        else if (change === "removed") { ok = label === "removed"; reason = "SAM label is '" + label + "', not 'removed' for '" + key + "'"; }
        else if (change === "moved") {
          var v = movedVerdicts[key] || movedVerdicts[conceptRaw] || {};
          var vConf = Number(v.confidence || 0) || 0;
          if (label !== "present_both") reason = "SAM label is '" + label + "', not 'present_both' for '" + key + "' - not moved";
          else if (!v.moved) reason = "moved-judge said not moved for '" + key + "' (confidence " + vConf.toFixed(2) + ")" + (v.reason ? ": " + v.reason : "");
          else if (vConf < MOVED_MIN_CONF) reason = "moved-judge confidence " + vConf.toFixed(2) + " < " + MOVED_MIN_CONF.toFixed(2);
          else ok = true;
        } else reason = "unsupported change type '" + change + "'";
        if (ok && coverageBad && (change === "added" || change === "removed") && isAnchor(key)) {
          ok = false; reason = coverageDropReason(change, coverage);
        }
        if (ok) {
          kept.push({ concept: key, change: change, explanation: claim.explanation || "", safety_note: claim.safety_note != null ? claim.safety_note : null, source: "spark", risk: rr.risk, risk_reason: rr.risk_reason, evidence: evidence(key, s) });
          keptConcepts[key] = true;
        } else {
          var d = {}; for (var k in claim) d[k] = claim[k];
          d.concept = key; d.risk = rr.risk; d.risk_reason = rr.risk_reason; d.reason = reason;
          dropped.push(d);
        }
      });
      Object.keys(summaries).forEach(function (concept) {
        var s = summaries[concept];
        if ((s.label === "added" || s.label === "removed") && !keptConcepts[concept]) {
          var rr = samOnlyRisk(concept, s.label);
          if (coverageBad && isAnchor(concept)) {
            dropped.push({ concept: concept, change: s.label, explanation: "SAM 3.1 detected '" + concept + "' as " + s.label + ".", safety_note: null, source: "sam", risk: rr.risk, risk_reason: rr.risk_reason, evidence: evidence(concept, s), reason: coverageDropReason(s.label, coverage) });
            return;
          }
          var frames = s.label === "added" ? s.after.frames_detected : s.before.frames_detected;
          kept.push({ concept: concept, change: s.label, explanation: "SAM 3.1 detected '" + concept + "' as " + s.label + " (present in " + frames + " frames).", safety_note: null, source: "sam", risk: rr.risk, risk_reason: rr.risk_reason, evidence: evidence(concept, s) });
          keptConcepts[concept] = true;
        }
      });
      return { kept: kept, dropped: dropped };
    }

    /* ================= pipeline ================= */
    var beforeFrames = [], afterFrames = [];
    var summaries = {}, movedVerdicts = {}, rawResult = { summary: "", claims: [] };
    var coverage = { score: 1.0, ok: true, anchor_overlap: 1.0, spark_score: 1.0, shared_anchors: [], only_before: [], only_after: [], missing_in_after: [], missing_in_before: [], retake_tip: "" };
    var privacy = { people_blurred: 0, documents_blurred: 0, frames_checked: 0, note: "People and paper documents were blurred before any frame was stored, shown or sent to the reasoning model." };
    var concepts = [];

    emit("keyframes", "start", { message: "Extracting keyframes" });
    return Promise.all([
      extractKeyframes(beforeFile, "BEFORE"),
      extractKeyframes(afterFile, "AFTER")
    ]).then(function (pair) {
      beforeFrames = pair[0]; afterFrames = pair[1];
      emit("keyframes", "done", {
        before: beforeFrames.map(function (f) { return f.dataUrl; }),
        after: afterFrames.map(function (f) { return f.dataUrl; }),
        before_count: beforeFrames.length, after_count: afterFrames.length
      });
      /* 2. privacy: blur people + paper documents BEFORE Spark sees frames */
      emit("privacy", "start", { message: "Blurring people and papers", model: SAM_MODEL });
      var all = beforeFrames.concat(afterFrames);
      var jobs = [];
      all.forEach(function (f, fi) { jobs.push({ f: f, fi: fi, concept: "person" }); jobs.push({ f: f, fi: fi, concept: "paper document" }); });
      return mapLimit(jobs, CONCURRENCY, function (job) {
        privacyChecks++;
        return samImage(job.f.dataUrl, job.concept).then(function (dets) {
          var blurred = 0;
          dets.forEach(function (d) { if (Number(d.c || 0) >= PRIVACY_CONF) { blurBox(job.f.canvas, d.box); blurred++; } });
          return { concept: job.concept, blurred: blurred };
        }).catch(function () { return { concept: job.concept, blurred: 0 }; });
      }).then(function (results) {
        results.forEach(function (r) {
          if (r.concept === "person") privacy.people_blurred += r.blurred; else privacy.documents_blurred += r.blurred;
        });
        privacy.frames_checked = all.length;
        all.forEach(function (f) { f.dataUrl = canvasToUrl(f.canvas); });
        emit("privacy", "done", {
          people_blurred: privacy.people_blurred, documents_blurred: privacy.documents_blurred,
          frames_checked: privacy.frames_checked, model: SAM_MODEL
        });
      });
    }).then(function () {
      /* 3. inventory (Spark), watchlist prepended, cap 12 */
      emit("inventory", "start", { message: "Inventorying objects", model: SPARK_MODEL });
      return sparkJson(inventoryContent(beforeFrames, afterFrames), 4000, "list_objects").then(function (data) {
        var objs = (data && data.objects) || [];
        var inv = [];
        (Array.isArray(objs) ? objs : []).slice(0, 10).forEach(function (o) {
          if (o && o.concept) inv.push({ concept: norm(o.concept), where_before: String(o.where_before || ""), where_after: String(o.where_after || ""), suspected_change: String(o.suspected_change || "unchanged") });
        });
        var seen = {};
        concepts = [];
        watchlist.forEach(function (c) { if (!seen[c]) { seen[c] = true; concepts.push(c); } });
        inv.forEach(function (o) { if (o.concept && !seen[o.concept]) { seen[o.concept] = true; concepts.push(o.concept); } });
        concepts = concepts.slice(0, 12);
        emit("inventory", "done", { concepts: concepts.slice(), objects: inv, count: concepts.length, model: SPARK_MODEL });
      }).catch(function () {
        concepts = watchlist.slice(0, 12);
        emit("inventory", "done", { concepts: concepts.slice(), objects: [], count: concepts.length, model: SPARK_MODEL, warning: "inventory failed; using watchlist only" });
      });
    }).then(function () {
      /* 4. coverage (Spark, 3+3) */
      emit("coverage", "start", { message: "Checking both walkthroughs cover the same room", model: SPARK_MODEL });
      coverageCalls++;
      return sparkJson(coverageContent(beforeFrames, afterFrames), 1500, "check_coverage").then(function (d) {
        var score = Math.max(0, Math.min(1, Number(d.score != null ? d.score : 1) || 0));
        coverage.spark_score = score; coverage.score = score;
        coverage.missing_in_after = Array.isArray(d.missing_in_after) ? d.missing_in_after.map(String) : [];
        coverage.missing_in_before = Array.isArray(d.missing_in_before) ? d.missing_in_before.map(String) : [];
        coverage.retake_tip = String(d.retake_tip || "");
        coverage.ok = score >= 0.6;
        emit("coverage", "done", { score: coverage.score, ok: coverage.ok, retake_tip: coverage.retake_tip, spark_score: coverage.spark_score, missing_in_after: coverage.missing_in_after, missing_in_before: coverage.missing_in_before, model: SPARK_MODEL });
      }).catch(function () {
        coverage.score = 1.0; coverage.spark_score = 1.0; coverage.ok = true;
        emit("coverage", "done", { score: 1, ok: true, retake_tip: "", spark_score: 1, model: SPARK_MODEL, warning: "coverage call failed; assuming covered" });
      });
    }).then(function () {
      /* 5. track: keyframe presence per concept x side */
      emit("track", "start", { message: "Tracking objects with SAM", model: SAM_MODEL, concepts: concepts.slice() });
      var jobs = [];
      concepts.forEach(function (c) { jobs.push({ concept: c, side: "before" }); jobs.push({ concept: c, side: "after" }); });
      var trackResults = {};
      return mapLimit(jobs, CONCURRENCY, function (job) {
        var frames = job.side === "before" ? beforeFrames : afterFrames;
        return trackConcept(frames, job.concept).then(function (sum) {
          if (!trackResults[job.concept]) trackResults[job.concept] = {};
          trackResults[job.concept][job.side] = sum;
          emit("track", "progress", { concept: job.concept, side: job.side, frames_detected: sum.frames_detected, best_conf: sum.best_conf, model: SAM_MODEL });
          return sum;
        });
      }).then(function () {
        concepts.forEach(function (c) {
          var b = trackResults[c].before, a = trackResults[c].after;
          var label = labelOf(b, a);
          summaries[c] = { concept: c, before: b, after: a, label: label, original_label: label, recheck: null, count_changed: b.max_instances !== a.max_instances };
        });
        /* deterministic anchor overlap caps the Spark coverage score */
        var either = [], both = [], onlyB = [], onlyA = [];
        Object.keys(summaries).forEach(function (c) {
          if (!isAnchor(c)) return;
          var s = summaries[c];
          if (s.before.present || s.after.present) {
            either.push(c);
            if (s.before.present && s.after.present) both.push(c);
            else if (s.before.present) onlyB.push(c); else onlyA.push(c);
          }
        });
        coverage.shared_anchors = both; coverage.only_before = onlyB; coverage.only_after = onlyA;
        coverage.anchor_overlap = either.length ? both.length / either.length : 1.0;
        coverage.score = Math.min(coverage.spark_score, coverage.anchor_overlap);
        coverage.ok = coverage.score >= 0.6;
        emit("coverage", "done", { score: coverage.score, ok: coverage.ok, retake_tip: coverage.retake_tip, spark_score: coverage.spark_score, anchor_overlap: coverage.anchor_overlap, shared_anchors: both, only_before: onlyB, only_after: onlyA });
        emit("track", "done", { summaries: summaries, count: concepts.length, model: SAM_MODEL });
      });
    }).then(function () {
      /* 6. labels + vocabulary repair for not_found watchlist items */
      var labels = {};
      Object.keys(summaries).forEach(function (c) { labels[c] = summaries[c].label; });
      emit("labels", "done", { labels: labels });
      var toRepair = watchlist.filter(function (c) { return summaries[c] && summaries[c].label === "not_found"; });
      if (!toRepair.length) { emit("repair", "done", { repaired: [], count: 0 }); return null; }
      emit("repair", "start", { concepts: toRepair.slice(), model: SPARK_MODEL });
      return mapLimit(toRepair, CONCURRENCY, function (concept) {
        return sparkJson(aliasesContent(concept, beforeFrames, afterFrames), 1000, "suggest_aliases").then(function (data) {
          var raw = (data && data.aliases) || [];
          var aliases = [], seen = {};
          (Array.isArray(raw) ? raw : [raw]).forEach(function (item) {
            var a = norm(typeof item === "object" && item ? (item.alias || item.concept || item.name || "") : item);
            if (a && a !== concept && !seen[a] && aliases.length < 3) { seen[a] = true; aliases.push(a); }
          });
          var found = null;
          var chain = Promise.resolve();
          aliases.forEach(function (alias) {
            chain = chain.then(function () {
              if (found) return null;
              var b3 = beforeFrames.slice(0, 3), a3 = afterFrames.slice(0, 3);
              return Promise.all([trackConcept(b3, alias), trackConcept(a3, alias)]).then(function (pair) {
                var lbl = labelOf(pair[0], pair[1]);
                if (lbl !== "not_found") found = { alias: alias, before: pair[0], after: pair[1], label: lbl };
              });
            });
          });
          return chain.then(function () {
            if (found) {
              var s = summaries[concept];
              s.before = found.before; s.after = found.after; s.label = found.label;
              s.recheck = { checked: true, found: true, alias: found.alias, label: found.label };
              s.count_changed = found.before.max_instances !== found.after.max_instances;
            }
            emit("repair", "progress", { concept: concept, aliases: aliases, found: !!found, alias: found ? found.alias : null, label: summaries[concept].label });
            return { concept: concept, aliases: aliases, found: !!found };
          });
        }).catch(function () {
          emit("repair", "progress", { concept: concept, aliases: [], found: false, label: summaries[concept].label });
          return { concept: concept, aliases: [], found: false };
        });
      }).then(function (repaired) {
        emit("repair", "done", { repaired: repaired, count: repaired.filter(function (r) { return r.found; }).length });
      });
    }).then(function () {
      /* 7. judge moved for present_both (max 6, watchlist first) */
      var both = Object.keys(summaries).filter(function (c) { return summaries[c].label === "present_both"; });
      both.sort(function (a, b) {
        var wa = isWatchlist(a, watchlist) ? 0 : 1, wb = isWatchlist(b, watchlist) ? 0 : 1;
        return wa - wb;
      });
      both = both.slice(0, 6);
      emit("judge", "start", { concepts: both.slice(), model: SPARK_MODEL });
      return mapLimit(both, CONCURRENCY, function (concept) {
        var s = summaries[concept];
        var bf = beforeFrames[s.before.best_frame || 0], af = afterFrames[s.after.best_frame || 0];
        return sparkJson(judgeContent(concept, bf, af, s.before.best_box, s.after.best_box), 1000, "judge_moved").then(function (d) {
          var verdict = { moved: !!d.moved, confidence: Math.max(0, Math.min(1, Number(d.confidence || 0) || 0)), reason: String(d.reason || "") };
          movedVerdicts[concept] = verdict;
          emit("judge", "progress", { concept: concept, moved: verdict.moved, confidence: verdict.confidence, reason: verdict.reason, model: SPARK_MODEL });
          return verdict;
        }).catch(function () {
          var verdict = { moved: false, confidence: 0, reason: "unparseable Spark response" };
          movedVerdicts[concept] = verdict;
          emit("judge", "progress", { concept: concept, moved: false, confidence: 0, reason: verdict.reason, model: SPARK_MODEL });
          return verdict;
        });
      }).then(function () { emit("judge", "done", { verdicts: movedVerdicts, count: both.length, model: SPARK_MODEL }); });
    }).then(function () {
      /* 8. report: Spark writes claims from the SAM diff table */
      emit("report", "start", { message: "Writing grounded report", model: SPARK_MODEL });
      return sparkJson(claimsContent(summaries, movedVerdicts), 4000, "write_claims").then(function (d) {
        var claims = [];
        (Array.isArray(d.claims) ? d.claims : []).forEach(function (c) {
          if (c && c.concept && ["added", "removed", "moved"].indexOf(c.change) !== -1) {
            claims.push({ concept: norm(c.concept), change: c.change, explanation: String(c.explanation || ""), safety_note: c.safety_note != null ? c.safety_note : null, risk: cleanRisk(c.risk) || "medium", risk_reason: String(c.risk_reason || "") });
          }
        });
        rawResult = { summary: String(d.summary || ""), claims: claims };
        emit("report", "done", { summary: rawResult.summary, claims: claims, count: claims.length, model: SPARK_MODEL });
      }).catch(function () {
        rawResult = { summary: "", claims: [] };
        emit("report", "done", { summary: "", claims: [], count: 0, model: SPARK_MODEL, warning: "report call failed; SAM-only claims will be used" });
      });
    }).then(function () {
      /* 9. grounding filter + annotated evidence + final result */
      emit("filter", "start", { message: "Grounding claims against SAM evidence" });
      var filtered = groundingFilter(rawResult.claims, summaries, movedVerdicts, coverage);
      function claimImages(claim) {
        var s = summaries[claim.concept];
        if (!s) return { before: null, after: null };
        var color = CHANGE_COLORS[claim.change] || "#ef8b0c";
        var bImg = null, aImg = null;
        if (s.before.best_box && s.before.best_frame != null) bImg = canvasToUrl(drawBox(beforeFrames[s.before.best_frame].canvas, s.before.best_box, claim.concept, color));
        else if (claim.change === "removed" && s.before.best_frame != null) bImg = beforeFrames[s.before.best_frame].dataUrl;
        if (s.after.best_box && s.after.best_frame != null) aImg = canvasToUrl(drawBox(afterFrames[s.after.best_frame].canvas, s.after.best_box, claim.concept, color));
        else if (claim.change === "added" && s.after.best_frame != null) aImg = afterFrames[s.after.best_frame].dataUrl;
        return { before: bImg, after: aImg };
      }
      filtered.kept.forEach(function (c) { c.images = claimImages(c); });
      filtered.dropped.forEach(function (c) { if (summaries[c.concept]) c.images = claimImages(c); });

      var watchlistStatus = watchlist.map(function (c) {
        var s = summaries[c];
        var status = "not_seen";
        if (s) {
          if (s.label === "removed") status = "missing";
          else if (s.label === "added") status = "added";
          else if (s.label === "present_both") {
            var v = movedVerdicts[c] || {};
            status = (v.moved && Number(v.confidence || 0) >= MOVED_MIN_CONF) ? "moved" : "seen";
          } else status = "not_seen";
        }
        return { concept: c, status: status, label: s ? s.label : "not_found", evidence: s ? evidence(c, s) : null };
      });

      var stats = {
        spark_calls: sparkCalls, sam_calls: samCalls, sam_image_calls: samCalls,
        privacy_checks: privacyChecks, coverage_calls: coverageCalls, floor_checks: 0,
        concepts_tracked: concepts.length, keyframes_before: beforeFrames.length, keyframes_after: afterFrames.length,
        kept: filtered.kept.length, dropped: filtered.dropped.length,
        spark_input_tokens: sparkInputTokens, spark_output_tokens: sparkOutputTokens
      };
      var result = {
        run_id: id, room: room, filmed_by: filmedBy,
        summary: rawResult.summary,
        kept_claims: filtered.kept, dropped_claims: filtered.dropped, raw_claims: rawResult.claims,
        claims: filtered.kept,
        watchlist: watchlist, watchlist_status: watchlistStatus,
        summaries: summaries, diff: summaries, moved_verdicts: movedVerdicts,
        coverage: coverage, privacy: privacy, floor_check: { items: [], dropped: [] },
        keyframes: { before: beforeFrames.map(function (f) { return f.dataUrl; }), after: afterFrames.map(function (f) { return f.dataUrl; }) },
        stats: stats, models: MODELS.slice(),
        cost_usd: Math.round(costUsd * 10000) / 10000, elapsed_s: elapsed()
      };
      emit("filter", "done", { kept: filtered.kept.length, dropped: filtered.dropped.length, kept_claims: filtered.kept, dropped_claims: filtered.dropped });
      emit("done", "done", { run_id: id, kept: filtered.kept.length, dropped: filtered.dropped.length });
      emit("result", "done", { result: result });
      return result;
    }).catch(function (err) {
      var e = err || new Error("Browser pipeline failed.");
      emit("error", "error", { error: String(e.message || e) });
      throw e;
    });
  }

  window.SLBrowserPipeline = { run: run };
})();
