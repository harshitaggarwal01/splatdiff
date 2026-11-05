(function () {
  "use strict";

  var SAMPLE_SRC = "/data/sample_after.mp4";
  var ROOM = "Bedroom";
  var FRAME_INTERVAL_MS = 1200;
  var FALL_SECONDS = 20;
  var ASK_HOLD_MS = 8000;

  var video = document.getElementById("lensVideo");
  var canvas = document.getElementById("hud");
  var lens = document.getElementById("lens");
  var badge = document.getElementById("modelBadge");
  var whisperEl = document.getElementById("whisper");
  var playBtn = document.getElementById("playBtn");
  var statusEl = document.getElementById("glassesStatus");
  var sourceSample = document.getElementById("sourceSample");
  var sourceCamera = document.getElementById("sourceCamera");
  var chipsEl = document.getElementById("watchlistChips");
  var watchInput = document.getElementById("watchlistInput");
  var watchAddBtn = document.getElementById("watchlistAddBtn");
  var memoryList = document.getElementById("memoryList");
  var askInput = document.getElementById("askInput");
  var askBtn = document.getElementById("askBtn");
  var fallBtn = document.getElementById("fallBtn");
  var fallOverlay = document.getElementById("fallOverlay");
  var fallPrompt = document.getElementById("fallPrompt");
  var fallOutcome = document.getElementById("fallOutcome");
  var fallOutcomeText = document.getElementById("fallOutcomeText");
  var fallFeedWrap = document.getElementById("fallFeedWrap");
  var fallFineBtn = document.getElementById("fallFineBtn");
  var fallBackBtn = document.getElementById("fallBackBtn");
  var fallCountdown = document.getElementById("fallCountdown");

  if (!video || !canvas) return;

  var ctx = canvas.getContext("2d");
  var offscreen = document.createElement("canvas");
  var reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var watchlist = ["walker", "floor lamp", "backpack"];
  var inFlight = false;
  var detections = [];
  var postedSize = { w: 0, h: 0 };
  var cameraStream = null;
  var currentSource = "sample";
  var fallActive = false;
  var fallTimer = null;
  var fallRemaining = FALL_SECONDS;
  var whisperTimer = null;
  var whisperHoldUntil = 0;

  // Last-seen memory: kept ONLY in this browser tab's memory (a plain
  // in-memory object). No server calls, no web storage, no thumbnails;
  // it is forgotten when this tab/session is closed.
  // Shape per item: {concept, alias, direction, distance, seenAt, thumbnail}
  var memoryLog = {};

  var ALIASES = {
    "walker": "walker",
    "floor lamp": "lamp",
    "backpack": "bag rucksack",
    "keys": "key keyring house keys",
    "glasses case": "glasses spectacles specs case",
    "walking stick": "stick cane"
  };

  function setStatus(text, isError) {
    statusEl.textContent = text || "";
    statusEl.classList.toggle("is-error", !!isError);
  }

  function capitalise(text) {
    text = String(text || "").trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
  }

  /* ---------- Last-seen memory ---------- */

  function aliasFor(concept) {
    return ALIASES[concept] || concept;
  }

  function ensureMemoryEntries() {
    watchlist.forEach(function (item) {
      if (!memoryLog[item]) {
        memoryLog[item] = {
          concept: item,
          alias: aliasFor(item),
          direction: "",
          distance: "",
          seenAt: null,
          thumbnail: null
        };
      }
    });
    Object.keys(memoryLog).forEach(function (key) {
      if (watchlist.indexOf(key) === -1) delete memoryLog[key];
    });
  }

  function formatAgo(seenAt, now) {
    if (!seenAt) return "";
    var seconds = Math.max(0, Math.floor((now.getTime() - seenAt.getTime()) / 1000));
    if (seconds < 5) return "just now";
    if (seconds < 60) return seconds + " s ago";
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + (minutes === 1 ? " min ago" : " min ago");
    var hours = Math.floor(minutes / 60);
    return hours + (hours === 1 ? " h ago" : " h ago");
  }

  function renderMemory() {
    if (!memoryList) return;
    ensureMemoryEntries();
    var now = new Date();
    memoryList.innerHTML = "";
    if (!watchlist.length) {
      var empty = document.createElement("li");
      empty.className = "memory-row memory-row-empty";
      empty.textContent = "Nothing on the watchlist yet.";
      memoryList.appendChild(empty);
      return;
    }
    watchlist.forEach(function (item) {
      var entry = memoryLog[item];
      var li = document.createElement("li");
      li.className = "memory-row";
      if (!entry || !entry.seenAt) {
        li.textContent = capitalise(item) + " \u2014 not seen yet";
      } else {
        var parts = capitalise(item) + " \u2014 seen " + formatAgo(entry.seenAt, now);
        if (entry.direction) parts += ", " + entry.direction;
        if (entry.distance) parts += ", " + entry.distance;
        li.textContent = parts;
      }
      memoryList.appendChild(li);
    });
  }

  function directionFor(box) {
    if (!postedSize.w || !box) return "ahead";
    var centreX = ((box[0] + box[2]) / 2) / postedSize.w;
    if (centreX < 0.4) return "on your left";
    if (centreX > 0.6) return "on your right";
    return "straight ahead";
  }

  function distanceFor(box) {
    if (!postedSize.w || !postedSize.h || !box) return "close";
    var area = Math.max(0, box[2] - box[0]) * Math.max(0, box[3] - box[1]);
    var frameArea = postedSize.w * postedSize.h;
    var ratio = frameArea ? area / frameArea : 0;
    if (ratio >= 0.2) return "close";
    if (ratio >= 0.06) return "a few steps away";
    return "far away";
  }

  function updateMemory(list) {
    ensureMemoryEntries();
    var best = {};
    list.forEach(function (det) {
      var key = String(det.concept || "").trim().toLowerCase();
      if (!key || watchlist.indexOf(key) === -1) return;
      if (!best[key] || (typeof det.c === "number" && (typeof best[key].c !== "number" || det.c > best[key].c))) {
        best[key] = det;
      }
    });
    Object.keys(best).forEach(function (key) {
      var det = best[key];
      var entry = memoryLog[key];
      if (!entry) return;
      entry.direction = directionFor(det.box);
      entry.distance = distanceFor(det.box);
      entry.seenAt = new Date();
      entry.thumbnail = null;
    });
    if (Object.keys(best).length) renderMemory();
  }

  // Relative times in the panel stay honest without any new model calls.
  setInterval(renderMemory, 1000);

  /* ---------- "Ask: where is my..." ---------- */

  var STOP_WORDS = {
    my: true, where: true, is: true, the: true, a: true, an: true,
    did: true, i: true, leave: true, left: true, it: true,
    find: true, please: true, do: true, you: true, see: true, seen: true
  };

  function tokensFor(text) {
    return String(text || "").toLowerCase().split(/[^a-z0-9]+/).filter(function (token) {
      return token && !STOP_WORDS[token];
    });
  }

  function findMemoryEntry(query) {
    ensureMemoryEntries();
    var queryTokens = tokensFor(query);
    if (!queryTokens.length) return null;
    var bestEntry = null;
    var bestScore = 0;
    watchlist.forEach(function (item) {
      var entry = memoryLog[item];
      if (!entry) return;
      var entryTokens = tokensFor(entry.concept).concat(tokensFor(entry.alias));
      var score = 0;
      queryTokens.forEach(function (token) {
        if (entryTokens.indexOf(token) !== -1) score += 1;
      });
      if (score > bestScore) {
        bestScore = score;
        bestEntry = entry;
      }
    });
    return bestScore > 0 ? bestEntry : null;
  }

  function answerAsk() {
    if (!askInput) return;
    var raw = askInput.value.trim();
    if (!raw) {
      askInput.focus();
      return;
    }
    var entry = findMemoryEntry(raw);
    var answer;
    if (entry && entry.seenAt) {
      answer = "Your " + entry.concept + " \u2014 last seen " + formatAgo(entry.seenAt, new Date());
      if (entry.direction) answer += ", " + entry.direction;
      if (entry.distance) answer += ", " + entry.distance;
      answer += ".";
    } else {
      var termTokens = tokensFor(raw);
      var term = entry ? entry.concept : (termTokens.length ? termTokens.join(" ") : raw.toLowerCase());
      answer = "I haven\u2019t seen your " + term + " yet \u2014 look around slowly.";
    }
    whisperHoldUntil = Date.now() + ASK_HOLD_MS;
    showWhisper(answer);
  }

  if (askBtn) askBtn.addEventListener("click", answerAsk);
  if (askInput) {
    askInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        answerAsk();
      }
    });
  }

  /* ---------- Watchlist chips ---------- */

  function renderSuggested() {
    var suggested = document.querySelectorAll("[data-suggested]");
    Array.prototype.forEach.call(suggested, function (button) {
      var value = button.getAttribute("data-suggested");
      var already = watchlist.indexOf(value) !== -1;
      button.disabled = already;
      button.setAttribute("aria-disabled", already ? "true" : "false");
      button.textContent = already ? value + " \u2014 added" : value;
    });
  }

  function renderChips() {
    chipsEl.innerHTML = "";
    watchlist.forEach(function (item, index) {
      var li = document.createElement("li");
      li.className = "watchlist-chip";
      var label = document.createElement("span");
      label.textContent = item;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "watchlist-remove";
      remove.textContent = "\u00d7";
      remove.setAttribute("aria-label", "Remove " + item + " from watchlist");
      remove.addEventListener("click", function () {
        watchlist.splice(index, 1);
        ensureMemoryEntries();
        renderChips();
        renderMemory();
        detections = [];
        drawHud();
      });
      li.appendChild(label);
      li.appendChild(remove);
      chipsEl.appendChild(li);
    });
    renderSuggested();
  }

  function addWatchValue(value) {
    value = String(value || "").trim().toLowerCase();
    if (!value) return;
    if (watchlist.indexOf(value) === -1) watchlist.push(value);
    ensureMemoryEntries();
    renderChips();
    renderMemory();
  }

  function addWatchItem() {
    var value = watchInput.value.trim().toLowerCase();
    if (!value) return;
    addWatchValue(value);
    watchInput.value = "";
    watchInput.focus();
  }

  watchAddBtn.addEventListener("click", addWatchItem);
  watchInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      addWatchItem();
    }
  });

  var suggestedButtons = document.querySelectorAll("[data-suggested]");
  Array.prototype.forEach.call(suggestedButtons, function (button) {
    button.addEventListener("click", function () {
      addWatchValue(button.getAttribute("data-suggested"));
    });
  });

  ensureMemoryEntries();
  renderChips();
  renderMemory();

  /* ---------- HUD drawing ---------- */

  function roundRectPath(c, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    c.beginPath();
    c.moveTo(x + r, y);
    c.lineTo(x + w - r, y);
    c.arcTo(x + w, y, x + w, y + r, r);
    c.lineTo(x + w, y + h - r);
    c.arcTo(x + w, y + h, x + w - r, y + h, r);
    c.lineTo(x + r, y + h);
    c.arcTo(x, y + h, x, y + h - r, r);
    c.lineTo(x, y + r);
    c.arcTo(x, y, x + r, y, r);
    c.closePath();
  }

  function sizeCanvas() {
    var rect = canvas.getBoundingClientRect();
    var dpr = window.devicePixelRatio || 1;
    var w = Math.max(1, Math.round(rect.width * dpr));
    var h = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    return { w: canvas.width, h: canvas.height, dpr: dpr };
  }

  // Boxes arrive in the posted frame's pixel space; the video is shown with
  // object-fit: cover, so map via the cover transform, not a plain stretch.
  function coverTransform(displayW, displayH) {
    var vw = postedSize.w || video.videoWidth || displayW;
    var vh = postedSize.h || video.videoHeight || displayH;
    var scale = Math.max(displayW / vw, displayH / vh);
    return {
      scale: scale,
      offsetX: (displayW - vw * scale) / 2,
      offsetY: (displayH - vh * scale) / 2
    };
  }

  function drawHud() {
    var size = sizeCanvas();
    ctx.clearRect(0, 0, size.w, size.h);
    if (!detections.length || !postedSize.w) return;
    var t = coverTransform(size.w, size.h);

    detections.forEach(function (det) {
      if (!det.box || det.box.length < 4) return;
      var x = det.box[0] * t.scale + t.offsetX;
      var y = det.box[1] * t.scale + t.offsetY;
      var w = (det.box[2] - det.box[0]) * t.scale;
      var h = (det.box[3] - det.box[1]) * t.scale;
      if (w <= 2 || h <= 2) return;

      ctx.save();
      ctx.strokeStyle = "#4E6A3B";
      ctx.lineWidth = Math.max(1.5, 2 * size.dpr);
      roundRectPath(ctx, x, y, w, h, 8 * size.dpr);
      ctx.stroke();

      var label = capitalise(det.concept);
      if (typeof det.c === "number" && isFinite(det.c)) {
        label += " " + Math.round(det.c * 100) + "%";
      }
      ctx.font = "600 " + Math.round(12 * size.dpr) + "px \"Public Sans\", sans-serif";
      var padX = 8 * size.dpr;
      var padY = 4 * size.dpr;
      var textW = ctx.measureText(label).width;
      var pillW = textW + padX * 2;
      var pillH = 12 * size.dpr + padY * 2;
      var pillX = Math.max(0, Math.min(x, size.w - pillW));
      var pillY = y - pillH - 4 * size.dpr;
      if (pillY < 0) pillY = y + 4 * size.dpr;
      ctx.fillStyle = "rgba(30, 26, 22, 0.82)";
      roundRectPath(ctx, pillX, pillY, pillW, pillH, pillH / 2);
      ctx.fill();
      ctx.fillStyle = "#F4EFE6";
      ctx.textBaseline = "middle";
      ctx.fillText(label, pillX + padX, pillY + pillH / 2 + 1);
      ctx.restore();
    });
  }

  function showWhisper(text) {
    if (whisperTimer) { clearTimeout(whisperTimer); whisperTimer = null; }
    if (!text) {
      whisperEl.classList.remove("is-visible");
      if (reducedMotion) whisperEl.textContent = "";
      else whisperTimer = setTimeout(function () { whisperEl.textContent = ""; }, 480);
      return;
    }
    if (whisperEl.textContent !== text) whisperEl.textContent = text;
    // Force a reflow so a changed line still fades in cleanly.
    void whisperEl.offsetWidth;
    whisperEl.classList.add("is-visible");
  }

  function whisperFor(list, serverWhisper) {
    if (serverWhisper) return String(serverWhisper);
    if (!list.length) return "";
    var first = list[0];
    var name = capitalise(first.concept || "Object");
    return name + " \u2014 ahead, a few steps away.";
  }

  window.addEventListener("resize", drawHud);
  if ("ResizeObserver" in window) new ResizeObserver(drawHud).observe(lens);
  video.addEventListener("loadedmetadata", drawHud);

  /* ---------- Frame loop ---------- */

  function normaliseDetections(data) {
    var raw = [];
    if (Array.isArray(data)) raw = data;
    else if (data && Array.isArray(data.detections)) raw = data.detections;
    else if (data && Array.isArray(data.objects)) raw = data.objects;
    else if (data && Array.isArray(data.results)) raw = data.results;
    return raw.map(function (item) {
      if (!item || typeof item !== "object") return null;
      var box = item.box || item.bbox || item.bounds || null;
      if (box && !Array.isArray(box)) {
        box = [box.x1, box.y1, box.x2, box.y2];
      }
      if (!box || box.length < 4) return null;
      var conf = item.c;
      if (typeof conf !== "number") conf = item.confidence;
      if (typeof conf !== "number") conf = item.score;
      return {
        concept: item.concept || item.label || item.name || item.object || "object",
        box: [Number(box[0]), Number(box[1]), Number(box[2]), Number(box[3])],
        c: typeof conf === "number" ? conf : null
      };
    }).filter(function (d) {
      return d && d.box.every(function (n) { return isFinite(n); });
    }).slice(0, 16);
  }

  function sendFrame() {
    if (inFlight || fallActive) return;
    if (video.paused || video.ended || video.readyState < 2) return;
    if (!video.videoWidth || !video.videoHeight) return;
    if (!watchlist.length) { detections = []; drawHud(); showWhisper(""); return; }

    var scale = Math.min(1, 640 / video.videoWidth);
    var w = Math.max(1, Math.round(video.videoWidth * scale));
    var h = Math.max(1, Math.round(video.videoHeight * scale));
    offscreen.width = w;
    offscreen.height = h;
    var octx = offscreen.getContext("2d");
    if (!octx) return;
    try { octx.drawImage(video, 0, 0, w, h); } catch (err) { return; }

    if (!offscreen.toBlob) return;
    inFlight = true;
    var started = performance.now();
    offscreen.toBlob(function (blob) {
      if (!blob) { inFlight = false; return; }
      postedSize = { w: w, h: h };
      var form = new FormData();
      form.append("image", blob, "frame.jpg");
      form.append("watchlist", JSON.stringify(watchlist));
      form.append("room", ROOM);
      fetch("/api/glasses/frame", { method: "POST", body: form })
        .then(function (resp) {
          if (!resp.ok) throw new Error("frame check failed (" + resp.status + ")");
          return resp.json();
        })
        .then(function (data) {
          var elapsed = (performance.now() - started) / 1000;
          var serverLatency = data && (data.latency_s || data.latency);
          var shown = typeof serverLatency === "number" ? serverLatency : elapsed;
          badge.textContent = "sam-3.1 \u00b7 " + shown.toFixed(1) + " s";
          detections = normaliseDetections(data);
          updateMemory(detections);
          drawHud();
          if (Date.now() >= whisperHoldUntil) {
            showWhisper(whisperFor(detections, data && (data.whisper || data.message)));
          }
          setStatus("");
        })
        .catch(function () {
          setStatus("Couldn\u2019t reach sam-3.1 just now \u2014 will try again.", true);
        })
        .finally(function () { inFlight = false; });
    }, "image/jpeg", 0.8);
  }

  setInterval(sendFrame, FRAME_INTERVAL_MS);

  /* ---------- Play / pause ---------- */

  function syncPlayButton() {
    var playing = !video.paused && !video.ended;
    playBtn.textContent = playing ? "Pause" : "Start";
    playBtn.setAttribute("aria-pressed", playing ? "true" : "false");
  }
  video.addEventListener("play", syncPlayButton);
  video.addEventListener("pause", syncPlayButton);
  playBtn.addEventListener("click", function () {
    if (video.paused || video.ended) {
      var p = video.play();
      if (p && p.catch) p.catch(function () { setStatus("The video could not start. Try again.", true); });
    } else {
      video.pause();
    }
  });
  syncPlayButton();

  /* ---------- Source switching ---------- */

  function stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach(function (track) { track.stop(); });
      cameraStream = null;
    }
    if (video.srcObject) video.srcObject = null;
  }

  function useSample(resume) {
    stopCamera();
    currentSource = "sample";
    if (video.getAttribute("src") !== SAMPLE_SRC) {
      video.setAttribute("src", SAMPLE_SRC);
      video.load();
    }
    detections = [];
    drawHud();
    showWhisper("");
    if (resume) { var p = video.play(); if (p && p.catch) p.catch(function () {}); }
  }

  function useCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus("This browser can\u2019t use a camera here. The sample walkthrough is still selected.", true);
      sourceSample.checked = true;
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then(function (stream) {
        // The user may have switched back while the prompt was open.
        if (!sourceCamera.checked) {
          stream.getTracks().forEach(function (track) { track.stop(); });
          return;
        }
        stopCamera();
        cameraStream = stream;
        currentSource = "camera";
        video.removeAttribute("src");
        video.load();
        video.srcObject = stream;
        detections = [];
        drawHud();
        showWhisper("");
        setStatus("");
        var p = video.play();
        if (p && p.catch) p.catch(function () {});
        syncPlayButton();
      })
      .catch(function () {
        sourceSample.checked = true;
        useSample(false);
        setStatus("Camera permission was not given, so the glasses are using the sample walkthrough instead. You can allow the camera in your browser settings and try again.", true);
      });
  }

  sourceSample.addEventListener("change", function () { if (sourceSample.checked) useSample(false); });
  sourceCamera.addEventListener("change", function () { if (sourceCamera.checked) useCamera(); });

  /* ---------- Fall simulation ---------- */

  function postFall(responded) {
    return fetch("/api/glasses/fall", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room: ROOM, wearer: "Dad", notify: "Priya", responded: responded })
    }).catch(function () { /* The on-screen outcome still stands. */ });
  }

  function stopFallTimer() {
    if (fallTimer) { clearInterval(fallTimer); fallTimer = null; }
  }

  function updateCountdown() {
    fallCountdown.textContent = "If there\u2019s no answer, Priya will be told. " +
      fallRemaining + (fallRemaining === 1 ? " second" : " seconds") + " left.";
  }

  function showFallOutcome(text, showFeedLink) {
    fallPrompt.hidden = true;
    fallOutcome.hidden = false;
    fallOutcomeText.textContent = text;
    fallFeedWrap.hidden = !showFeedLink;
    fallBackBtn.focus();
  }

  function endFall() {
    stopFallTimer();
    fallActive = false;
    fallOverlay.hidden = true;
    lens.classList.remove("is-fall");
    fallBtn.disabled = false;
    fallBtn.focus();
  }

  fallBtn.addEventListener("click", function () {
    if (fallActive) return;
    fallActive = true;
    fallRemaining = FALL_SECONDS;
    fallPrompt.hidden = false;
    fallOutcome.hidden = true;
    fallOverlay.hidden = false;
    lens.classList.add("is-fall");
    fallBtn.disabled = true;
    showWhisper("");
    updateCountdown();
    fallFineBtn.focus();
    stopFallTimer();
    fallTimer = setInterval(function () {
      fallRemaining -= 1;
      if (fallRemaining <= 0) {
        stopFallTimer();
        postFall(false);
        showFallOutcome("Priya has been told.", true);
        return;
      }
      updateCountdown();
    }, 1000);
  });

  fallFineBtn.addEventListener("click", function () {
    stopFallTimer();
    postFall(true);
    showFallOutcome("Glad you\u2019re OK.", false);
  });

  fallBackBtn.addEventListener("click", endFall);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && fallActive && !fallOutcome.hidden) endFall();
  });
})();
