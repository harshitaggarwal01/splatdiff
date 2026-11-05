"use strict";

/* Second Look front-end (engine: SplatDiff). Vanilla JS, same-origin API per build_log/UI_CONTRACT.md. */

const $ = (id) => document.getElementById(id);

const DEFAULT_TITLE = "Second Look — Room check";

const els = {
  todayDate: $("todayDate"),
  historyBtn: $("historyBtn"),
  historyDrawer: $("historyDrawer"),
  historyClose: $("historyClose"),
  historyList: $("historyList"),
  dropBefore: $("dropBefore"),
  dropAfter: $("dropAfter"),
  fileBefore: $("fileBefore"),
  fileAfter: $("fileAfter"),
  videoBefore: $("videoBefore"),
  videoAfter: $("videoAfter"),
  dropBeforeEmpty: $("dropBeforeEmpty"),
  dropAfterEmpty: $("dropAfterEmpty"),
  fileNameBefore: $("fileNameBefore"),
  fileNameAfter: $("fileNameAfter"),
  sampleNote: $("sampleNote"),
  tagBox: $("tagBox"),
  tagList: $("tagList"),
  tagInput: $("tagInput"),
  voiceBtn: $("voiceBtn"),
  voiceBtnText: $("voiceBtnText"),
  voiceStopBtn: $("voiceStopBtn"),
  voiceTimer: $("voiceTimer"),
  voiceStatus: $("voiceStatus"),
  voiceQuote: $("voiceQuote"),
  voiceQuoteText: $("voiceQuoteText"),
  narrationCheck: $("narrationCheck"),
  runBtn: $("runBtn"),
  sampleBtn: $("sampleBtn"),
  actions: $("actions"),
  runError: $("runError"),
  liveSection: $("liveSection"),
  stageList: $("stageList"),
  ledgerLine: $("ledgerLine"),
  liveError: $("liveError"),
  liveErrorText: $("liveErrorText"),
  retryBtn: $("retryBtn"),
  reportSection: $("reportSection"),
  attentionBanner: $("attentionBanner"),
  printHeader: $("printHeader"),
  reportSummary: $("reportSummary"),
  reportStats: $("reportStats"),
  watchlistBlock: $("watchlistBlock"),
  watchlistRows: $("watchlistRows"),
  findingsBlock: $("findingsBlock"),
  findingsEmpty: $("findingsEmpty"),
  findingsList: $("findingsList"),
  struckBlock: $("struckBlock"),
  struckList: $("struckList"),
  footerLedger: $("footerLedger"),
  printBtn: $("printBtn"),
  copyBtn: $("copyBtn"),
  copyBtnText: $("copyBtnText"),
  shareBtn: $("shareBtn"),
  shareBtnText: $("shareBtnText"),
};

const state = {
  beforeFile: null,
  afterFile: null,
  sampleMode: false,
  sampleLabel: "",
  tags: [],
  running: false,
  runId: null,
  eventSource: null,
  currentResult: null,
  attentionItems: [],
  stageRows: new Map(),
  trackChips: new Map(),
  inventoryConcepts: [],
  trackMarks: new Map(),
  trackTotal: 0,
  trackDone: 0,
  modelsUsed: [],
  lastElapsed: 0,
  lastCost: 0,
  liveScrolled: false,
  recorder: null,
  recorderChunks: [],
  recorderTimer: null,
  recorderStartedAt: 0,
};

const ICON_X = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>';
const ICON_EYE = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
const ICON_CHECK = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>';

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isNum(v) { return typeof v === "number" && Number.isFinite(v); }
function fmtCost(v) { return "$" + (isNum(v) ? v : 0).toFixed(2); }
function fmtSeconds(v) { return (isNum(v) ? v : 0).toFixed(1) + " s"; }
function fmtConf(v) { return isNum(v) ? v.toFixed(2) : "—"; }
function fmtCount(v) { return isNum(v) ? String(v) : "—"; }
function capitalise(s) {
  const t = String(s == null ? "" : s).trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "";
}
function sentenceCase(s) {
  const t = String(s == null ? "" : s).trim().replace(/\s+/g, " ").toLowerCase();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "";
}
function reducedMotion() {
  return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* Remove SAM box/coordinate/confidence fragments from Spark prose, then tidy. */
function cleanExplanation(value) {
  let s = String(value == null ? "" : value);
  s = s.replace(/\bbox\s*\[[^\]]*\]/gi, "");
  s = s.replace(/\[\s*\d+(?:\s*,\s*\d+){2,}\s*\]/g, "");
  s = s.replace(/\(\s*(?:conf|confidence)\b[^)]*\)/gi, "");
  /* Leftover coordinate-removal fragments, e.g. "with best at,", "best at", "at conf 0.87". */
  s = s.replace(/\bwith\s+best\s+at\b[^,.;!?]*/gi, "");
  s = s.replace(/\bbest\s+at\b[^,.;!?]*/gi, "");
  s = s.replace(/\bat\s+conf(?:idence)?\b\s*[:=]?\s*\d+(?:\.\d+)?/gi, "");
  s = s.replace(/\bwith\s+at\b\s*,?/gi, "");
  s = s.replace(/\bconf(?:idence)?\s*[:=]?\s*\d+(?:\.\d+)?\b/gi, "");
  s = s.replace(/\b(?:with|at)\s*(?=[,.;!?]|$)/gi, "");
  s = s.replace(/\(\s*[,;:]?\s*\)/g, "");
  s = s.replace(/\s+([,.;:!?])/g, "$1");
  s = s.replace(/,(\s*,)+/g, ",");
  s = s.replace(/([.!?])\s*,/g, "$1");
  s = s.replace(/\s{2,}/g, " ");
  s = s.replace(/^[\s,;]+/, "");
  s = s.replace(/\s+(?:with|at)\s*$/i, "");
  return s.trim();
}

/* ---------------- Date / run_id helpers ---------------- */

function parseRunDate(runId) {
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/.exec(String(runId || ""));
  if (!m) return null;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
  return Number.isNaN(d.getTime()) ? null : d;
}
function fmtRunDate(runId) {
  const d = parseRunDate(runId);
  if (!d) return String(runId || "");
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) +
    " · " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
function fmtShareDate(result) {
  const d = parseRunDate(result && result.run_id) || new Date();
  return d.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

function initDate() {
  const now = new Date();
  els.todayDate.dateTime = now.toISOString().slice(0, 10);
  els.todayDate.textContent = now.toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}

/* ---------------- Watchlist tags ---------------- */

function renderTags(highlightName) {
  els.tagList.innerHTML = state.tags.map((tag) => {
    const hl = highlightName && tag.toLowerCase() === highlightName.toLowerCase() ? " just-added" : "";
    return '<span class="tag' + hl + '"><span>' + escapeHtml(tag) + "</span>" +
      '<button type="button" class="tag-remove" data-tag="' + escapeHtml(tag) + '" aria-label="Remove ' +
      escapeHtml(tag) + ' from the watchlist">' + ICON_X + "</button></span>";
  }).join("");
  els.tagList.querySelectorAll(".tag-remove").forEach((btn) => {
    btn.addEventListener("click", () => removeTag(btn.getAttribute("data-tag")));
  });
  if (highlightName) {
    window.setTimeout(() => {
      els.tagList.querySelectorAll(".tag.just-added").forEach((el) => el.classList.remove("just-added"));
    }, 1800);
  }
}

function addTag(raw, highlight) {
  const name = String(raw || "").trim().replace(/\s+/g, " ");
  if (!name) return false;
  if (state.tags.some((t) => t.toLowerCase() === name.toLowerCase())) return false;
  state.tags.push(name);
  renderTags(highlight ? name : null);
  return true;
}

function removeTag(name) {
  state.tags = state.tags.filter((t) => t !== name);
  renderTags(null);
}

function initTags() {
  els.tagInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === ",") {
      ev.preventDefault();
      if (addTag(els.tagInput.value, false)) els.tagInput.value = "";
    } else if (ev.key === "Backspace" && !els.tagInput.value && state.tags.length) {
      removeTag(state.tags[state.tags.length - 1]);
    }
  });
  els.tagInput.addEventListener("input", () => {
    if (els.tagInput.value.includes(",")) {
      const parts = els.tagInput.value.split(",");
      els.tagInput.value = parts.pop() || "";
      parts.forEach((p) => addTag(p, false));
    }
  });
  els.tagInput.addEventListener("blur", () => {
    if (els.tagInput.value.trim() && addTag(els.tagInput.value, false)) els.tagInput.value = "";
  });
  els.tagBox.addEventListener("click", (ev) => {
    if (ev.target === els.tagBox) els.tagInput.focus();
  });
}

/* ---------------- Video intake ---------------- */

function updateRunButton() {
  const ready = !state.running &&
    (state.sampleMode || (state.beforeFile && state.afterFile));
  els.runBtn.disabled = !ready;
}

function setVideoSide(side, file, url, displayName) {
  const video = side === "before" ? els.videoBefore : els.videoAfter;
  const empty = side === "before" ? els.dropBeforeEmpty : els.dropAfterEmpty;
  const nameEl = side === "before" ? els.fileNameBefore : els.fileNameAfter;
  const zone = side === "before" ? els.dropBefore : els.dropAfter;
  if (!file && !url) return;
  if (file) {
    if (video.dataset.objectUrl) URL.revokeObjectURL(video.dataset.objectUrl);
    const objUrl = URL.createObjectURL(file);
    video.dataset.objectUrl = objUrl;
    video.src = objUrl;
  } else {
    video.removeAttribute("data-object-url");
    video.src = url;
  }
  video.hidden = false;
  empty.hidden = true;
  nameEl.hidden = false;
  nameEl.textContent = displayName || (file ? file.name : "");
  zone.classList.add("has-video");
}

function setFile(side, file) {
  if (!file) return;
  if (file.type && !file.type.startsWith("video/")) {
    showRunError("That file does not look like a video. Please choose the walkthrough recording.");
    return;
  }
  hideRunError();
  if (side === "before") state.beforeFile = file; else state.afterFile = file;
  if (state.sampleMode) {
    state.sampleMode = false;
    els.sampleNote.hidden = true;
  }
  setVideoSide(side, file, null, file.name);
  updateRunButton();
}

function initDropzone(side) {
  const zone = side === "before" ? els.dropBefore : els.dropAfter;
  const input = side === "before" ? els.fileBefore : els.fileAfter;

  zone.addEventListener("click", (ev) => {
    if (ev.target.closest("video")) return;
    if (!zone.classList.contains("has-video") || ev.target === zone) input.click();
  });
  zone.addEventListener("keydown", (ev) => {
    if ((ev.key === "Enter" || ev.key === " ") && !zone.classList.contains("has-video")) {
      ev.preventDefault();
      input.click();
    }
  });
  input.addEventListener("change", () => {
    if (input.files && input.files[0]) setFile(side, input.files[0]);
    input.value = "";
  });
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (ev) => {
    ev.preventDefault();
    zone.classList.add("drag-over");
  }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (ev) => {
    ev.preventDefault();
    zone.classList.remove("drag-over");
  }));
  zone.addEventListener("drop", (ev) => {
    const files = ev.dataTransfer && ev.dataTransfer.files;
    if (files && files[0]) setFile(side, files[0]);
  });
}

/* ---------------- Sample ---------------- */

async function loadSample() {
  hideRunError();
  els.sampleBtn.disabled = true;
  try {
    const resp = await fetch("/api/sample");
    if (!resp.ok) throw new Error("The sample room could not be loaded (" + resp.status + ").");
    const data = await resp.json();
    if (!data.before || !data.after) throw new Error("The sample room is not available on this server.");
    state.sampleMode = true;
    state.sampleLabel = data.label || "Sample room";
    state.beforeFile = null;
    state.afterFile = null;
    setVideoSide("before", null, data.before, data.before.split("/").pop());
    setVideoSide("after", null, data.after, data.after.split("/").pop());
    if (Array.isArray(data.watchlist) && data.watchlist.length) {
      state.tags = [];
      data.watchlist.forEach((item) => addTag(item, false));
      renderTags(null);
    }
    els.sampleNote.hidden = false;
    els.sampleNote.textContent = "Synthetic test room made with Muse Image, so every result can be scored. Real footage works the same way.";
    updateRunButton();
    els.runBtn.focus();
  } catch (err) {
    showRunError(err && err.message ? err.message : "The sample room could not be loaded.");
  } finally {
    els.sampleBtn.disabled = false;
  }
}

/* ---------------- Voice notes ---------------- */

function setVoiceStatus(msg, isError) {
  els.voiceStatus.hidden = !msg;
  els.voiceStatus.textContent = msg || "";
  els.voiceStatus.classList.toggle("voice-status-error", !!isError);
}

function fmtTimer(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return m + ":" + String(s).padStart(2, "0");
}

function stopRecorderUi() {
  if (state.recorderTimer) { window.clearInterval(state.recorderTimer); state.recorderTimer = null; }
  els.voiceStopBtn.hidden = true;
  els.voiceTimer.hidden = true;
  els.voiceBtn.hidden = false;
  els.voiceBtn.disabled = false;
  els.voiceBtnText.textContent = "Speak your care notes";
}

async function sendVoiceNote(blob, mimeType) {
  const ext = mimeType.includes("ogg") ? "ogg" : mimeType.includes("wav") ? "wav" :
    mimeType.includes("mp4") ? "mp4" : "webm";
  const form = new FormData();
  form.append("audio", blob, "care-note." + ext);
  setVoiceStatus("Listening back to your notes…", false);
  try {
    const resp = await fetch("/api/voice-note", { method: "POST", body: form });
    if (!resp.ok) throw new Error("We could not transcribe that recording (" + resp.status + "). Please try again.");
    const data = await resp.json();
    if (data.transcript) {
      els.voiceQuote.hidden = false;
      els.voiceQuoteText.textContent = "“" + data.transcript + "”";
    }
    let added = 0;
    if (Array.isArray(data.items)) {
      data.items.forEach((item) => { if (addTag(item, true)) added += 1; });
    }
    if (data.transcript) {
      setVoiceStatus(added ? "Added " + added + (added === 1 ? " item" : " items") + " to the watchlist below." :
        "Heard you — nothing new to add to the watchlist.", false);
    } else {
      setVoiceStatus("We could not make out any words in that recording. Please try again, a little closer to the microphone.", true);
    }
  } catch (err) {
    setVoiceStatus(err && err.message ? err.message : "We could not transcribe that recording. Please try again.", true);
  }
}

async function startVoiceNote() {
  setVoiceStatus("", false);
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
    setVoiceStatus("This browser cannot record from the microphone. You can type the items that must stay put instead.", true);
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) {
      setVoiceStatus("Microphone permission was denied. Allow microphone access in your browser, or type the items that must stay put instead.", true);
    } else {
      setVoiceStatus("No microphone could be found. You can type the items that must stay put instead.", true);
    }
    return;
  }

  const mimeType = ["audio/webm", "audio/ogg", "audio/mp4", ""].find((t) => {
    try { return !t || MediaRecorder.isTypeSupported(t); } catch (e) { return false; }
  }) || "";
  let recorder;
  try {
    recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
  } catch (err) {
    stream.getTracks().forEach((t) => t.stop());
    setVoiceStatus("Recording is not supported in this browser. You can type the items instead.", true);
    return;
  }
  state.recorder = recorder;
  state.recorderChunks = [];
  recorder.addEventListener("dataavailable", (ev) => {
    if (ev.data && ev.data.size) state.recorderChunks.push(ev.data);
  });
  recorder.addEventListener("stop", () => {
    stream.getTracks().forEach((t) => t.stop());
    const type = recorder.mimeType || mimeType || "audio/webm";
    const blob = new Blob(state.recorderChunks, { type });
    stopRecorderUi();
    if (blob.size) sendVoiceNote(blob, type);
  });

  recorder.start();
  state.recorderStartedAt = Date.now();
  els.voiceBtn.disabled = true;
  els.voiceBtn.hidden = true;
  els.voiceBtnText.textContent = "Recording…";
  els.voiceStopBtn.hidden = false;
  els.voiceTimer.hidden = false;
  els.voiceTimer.textContent = "0:00";
  state.recorderTimer = window.setInterval(() => {
    els.voiceTimer.textContent = fmtTimer((Date.now() - state.recorderStartedAt) / 1000);
  }, 250);
  els.voiceStopBtn.focus();
}

/* ---------------- Stages ---------------- */

const STAGE_DEFS = [
  { id: "voice", title: "Listening to your notes", model: "muse-voice-transcribe-1.0", detail: "", optional: true },
  { id: "normalize", title: "Preparing both walkthroughs", model: "ffmpeg", detail: "5 fps, 640 px" },
  { id: "keyframes", title: "Picking the moments to compare", model: "ffmpeg", detail: "" },
  { id: "inventory", title: "Taking inventory of the room", model: "muse-spark-1.3", detail: "" },
  { id: "track", title: "Tracking every object in both videos", model: "sam-3.1", detail: "" },
  { id: "repair", title: "Learning the family's words", model: "muse-spark-1.3 + sam-3.1", detail: "", optional: true },
  { id: "recheck", title: "Double-checking anything that appeared or vanished", model: "sam-3.1", detail: "" },
  { id: "judge", title: "Deciding what actually moved", model: "muse-spark-1.3", detail: "" },
  { id: "report", title: "Writing the findings", model: "muse-spark-1.3", detail: "" },
  { id: "filter", title: "Holding every claim to its evidence", model: "grounding filter", detail: "" },
];

function renderStage(def) {
  const li = document.createElement("li");
  li.className = "stage-row";
  li.dataset.stage = def.id;
  li.dataset.status = "pending";
  li.innerHTML =
    '<span class="stage-dot" aria-hidden="true"></span>' +
    '<div class="stage-body">' +
      '<div class="stage-head"><span class="stage-title">' + escapeHtml(def.title) + "</span>" +
      '<span class="stage-model mono">' + escapeHtml(def.model) + "</span></div>" +
      '<div class="stage-detail">' + escapeHtml(def.detail || "") + "</div>" +
      '<div class="stage-extra"></div>' +
      '<ul class="stage-lines"></ul>' +
    "</div>";
  return li;
}

function ensureStage(id) {
  if (state.stageRows.has(id)) return state.stageRows.get(id);
  const def = STAGE_DEFS.find((d) => d.id === id) ||
    { id, title: capitalise(id), model: "", detail: "" };
  const row = renderStage(def);
  if (id === "voice") {
    els.stageList.insertBefore(row, els.stageList.firstChild);
  } else {
    const order = STAGE_DEFS.map((d) => d.id);
    let inserted = false;
    for (const child of Array.from(els.stageList.children)) {
      if (order.indexOf(child.dataset.stage) > order.indexOf(id)) {
        els.stageList.insertBefore(row, child);
        inserted = true;
        break;
      }
    }
    if (!inserted) els.stageList.appendChild(row);
  }
  state.stageRows.set(id, row);
  return row;
}

function setStage(id, status, detail) {
  const row = ensureStage(id);
  if (status) row.dataset.status = status;
  if (detail != null) row.querySelector(".stage-detail").textContent = detail;
  return row;
}

function stageExtra(id) { return ensureStage(id).querySelector(".stage-extra"); }
function stageLines(id) { return ensureStage(id).querySelector(".stage-lines"); }

function addStageLine(id, html) {
  const li = document.createElement("li");
  li.innerHTML = html;
  stageLines(id).appendChild(li);
}

function resetStages() {
  els.stageList.innerHTML = "";
  state.stageRows.clear();
  state.trackChips.clear();
  state.inventoryConcepts = [];
  state.trackMarks.clear();
  state.trackTotal = 0;
  state.trackDone = 0;
  state.modelsUsed = [];
  state.lastElapsed = 0;
  state.lastCost = 0;
  STAGE_DEFS.filter((d) => !d.optional).forEach((def) => {
    const row = renderStage(def);
    els.stageList.appendChild(row);
    state.stageRows.set(def.id, row);
  });
  els.liveError.hidden = true;
  updateLedger(null);
}

function noteModel(model) {
  if (model && !state.modelsUsed.includes(model)) state.modelsUsed.push(model);
}

function updateLedger(event) {
  if (event) {
    if (isNum(event.elapsed_s)) state.lastElapsed = event.elapsed_s;
    if (isNum(event.cost_usd)) state.lastCost = event.cost_usd;
    if (event.model) noteModel(event.model);
  }
  const models = state.modelsUsed.length ? state.modelsUsed.join(", ") : "—";
  els.ledgerLine.textContent =
    "elapsed " + state.lastElapsed.toFixed(1) + " s · cost " + fmtCost(state.lastCost) +
    " · models used: " + models;
}

function renderFilmstrips(event) {
  const before = Array.isArray(event.before) ? event.before : [];
  const after = Array.isArray(event.after) ? event.after : [];
  if (!before.length && !after.length) return;
  const strip = (label, urls) =>
    '<div class="filmstrip-group"><div class="filmstrip-label">' + escapeHtml(label) + '</div>' +
    '<div class="filmstrip">' + urls.map((u, i) =>
      '<img src="' + escapeHtml(u) + '" alt="' + escapeHtml(label) + " keyframe " + (i + 1) +
      '" loading="lazy">').join("") + "</div></div>";
  stageExtra("keyframes").innerHTML =
    '<div class="filmstrips">' + strip("Last visit", before) + strip("Today", after) + "</div>";
}

function mergeInventoryConcepts(concepts) {
  if (!Array.isArray(concepts)) return state.inventoryConcepts;
  concepts.forEach((c) => {
    const name = String(c == null ? "" : c).trim();
    if (!name) return;
    if (!state.inventoryConcepts.some((x) => x.toLowerCase() === name.toLowerCase())) {
      state.inventoryConcepts.push(name);
    }
  });
  return state.inventoryConcepts;
}

function renderConceptChips(concepts) {
  if (!Array.isArray(concepts) || !concepts.length) return;
  const all = mergeInventoryConcepts(concepts).slice();
  stageExtra("inventory").innerHTML =
    '<div class="chip-row">' + all.map((c) =>
      '<span class="track-chip">' + escapeHtml(c) + "</span>").join("") + "</div>";
}

function renderTrackChips(concepts) {
  const all = mergeInventoryConcepts(concepts).slice();
  if (!all.length) return;
  stageExtra("track").innerHTML =
    '<div class="chip-row">' + all.map((c) =>
      '<span class="track-chip" data-concept="' + escapeHtml(c) + '"><span>' + escapeHtml(c) + "</span>" +
      '<span class="track-marks">' +
      '<span class="track-mark" data-video="before" title="Last visit">L</span>' +
      '<span class="track-mark" data-video="after" title="Today">T</span>' +
      "</span></span>").join("") + "</div>" +
    '<div class="track-count mono" id="trackCount"></div>';
  state.trackChips.clear();
  stageExtra("track").querySelectorAll(".track-chip").forEach((chip) => {
    const key = (chip.getAttribute("data-concept") || "").toLowerCase();
    state.trackChips.set(key, chip);
    const marks = state.trackMarks.get(key);
    if (marks) {
      ["before", "after"].forEach((side) => {
        if (typeof marks[side] !== "boolean") return;
        const mark = chip.querySelector('.track-mark[data-video="' + side + '"]');
        if (!mark) return;
        mark.classList.toggle("filled", marks[side]);
        mark.classList.toggle("hollow", !marks[side]);
        mark.title = (side === "after" ? "Today" : "Last visit") + ": " +
          (marks[side] ? "found" : "not found");
      });
    }
  });
  updateTrackCount();
}

function updateTrackCount() {
  const el = $("trackCount");
  if (el && state.trackTotal) {
    el.textContent = state.trackDone + "/" + state.trackTotal + " tracks";
  }
}

function markTrack(event) {
  const conceptName = String(event.concept || "").trim();
  if (!conceptName) return;
  const key = conceptName.toLowerCase();
  if (!state.trackChips.has(key)) {
    renderTrackChips([conceptName]);
  }
  const chip = state.trackChips.get(key);
  if (!chip) return;
  const side = event.video === "after" ? "after" : "before";
  const mark = chip.querySelector('.track-mark[data-video="' + side + '"]');
  if (!mark) return;
  const found = isNum(event.detections) ? event.detections > 0 : (isNum(event.frames) && event.frames > 0);
  if (!state.trackMarks.has(key)) state.trackMarks.set(key, { before: null, after: null });
  state.trackMarks.get(key)[side] = found;
  mark.classList.add(found ? "filled" : "hollow");
  mark.classList.remove(found ? "hollow" : "filled");
  mark.title = (side === "after" ? "Today" : "Last visit") + ": " +
    (isNum(event.detections) ? event.detections + " detections" : "checked");
}

function sideWords(video) {
  return video === "after" ? "today" : video === "before" ? "last visit" : "";
}

/* ---------------- SSE handling ---------------- */

function handleEvent(event) {
  if (!event || !event.stage) return;
  updateLedger(event);
  const stage = event.stage;
  const status = event.status;

  if (stage === "voice") {
    noteModel(event.model || "muse-voice-transcribe-1.0");
    setStage("voice", status === "error" ? "error" : "done");
    if (event.transcript) {
      stageLines("voice").innerHTML = "";
      addStageLine("voice", '<span class="voice-line">“' + escapeHtml(event.transcript) + "”</span>");
    } else if (Array.isArray(event.items) && event.items.length) {
      setStage("voice", "done", event.items.join(", "));
    }
    updateLedger(null);
    return;
  }

  if (stage === "error") {
    showLiveError(event.message || "Something went wrong during this check.");
    finishRun(false);
    return;
  }

  if (stage === "done") {
    if (isNum(event.elapsed_s)) state.lastElapsed = event.elapsed_s;
    if (isNum(event.cost_usd)) state.lastCost = event.cost_usd;
    updateLedger(null);
    return;
  }

  if (stage === "result") {
    if (event.result) {
      if (isNum(event.result.cost_usd)) state.lastCost = event.result.cost_usd;
      if (isNum(event.result.latency_s)) state.lastElapsed = event.result.latency_s;
      updateLedger(null);
      renderReport(event.result);
    }
    finishRun(true);
    return;
  }

  const mapped = status === "start" || status === "progress" ? "active" : status === "done" ? "done" : null;
  if (mapped) setStage(stage, mapped);
  if (event.model) noteModel(event.model);

  if (stage === "keyframes" && status === "done") renderFilmstrips(event);

  if (stage === "inventory") {
    if (Array.isArray(event.concepts) && event.concepts.length) mergeInventoryConcepts(event.concepts);
    if (status === "done" && Array.isArray(event.concepts) && event.concepts.length) {
      setStage("inventory", "done", state.inventoryConcepts.length + (state.inventoryConcepts.length === 1 ? " object" : " objects") + " to track");
      renderConceptChips(event.concepts);
    }
  }

  if (stage === "track") {
    if (status === "start") {
      state.trackTotal = isNum(event.total) ? event.total : 0;
      state.trackDone = 0;
      const concepts = Array.isArray(event.concepts) && event.concepts.length
        ? event.concepts : state.inventoryConcepts.slice();
      if (concepts.length) renderTrackChips(concepts);
      if (!state.trackTotal && concepts.length) state.trackTotal = concepts.length * 2;
      updateTrackCount();
    }
    if (status === "progress") {
      if (event.concept && !state.trackChips.has(String(event.concept).toLowerCase())) {
        renderTrackChips([event.concept]);
      }
      markTrack(event);
      state.trackDone = isNum(event.done) ? event.done : state.trackDone + 1;
      if (isNum(event.total)) state.trackTotal = event.total;
      updateTrackCount();
    }
    if (status === "done") setStage("track", "done", state.trackTotal ? state.trackTotal + " tracks finished" : "Tracking finished");
  }

  if (stage === "repair") {
    noteModel("muse-spark-1.3");
    noteModel("sam-3.1");
    if (status === "start") {
      const concepts = Array.isArray(event.concepts) ? event.concepts : [];
      setStage("repair", "active", concepts.length
        ? concepts.length + (concepts.length === 1 ? " name" : " names") + " to learn" : "");
    }
    if (status === "progress") {
      const concept = String(event.concept || "Object");
      const alias = typeof event.alias === "string" && event.alias.trim() ? event.alias.trim() : null;
      const c = isNum(event.c) ? event.c : event.confidence;
      if (alias) {
        addStageLine("repair",
          escapeHtml(concept) + " → “" + escapeHtml(alias) + "”" +
          (isNum(c) ? ' <span class="mono">(c ' + c.toFixed(2) + ")</span>" : ""));
      } else {
        addStageLine("repair", escapeHtml(concept) + " — no visual match");
      }
    }
    if (status === "done") {
      setStage("repair", "done", isNum(event.repaired)
        ? event.repaired + (event.repaired === 1 ? " name matched" : " names matched") : "Done");
    }
    updateLedger(null);
  }

  if (stage === "recheck" && status === "progress") {
    const where = sideWords(event.video);
    const conf = isNum(event.c) ? event.c : event.confidence;
    if (event.found) {
      addStageLine("recheck",
        escapeHtml(capitalise(event.concept || "Object")) + " — found" +
        (where ? " in " + escapeHtml(where) : "") +
        (isNum(conf) ? ' <span class="mono">(c ' + conf.toFixed(2) + ")</span>" : ""));
    } else {
      addStageLine("recheck",
        escapeHtml(capitalise(event.concept || "Object")) + " — confirmed absent" +
        (where ? " from " + escapeHtml(where) : ""));
    }
  }
  if (stage === "recheck" && status === "done") setStage("recheck", "done");

  if (stage === "judge" && status === "progress") {
    const conf = isNum(event.confidence) ? event.confidence : event.c;
    addStageLine("judge",
      escapeHtml(capitalise(event.concept || "Object")) + " — " +
      (event.moved ? "moved" : "stayed") +
      (isNum(conf) ? ' <span class="mono">' + conf.toFixed(2) + "</span>" : "") +
      (event.reason ? ' <span>· ' + escapeHtml(event.reason) + "</span>" : ""));
  }
  if (stage === "judge" && status === "done") setStage("judge", "done");

  if (stage === "report" && status === "done") {
    setStage("report", "done", isNum(event.raw_claims) ? event.raw_claims + " claims suggested" : "");
  }

  if (stage === "filter" && status === "done") {
    const kept = isNum(event.kept) ? event.kept : 0;
    const dropped = isNum(event.dropped) ? event.dropped : 0;
    setStage("filter", "done", kept + " kept · " + dropped + " struck");
  }

  updateLedger(null);
}

function showLiveError(message) {
  els.liveError.hidden = false;
  els.liveErrorText.textContent = message;
  Array.from(state.stageRows.values()).forEach((row) => {
    if (row.dataset.status === "active") row.dataset.status = "error";
  });
}

function closeEvents() {
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
}

function finishRun(scrollToReport) {
  closeEvents();
  state.running = false;
  updateRunButton();
  Array.from(state.stageRows.values()).forEach((row) => {
    if (row.dataset.status === "active") row.dataset.status = "done";
  });
  if (scrollToReport && !els.reportSection.hidden) {
    els.reportSection.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  }
}

/* ---------------- Running a check ---------------- */

function showRunError(msg) {
  els.runError.hidden = false;
  els.runError.textContent = msg;
}
function hideRunError() {
  els.runError.hidden = true;
  els.runError.textContent = "";
}

async function startRun() {
  if (state.running) return;
  hideRunError();
  if (!state.sampleMode && (!state.beforeFile || !state.afterFile)) {
    showRunError("Choose both walkthrough videos first — one from the last visit and one from today.");
    return;
  }

  const form = new FormData();
  if (state.sampleMode) {
    form.append("sample", "1");
  } else {
    form.append("before", state.beforeFile);
    form.append("after", state.afterFile);
  }
  form.append("watchlist", state.tags.join(","));
  form.append("narration", els.narrationCheck.checked ? "1" : "");

  state.running = true;
  state.liveScrolled = false;
  updateRunButton();
  els.runBtn.disabled = true;
  resetStages();
  els.liveSection.hidden = false;
  els.reportSection.hidden = true;

  let runId;
  try {
    const resp = await fetch("/api/runs", { method: "POST", body: form });
    if (!resp.ok) {
      let detail = "";
      try { const j = await resp.json(); detail = j.detail || j.message || ""; } catch (e) { /* keep status text */ }
      throw new Error(detail || "The check could not be started (" + resp.status + ").");
    }
    const data = await resp.json();
    runId = data.run_id;
    if (!runId) throw new Error("The server did not return a run id. Please try again.");
  } catch (err) {
    state.running = false;
    updateRunButton();
    showLiveError(err && err.message ? err.message : "The check could not be started. Please try again.");
    if (!state.liveScrolled) {
      els.liveSection.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
      state.liveScrolled = true;
    }
    return;
  }

  state.runId = runId;
  if (!state.liveScrolled) {
    els.liveSection.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
    state.liveScrolled = true;
  }
  closeEvents();
  const source = new EventSource("/api/runs/" + encodeURIComponent(runId) + "/events");
  state.eventSource = source;
  source.onmessage = (msg) => {
    try { handleEvent(JSON.parse(msg.data)); } catch (e) { /* ignore malformed frames */ }
  };
  source.onerror = () => {
    if (!state.running) return;
    fetch("/api/runs/" + encodeURIComponent(runId))
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        if (data.status === "done" && data.result) { renderReport(data.result); finishRun(true); }
        else if (data.status === "error") {
          const ev = (data.events || []).find((e) => e.stage === "error");
          showLiveError(ev ? ev.message : "This check stopped unexpectedly.");
          finishRun(false);
        }
      })
      .catch(() => { /* leave the live view as-is */ });
  };
}

/* ---------------- Report rendering ---------------- */

const RISK_ORDER = { high: 0, medium: 1, low: 2 };
function riskOf(item) {
  const r = String((item && item.risk) || "medium").toLowerCase();
  return RISK_ORDER.hasOwnProperty(r) ? r : "medium";
}
function sortedByRisk(items) {
  return (Array.isArray(items) ? items : []).slice()
    .sort((a, b) => RISK_ORDER[riskOf(a)] - RISK_ORDER[riskOf(b)]);
}

function normConceptKey(value) {
  return String(value == null ? "" : value).toLowerCase().replace(/_/g, " ")
    .replace(/\s+/g, " ").trim();
}
function slugForId(value) {
  return normConceptKey(value).replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "item";
}
function attentionTargetId(prefix, concept, index) {
  return prefix + "-" + (isNum(index) ? index : 0) + "-" + slugForId(concept);
}

function aliasFor(result, concept) {
  try {
    const aliases = result && result.aliases;
    if (!aliases || !concept) return null;
    const wanted = normConceptKey(concept);
    const pick = (v) => {
      if (typeof v === "string") return v.trim() || null;
      if (v && typeof v === "object") {
        const a = v.alias || v.tracked_as || v.trackedAs || v.name || v.value;
        return typeof a === "string" && a.trim() ? a.trim() : null;
      }
      return null;
    };
    if (Array.isArray(aliases)) {
      for (const item of aliases) {
        if (!item || typeof item !== "object") continue;
        const key = normConceptKey(item.concept || item.item || item.name || "");
        const alias = pick(item.alias != null ? item.alias : item);
        if (alias && key && key === wanted) return alias;
        if (alias && !key && aliases.length === 1) return alias;
      }
      return null;
    }
    if (typeof aliases === "object") {
      for (const key of Object.keys(aliases)) {
        if (normConceptKey(key) === wanted) return pick(aliases[key]);
      }
    }
  } catch (e) { /* old / odd shapes must never crash the report */ }
  return null;
}

function normalizeImageUrl(raw) {
  if (typeof raw !== "string") return null;
  let u = raw.trim().replace(/\\/g, "/");
  if (!u) return null;
  if (!/^(https?:\/\/|data:|blob:|\/)/i.test(u)) u = "/" + u;
  return u;
}

function collectImageStrings(pool, out, seen) {
  if (pool == null || seen.has(pool)) return out;
  if (typeof pool === "string") { out.push(pool); return out; }
  if (typeof pool !== "object") return out;
  seen.add(pool);
  if (Array.isArray(pool)) pool.forEach((v) => collectImageStrings(v, out, seen));
  else Object.keys(pool).forEach((k) => collectImageStrings(pool[k], out, seen));
  return out;
}

function claimImages(claim, result) {
  const out = { before: null, after: null };
  try {
    if (claim && claim.images) {
      out.before = normalizeImageUrl(claim.images.before) || null;
      out.after = normalizeImageUrl(claim.images.after) || null;
    }
    if (claim && claim.evidence && claim.evidence.images) {
      out.before = out.before || normalizeImageUrl(claim.evidence.images.before);
      out.after = out.after || normalizeImageUrl(claim.evidence.images.after);
    }
    const concept = String((claim && claim.concept) || "");
    const underscored = concept.trim().toLowerCase().replace(/\s+/g, "_");
    if (result && result.annotated_images) {
      const pool = result.annotated_images;
      if (!Array.isArray(pool) && pool && typeof pool === "object") {
        const key = concept;
        let entry = pool[key] || pool[underscored] || null;
        if (!entry) {
          const matchKey = Object.keys(pool).find((k) =>
            k.toLowerCase().includes(key.toLowerCase()) || key.toLowerCase().includes(k.toLowerCase()));
          if (matchKey) entry = pool[matchKey];
        }
        if (typeof entry === "string") {
          const u = normalizeImageUrl(entry);
          if (/before/i.test(entry)) out.before = out.before || u; else out.after = out.after || u;
        } else if (entry && typeof entry === "object" && !Array.isArray(entry)) {
          out.before = out.before || normalizeImageUrl(entry.before);
          out.after = out.after || normalizeImageUrl(entry.after);
        } else if (Array.isArray(entry)) {
          entry.forEach((s) => {
            const u = normalizeImageUrl(s);
            if (!u) return;
            if (/before/i.test(String(s))) out.before = out.before || u;
            else if (/after/i.test(String(s))) out.after = out.after || u;
          });
        }
      }
      if ((!out.before || !out.after) && underscored) {
        const strings = collectImageStrings(pool, [], new Set());
        strings.forEach((raw) => {
          const u = normalizeImageUrl(raw);
          if (!u) return;
          const low = u.toLowerCase();
          if (!out.before && low.includes("/before_" + underscored + ".")) out.before = u;
          if (!out.after && low.includes("/after_" + underscored + ".")) out.after = u;
        });
      }
    }
  } catch (e) { /* fall through with whatever was found */ }
  return out;
}

function formatRecheck(recheck) {
  if (!recheck || typeof recheck !== "object" || !Object.keys(recheck).length) return "not re-checked";
  if (recheck.checked === false) return "not re-checked";
  const conf = isNum(recheck.c) ? recheck.c : recheck.confidence;
  let text;
  if (typeof recheck.found === "boolean") text = recheck.found ? "found" : "not found";
  else if (recheck.result) text = String(recheck.result);
  else text = "checked";
  const where = recheck.video ? sideWords(recheck.video) : recheck.where || "";
  if (where) text += " in " + where;
  if (isNum(recheck.frame)) text += ", frame " + recheck.frame;
  if (isNum(recheck.keyframe)) text += ", keyframe " + recheck.keyframe;
  if (isNum(conf)) text += " (c " + conf.toFixed(2) + ")";
  return text;
}

function evidenceBoard(claim, result) {
  const ev = (claim && claim.evidence) || {};
  const images = claimImages(claim, result);
  const plate = (url, label, frame) => {
    const caption = escapeHtml(label) + (isNum(frame) ?
      ' · <span class="mono">frame ' + frame + "</span>" : "");
    if (url) {
      return '<figure class="plate"><img src="' + escapeHtml(url) + '" alt="' +
        escapeHtml(label) + " evidence frame for " + escapeHtml(claim.concept || "this object") +
        '" loading="lazy"><figcaption>' + caption + "</figcaption></figure>";
    }
    return '<figure class="plate"><div class="plate-missing">not in frame</div><figcaption>' +
      caption + "</figcaption></figure>";
  };
  const rows = [
    ["Frames seen — last visit / today", fmtCount(ev.frames_before) + " / " + fmtCount(ev.frames_after)],
    ["Confidence — last visit / today", fmtConf(ev.confidence_before) + " / " + fmtConf(ev.confidence_after)],
    ["SAM re-check", formatRecheck(ev.recheck)],
  ];
  if (claim && claim.risk_reason) rows.push(["Why this risk", String(claim.risk_reason)]);
  rows.push(["Source", (claim && claim.source) || "—"]);
  if (ev.label) rows.unshift(["SAM finding", String(ev.label).replace(/_/g, " ")]);
  const table = '<table class="evidence-table"><tbody>' + rows.map((r) =>
    "<tr><th scope=\"row\">" + escapeHtml(r[0]) + "</th><td>" + escapeHtml(r[1]) + "</td></tr>").join("") +
    "</tbody></table>";
  return '<div class="plates">' +
    plate(images.before, "Last visit", ev.best_frame_before) +
    plate(images.after, "Today", ev.best_frame_after) +
    "</div>" + table;
}

function evidenceDisclosure(claim, result) {
  return '<details class="evidence"><summary>' + ICON_EYE + "Evidence</summary>" +
    '<div class="evidence-board">' + evidenceBoard(claim, result) + "</div></details>";
}

function changeClass(change) {
  const c = String(change || "").toLowerCase();
  return c === "added" || c === "removed" || c === "moved" ? "change-" + c : "";
}

function trackedAsHtml(result, concept) {
  const alias = aliasFor(result, concept);
  if (!alias) return "";
  return '<p class="tracked-as mono">tracked as “' + escapeHtml(alias) + "”</p>";
}

/* ---------------- "Do this next" + "Mark as sorted" ---------------- */

function doNextSteps(kind, conceptRaw) {
  const concept = String(conceptRaw == null ? "" : conceptRaw).trim().replace(/\s+/g, " ").toLowerCase() || "item";
  const k = String(kind || "").toLowerCase();
  if (k === "moved") {
    return [
      "Ask Dad first: did he move the " + concept + " on purpose? If so, that is the new setup — film it as the next baseline.",
      "If not, whoever is there puts it back where it was set up, with Dad. Far away? Send this to someone local — never ask Dad to move furniture alone.",
      "Next visit, film this corner again — Second Look will confirm it is back.",
    ];
  }
  if (k === "removed" || k === "missing") {
    return [
      "Ask Dad where the " + concept + " is, then put it back where he expects it.",
      "If it was taken away on purpose, take it off the watchlist.",
      "Re-check next visit.",
    ];
  }
  if (k === "added" || k === "appeared") {
    return [
      "If the " + concept + " is on the floor or in a walkway, move it out of the path, with Dad.",
      "Check the route from bed to bathroom is clear.",
      "Re-check next visit.",
    ];
  }
  if (k === "not_seen") {
    return [
      "Look for the " + concept + " in person.",
      "Film that corner slowly next visit.",
    ];
  }
  return [];
}

function sortedKey(result, concept) {
  const runId = (result && result.run_id) || state.runId || "run";
  return "second-look:sorted:" + String(runId) + ":" + normConceptKey(concept);
}
function readSorted(result, concept) {
  try { return window.localStorage.getItem(sortedKey(result, concept)) === "1"; }
  catch (e) { return false; }
}
function writeSorted(result, concept, sorted) {
  try {
    if (sorted) window.localStorage.setItem(sortedKey(result, concept), "1");
    else window.localStorage.removeItem(sortedKey(result, concept));
  } catch (e) { /* private mode / storage unavailable: toggle still works for this view */ }
}

function applySorted(owner, btn, stateEl, sorted) {
  owner.classList.toggle("is-sorted", sorted);
  btn.setAttribute("aria-pressed", sorted ? "true" : "false");
  if (stateEl) stateEl.hidden = !sorted;
}

function makeSortedControl(owner, result, concept) {
  const wrap = document.createElement("div");
  wrap.className = "sorted-row";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn btn-quiet sorted-btn";
  btn.innerHTML = ICON_CHECK + "<span>Mark as sorted</span>";
  btn.setAttribute("aria-pressed", "false");
  const stateEl = document.createElement("span");
  stateEl.className = "sorted-state";
  stateEl.textContent = "Sorted";
  stateEl.hidden = true;
  wrap.appendChild(btn);
  wrap.appendChild(stateEl);
  applySorted(owner, btn, stateEl, readSorted(result, concept));
  btn.addEventListener("click", () => {
    const next = btn.getAttribute("aria-pressed") !== "true";
    writeSorted(result, concept, next);
    applySorted(owner, btn, stateEl, next);
    /* Sorted items leave the "Needs attention" count (and document title) at once. */
    if (state.currentResult) renderAttentionBanner(state.currentResult);
  });
  return wrap;
}

function makeDoNext(kind, concept, result, owner) {
  const steps = doNextSteps(kind, concept);
  if (!steps.length) return null;
  const block = document.createElement("div");
  block.className = "do-next";
  block.innerHTML =
    '<p class="do-next-title">Do this next</p>' +
    "<ol>" + steps.map((s) => "<li>" + escapeHtml(s) + "</li>").join("") + "</ol>";
  block.appendChild(makeSortedControl(owner, result, concept));
  return block;
}

function renderFinding(claim, result, index) {
  claim = claim || {};
  const risk = riskOf(claim);
  const change = String(claim.change || "").toLowerCase();
  const el = document.createElement("article");
  el.className = "finding";
  el.id = attentionTargetId("finding", claim.concept || "object", index);
  el.dataset.concept = String(claim.concept || "");
  const explanation = cleanExplanation(claim.explanation || "");
  el.innerHTML =
    '<div class="finding-top">' +
    '<span class="risk-tag risk-' + risk + '"><span class="risk-dot" aria-hidden="true"></span>' +
    escapeHtml(risk) + " risk</span></div>" +
    '<h4 class="finding-title ' + changeClass(change) + '">' +
    escapeHtml(sentenceCase(claim.concept || "Object")) + " — " + escapeHtml(change) + "</h4>" +
    trackedAsHtml(result, claim.concept) +
    (explanation ? '<p class="finding-text">' + escapeHtml(explanation) + "</p>" : "") +
    (claim.safety_note ? '<p class="finding-note">' + escapeHtml(claim.safety_note) + "</p>" : "") +
    evidenceDisclosure(claim, result);
  if (risk === "high" || risk === "medium") {
    const block = makeDoNext(change, claim.concept, result, el);
    if (block) el.appendChild(block);
  } else {
    el.appendChild(makeSortedControl(el, result, claim.concept));
  }
  return el;
}

function renderStruck(claim, result, index) {
  claim = claim || {};
  const el = document.createElement("article");
  el.className = "struck";
  const delay = reducedMotion() ? 0 : index * 120;
  const explanation = cleanExplanation(claim.explanation || "");
  el.innerHTML =
    '<h4 class="struck-title"><span class="strike-wrap"><span class="strike-text">' +
    escapeHtml(sentenceCase(claim.concept || "Object")) + " — " +
    escapeHtml(String(claim.change || "").toLowerCase()) +
    '</span><svg class="strike-svg" viewBox="0 0 300 12" preserveAspectRatio="none" aria-hidden="true">' +
    '<path class="strike-path" style="--strike-delay:' + delay + 'ms" ' +
    'd="M2 7 C 40 3, 70 11, 110 6 S 180 3, 220 8 S 280 5, 298 7"/></svg></span></h4>' +
    trackedAsHtml(result, claim.concept) +
    (claim.reason ? '<p class="struck-reason">' + escapeHtml(claim.reason) + "</p>" : "") +
    (explanation ? '<p class="struck-text">' + escapeHtml(explanation) + "</p>" : "") +
    evidenceDisclosure(claim, result);
  return el;
}

const WATCH_STATUS_WORDS = {
  in_place: "seen where it was",
  moved: "moved",
  missing: "gone from where it was",
  appeared: "new in the room",
  not_seen: "not seen in this video",
};

const WATCH_STATUS_NOTES = {
  in_place: "We can see it is there, not that it is reachable or working.",
  not_seen: "Not the same as missing — check it in person.",
};

function renderWatchlist(result) {
  const items = Array.isArray(result.watchlist_status) ? result.watchlist_status : [];
  els.watchlistBlock.hidden = !items.length;
  els.watchlistRows.innerHTML = "";
  items.forEach((item, rowIndex) => {
    item = item || {};
    const risk = riskOf(item);
    const statusKey = String(item.status || "not_seen").toLowerCase();
    const status = WATCH_STATUS_WORDS[statusKey] || String(item.status || "not seen").replace(/_/g, " ");
    const concept = item.concept || item.item || "";
    const row = document.createElement("div");
    row.className = "watch-row";
    row.id = attentionTargetId("watch", concept || "item", rowIndex);
    row.dataset.concept = String(concept || "");
    const itemImages = (item.images && (item.images.before || item.images.after))
      ? { before: normalizeImageUrl(item.images.before), after: normalizeImageUrl(item.images.after) }
      : claimImages({ concept }, result);
    const thumbs = [];
    if (itemImages.before) {
      thumbs.push('<img src="' + escapeHtml(itemImages.before) + '" alt="Last visit: ' +
        escapeHtml(concept) + '" loading="lazy">');
    }
    if (itemImages.after) {
      thumbs.push('<img src="' + escapeHtml(itemImages.after) + '" alt="Today: ' +
        escapeHtml(concept) + '" loading="lazy">');
    }
    const statusNote = WATCH_STATUS_NOTES[statusKey] || "";
    const serverNote = item.note && String(item.note) !== statusNote ? String(item.note) : "";
    row.innerHTML =
      '<div class="watch-main"><span class="watch-name">' + escapeHtml(concept) + "</span>" +
      ' <span class="watch-status">— ' + escapeHtml(status) + "</span>" +
      trackedAsHtml(result, concept) +
      (statusNote ? '<div class="watch-note">' + escapeHtml(statusNote) + "</div>" : "") +
      (serverNote ? '<div class="watch-note">' + escapeHtml(serverNote) + "</div>" : "") + "</div>" +
      '<span class="risk-tag risk-' + risk + '"><span class="risk-dot" aria-hidden="true"></span>' +
      escapeHtml(risk) + " risk</span>" +
      (thumbs.length ? '<div class="watch-thumbs">' + thumbs.join("") + "</div>" : "");
    if (statusKey === "moved" || statusKey === "missing" || statusKey === "not_seen") {
      const main = row.querySelector(".watch-main");
      const block = makeDoNext(statusKey, concept, result, row);
      if (block && main) main.appendChild(block);
    }
    els.watchlistRows.appendChild(row);
  });
}

/* ---------------- "Needs attention" banner ---------------- */

const WATCH_ATTENTION_STATUSES = ["missing", "moved", "not_seen"];

function watchAttentionPhrase(statusKey) {
  if (statusKey === "missing") return "gone from where it was";
  if (statusKey === "moved") return "moved";
  if (statusKey === "not_seen") return "not seen in this video";
  if (statusKey === "appeared") return "new in the room";
  return "needs attention";
}

/* Kept HIGH findings + watchlist rows that are HIGH or missing/moved/not_seen,
   de-duplicated by concept (a concept already listed as a finding is not
   listed again as a watchlist row). Sorted items stay listed, marked sorted. */
function collectAttentionItems(result) {
  const items = [];
  const seen = new Set();
  const kept = sortedByRisk(
    Array.isArray(result.kept_claims) ? result.kept_claims
      : Array.isArray(result.claims) ? result.claims : []);
  kept.forEach((claim, i) => {
    claim = claim || {};
    if (riskOf(claim) !== "high") return;
    const concept = String(claim.concept || "Object");
    const change = String(claim.change || "").toLowerCase();
    items.push({
      concept,
      kind: change,
      label: sentenceCase(concept) + " — " + change,
      targetId: attentionTargetId("finding", concept, i),
      sorted: readSorted(result, concept),
    });
    seen.add(normConceptKey(concept));
  });
  const watch = Array.isArray(result.watchlist_status) ? result.watchlist_status : [];
  watch.forEach((item, i) => {
    item = item || {};
    const statusKey = String(item.status || "not_seen").toLowerCase();
    if (riskOf(item) !== "high" && !WATCH_ATTENTION_STATUSES.includes(statusKey)) return;
    const concept = String(item.concept || item.item || "Item");
    if (seen.has(normConceptKey(concept))) return;
    seen.add(normConceptKey(concept));
    items.push({
      concept,
      kind: statusKey,
      label: sentenceCase(concept) + " — " + watchAttentionPhrase(statusKey),
      targetId: attentionTargetId("watch", concept, i),
      sorted: readSorted(result, concept),
    });
  });
  return items;
}

function highlightAttentionTarget(targetId) {
  const target = document.getElementById(targetId);
  if (!target) return;
  target.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
  target.classList.remove("attention-highlight");
  /* Restart the highlight even if this target was just highlighted. */
  void target.offsetWidth;
  target.classList.add("attention-highlight");
  window.setTimeout(() => target.classList.remove("attention-highlight"), 1900);
}

function renderAttentionBanner(result) {
  if (!els.attentionBanner || !result) return;
  const items = collectAttentionItems(result);
  state.attentionItems = items;
  const pending = items.filter((item) => !item.sorted);
  const sortedItems = items.filter((item) => item.sorted);
  const n = pending.length;

  document.title = n > 0 ? "(" + n + ") " + DEFAULT_TITLE : DEFAULT_TITLE;

  const sortedListHtml = sortedItems.length
    ? '<ul class="attention-list attention-sorted-list">' + sortedItems.map((item) =>
        '<li class="is-sorted"><span>' + escapeHtml(item.label) + '</span>' +
        '<span class="attention-sorted-badge">Sorted</span></li>').join("") + "</ul>"
    : "";

  if (!n) {
    els.attentionBanner.className = "attention-banner is-calm";
    els.attentionBanner.innerHTML =
      '<p class="attention-calm">Nothing needs attention — every watched item was seen where it was.</p>' +
      sortedListHtml;
    els.attentionBanner.hidden = false;
    return;
  }

  els.attentionBanner.className = "attention-banner is-alert";
  els.attentionBanner.innerHTML =
    '<h3 class="attention-title">Needs attention: ' + n + "</h3>" +
    '<ul class="attention-list">' + pending.map((item) =>
      '<li><a class="attention-link" href="#' + escapeHtml(item.targetId) +
      '" data-target="' + escapeHtml(item.targetId) + '">' +
      escapeHtml(item.label) + "</a></li>").join("") + "</ul>" +
    sortedListHtml;
  els.attentionBanner.hidden = false;
  els.attentionBanner.querySelectorAll(".attention-link").forEach((link) => {
    link.addEventListener("click", (ev) => {
      ev.preventDefault();
      highlightAttentionTarget(link.getAttribute("data-target"));
    });
  });
}

function renderReport(result) {
  if (!result || typeof result !== "object") return;
  state.currentResult = result;
  if (result.run_id) state.runId = result.run_id;
  const kept = Array.isArray(result.kept_claims) ? result.kept_claims
    : Array.isArray(result.claims) ? result.claims : [];
  const dropped = Array.isArray(result.dropped) ? result.dropped : [];
  const stats = (result.stats && typeof result.stats === "object") ? result.stats : {};

  els.reportSummary.textContent = result.summary ||
    "This check is complete. The findings below are the ones the evidence supports.";

  const conceptCount = isNum(stats.concepts) ? stats.concepts :
    isNum(result.concepts) ? result.concepts :
    (Array.isArray(result.concepts) ? result.concepts.length : kept.length + dropped.length);
  const samRequests = isNum(stats.sam_requests) ? stats.sam_requests :
    isNum(result.sam_requests) ? result.sam_requests : 0;
  els.reportStats.textContent =
    "Checked " + conceptCount + (conceptCount === 1 ? " object" : " objects") +
    " · " + samRequests + " SAM tracks · " + fmtCost(result.cost_usd) + " · " + fmtSeconds(result.latency_s);

  const runDate = parseRunDate(result.run_id);
  const printDate = runDate ?
    runDate.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" }) :
    new Date().toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
  els.printHeader.textContent = "Second Look — Room check, " + printDate;

  renderWatchlist(result);

  const sortedKept = sortedByRisk(kept);
  els.findingsList.innerHTML = "";
  sortedKept.forEach((claim, i) => els.findingsList.appendChild(renderFinding(claim, result, i)));
  els.findingsEmpty.hidden = sortedKept.length > 0;

  els.struckBlock.hidden = false;
  els.struckList.innerHTML = "";
  const struckNote = els.struckBlock.querySelector(".report-note");
  if (!dropped.length) {
    if (struckNote) struckNote.hidden = true;
    const quiet = document.createElement("p");
    quiet.className = "report-empty struck-empty";
    quiet.textContent = "Nothing was struck this time — every claim had its evidence.";
    els.struckList.appendChild(quiet);
  } else {
    if (struckNote) struckNote.hidden = false;
    dropped.forEach((claim, i) => els.struckList.appendChild(renderStruck(claim, result, i)));
  }

  renderAttentionBanner(result);

  const models = Array.isArray(result.models) ? result.models : [];
  const ledgerModels = [
    ["muse-spark-1.3", "reasons"],
    ["sam-3.1", "proves"],
  ];
  if (models.includes("muse-voice-transcribe-1.0")) {
    ledgerModels.push(["muse-voice-transcribe-1.0", "listens"]);
  }
  const footerBits =
    '<span class="ledger-heading">Three Meta models ran this check</span>' +
    ledgerModels.map((pair) =>
      '<span class="model-chip">' + escapeHtml(pair[0]) + " · " + escapeHtml(pair[1]) + "</span>").join("");
  const statBits = [
    isNum(stats.spark_calls) ? stats.spark_calls + " Spark calls" : null,
    isNum(stats.sam_requests) ? stats.sam_requests + " SAM requests" : null,
    isNum(stats.sam_frames) ? stats.sam_frames + " SAM frames" : null,
    isNum(stats.rechecks) ? stats.rechecks + " re-checks" : null,
    "cost " + fmtCost(result.cost_usd),
    "took " + fmtSeconds(result.latency_s),
    result.run_id ? "run " + result.run_id : null,
  ].filter(Boolean).map((s) => '<span class="footer-stat">' + escapeHtml(s) + "</span>").join("");
  els.footerLedger.innerHTML = footerBits + statBits +
    '<p class="ledger-credit">Built with Muse Image (test room) and Muse Wonder (code). Engine: SplatDiff.</p>';

  els.reportSection.hidden = false;
  els.reportSection.classList.remove("report-animated");
  if (!reducedMotion()) {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => els.reportSection.classList.add("report-animated"));
    });
  } else {
    els.reportSection.classList.add("report-animated");
  }
}

/* ---------------- Copy / print / send to family ---------------- */

function buildCopyText(result) {
  if (!result) return "";
  const lines = [];
  lines.push("Second Look room check" + (result.run_id ? " (" + fmtRunDate(result.run_id) + ")" : ""));
  if (result.summary) lines.push("", result.summary);
  const kept = sortedByRisk(result.kept_claims || result.claims || []);
  if (kept.length) {
    lines.push("", "What changed:");
    kept.forEach((c) => {
      const alias = aliasFor(result, c.concept);
      lines.push("- " + sentenceCase(c.concept || "") + " — " + String(c.change || "").toLowerCase() +
        " (" + riskOf(c) + " risk)" +
        (alias ? " [tracked as “" + alias + "”]" : "") +
        (c.explanation ? ": " + cleanExplanation(c.explanation) : "") +
        (c.safety_note ? " " + c.safety_note : "") +
        (c.risk_reason ? " Why this risk: " + c.risk_reason : ""));
    });
  }
  const dropped = Array.isArray(result.dropped) ? result.dropped : [];
  if (dropped.length) {
    lines.push("", "Struck from the report (not supported by evidence):");
    dropped.forEach((c) => {
      lines.push("- " + sentenceCase(c.concept || "") + " — " + String(c.change || "").toLowerCase() +
        (c.reason ? ": " + c.reason : ""));
    });
  } else {
    lines.push("", "Nothing was struck this time — every claim had its evidence.");
  }
  lines.push("", "Cost " + fmtCost(result.cost_usd) + " · took " + fmtSeconds(result.latency_s));
  return lines.join("\n");
}

async function copySummary() {
  const text = buildCopyText(state.currentResult);
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "absolute";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* clipboard unavailable */ }
    document.body.removeChild(ta);
  }
  els.copyBtnText.textContent = "Copied";
  window.setTimeout(() => { els.copyBtnText.textContent = "Copy summary"; }, 2000);
}

/* Plain-text share body, kept under ~1800 chars so mail clients do not choke. */
function buildShareText(result) {
  if (!result) return "";
  const disclaimer = "Not a medical device.";
  const lines = [];
  lines.push("Second Look — room check " + fmtShareDate(result));
  if (result.summary) lines.push("", String(result.summary).trim());

  const attention = (Array.isArray(state.attentionItems) ? state.attentionItems : collectAttentionItems(result))
    .filter((item) => !item.sorted);
  if (attention.length) {
    lines.push("", "Needs attention:");
    attention.forEach((item) => {
      lines.push("- " + item.label);
      const steps = doNextSteps(item.kind, item.concept);
      const usable = steps.length ? steps : ["Check this item in person.", "Re-check next visit."];
      lines.push("  Do this next: " + usable.map((s, i) => (i + 1) + ". " + s).join(" "));
    });
  } else {
    lines.push("", "Nothing needs attention — every watched item was seen where it was.");
  }

  const dropped = Array.isArray(result.dropped) ? result.dropped : [];
  if (dropped.length) {
    lines.push("", "Struck from the report (not supported by evidence):");
    dropped.forEach((c) => {
      lines.push("- " + sentenceCase(c.concept || "") + " — " + String(c.change || "").toLowerCase() +
        (c.reason ? ": " + c.reason : ""));
    });
  }

  lines.push("", disclaimer);
  let text = lines.join("\n");
  if (text.length > 1800) {
    const budget = 1800 - disclaimer.length - 2;
    text = text.slice(0, budget).replace(/\s+\S*$/, "").trimEnd() + "\n" + disclaimer;
  }
  return text;
}

async function shareSummary() {
  const result = state.currentResult;
  if (!result) return;
  const title = "Second Look — room check " + fmtShareDate(result);
  const text = buildShareText(result);
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ title, text });
      return;
    } catch (err) {
      /* The family member closed the share sheet — do not fall through to email. */
      if (err && err.name === "AbortError") return;
      /* Any other share failure falls back to email below. */
    }
  }
  const mailto = "mailto:?subject=" + encodeURIComponent(title) +
    "&body=" + encodeURIComponent(text);
  window.location.href = mailto;
}

/* ---------------- History ---------------- */

function renderHistory(items) {
  if (!Array.isArray(items) || !items.length) {
    els.historyList.innerHTML = '<p class="history-empty">No checks yet — try the sample room.</p>';
    return;
  }
  els.historyList.innerHTML = "";
  items.forEach((item) => {
    item = item || {};
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-item";
    const kept = isNum(item.kept) ? item.kept : 0;
    const dropped = isNum(item.dropped) ? item.dropped : 0;
    btn.innerHTML =
      '<span class="history-item-summary">' + escapeHtml(item.summary || "Room check") + "</span>" +
      '<span class="history-item-meta">' + escapeHtml(fmtRunDate(item.run_id)) + " · " +
      kept + " kept · " + dropped + ' struck · <span class="mono">' + fmtCost(item.cost_usd) +
      " · " + fmtSeconds(item.latency_s) + "</span></span>";
    btn.addEventListener("click", () => loadHistoryItem(item.run_id));
    els.historyList.appendChild(btn);
  });
}

async function loadHistoryItem(runId) {
  if (!runId) return;
  els.historyList.innerHTML = '<p class="history-status">Loading that check…</p>';
  try {
    const resp = await fetch("/api/history/" + encodeURIComponent(runId));
    if (!resp.ok) throw new Error("That check could not be loaded (" + resp.status + ").");
    const result = await resp.json();
    renderReport(result || {});
    els.historyDrawer.hidden = true;
    els.historyBtn.setAttribute("aria-expanded", "false");
    els.reportSection.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  } catch (err) {
    els.historyList.innerHTML = '<p class="history-status history-status-error">' +
      escapeHtml(err && err.message ? err.message : "That check could not be loaded.") + "</p>";
  }
}

async function toggleHistory() {
  const opening = els.historyDrawer.hidden;
  els.historyDrawer.hidden = !opening;
  els.historyBtn.setAttribute("aria-expanded", String(opening));
  if (!opening) return;
  els.historyList.innerHTML = '<p class="history-status">Loading past checks…</p>';
  try {
    const resp = await fetch("/api/history");
    if (!resp.ok) throw new Error("Past checks could not be loaded (" + resp.status + ").");
    renderHistory(await resp.json());
  } catch (err) {
    els.historyList.innerHTML = '<p class="history-status history-status-error">' +
      escapeHtml(err && err.message ? err.message : "Past checks could not be loaded.") + "</p>";
  }
}

/* ---------------- Wiring ---------------- */

function init() {
  initDate();
  initTags();
  initDropzone("before");
  initDropzone("after");
  renderTags(null);
  updateRunButton();
  els.voiceStopBtn.hidden = true;
  els.voiceTimer.hidden = true;
  els.voiceBtn.hidden = false;

  els.sampleBtn.addEventListener("click", loadSample);
  els.runBtn.addEventListener("click", startRun);
  els.retryBtn.addEventListener("click", () => {
    els.liveError.hidden = true;
    if (state.sampleMode || (state.beforeFile && state.afterFile)) startRun();
    else {
      document.getElementById("intake").scrollIntoView({
        behavior: reducedMotion() ? "auto" : "smooth", block: "start",
      });
      els.runBtn.focus();
    }
  });
  els.historyBtn.addEventListener("click", toggleHistory);
  els.historyClose.addEventListener("click", () => {
    els.historyDrawer.hidden = true;
    els.historyBtn.setAttribute("aria-expanded", "false");
    els.historyBtn.focus();
  });
  els.voiceBtn.addEventListener("click", startVoiceNote);
  els.voiceStopBtn.addEventListener("click", () => {
    if (state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
    else stopRecorderUi();
  });
  els.printBtn.addEventListener("click", () => window.print());
  els.copyBtn.addEventListener("click", copySummary);
  if (els.shareBtn) els.shareBtn.addEventListener("click", shareSummary);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !els.historyDrawer.hidden) {
      els.historyDrawer.hidden = true;
      els.historyBtn.setAttribute("aria-expanded", "false");
    }
  });

  /* Deep link ?sample=1: run the same action as "Use the sample room"
     (previews + watchlist), then scroll to the actions. Never auto-start
     the check itself — the user still presses "Check the room". */
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("sample") === "1") {
      Promise.resolve(loadSample()).then(() => {
        const target = els.actions || els.runBtn;
        if (target) {
          target.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
        }
      });
    }
  } catch (e) { /* malformed query string: load the page normally */ }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
