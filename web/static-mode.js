/*
 * Second Look — static (GitHub Pages) mode.
 *
 * Implements window.SL per build_log/STATIC_CONTRACT.md:
 *   - visitor's own Meta API key dialog (sessionStorage only)
 *   - direct browser -> api.meta.ai client (Spark, SAM 3.1, ASR)
 *   - fetch shim serving baked JSON + local (in-tab) state for /api/...
 *   - EventSource shim (recorded replay, local pipeline, local feed)
 *   - static-demo banner
 *
 * Plain ES2019, no dependencies. Defensive try/catch throughout.
 * The API key is never logged anywhere.
 */
(function () {
  'use strict';

  if (!window.SL_STATIC) {
    return;
  }

  var BASE = typeof window.SL_BASE === 'string' && window.SL_BASE ? window.SL_BASE : '/splatdiff';
  // Normalise: no trailing slash (except root, which this never is).
  if (BASE.length > 1 && BASE.charAt(BASE.length - 1) === '/') {
    BASE = BASE.slice(0, BASE.length - 1);
  }

  var API_ORIGIN = 'https://api.meta.ai';
  var KEY_STORAGE = 'sl_meta_key';
  var GITHUB_URL = 'https://github.com/harshitaggarwal01/splatdiff';
  var GET_KEY_URL = 'https://dev.meta.ai';
  var SPARK_MODEL = 'muse-spark-1.3';
  var SAM_MODEL = 'sam-3.1';
  var ASR_MODEL = 'muse-voice-transcribe-1.0';
  var FRIENDLY_501 = "Available when you run Second Look yourself \u2014 see GitHub.";

  var nativeFetch = window.fetch ? window.fetch.bind(window) : null;
  var NativeEventSource = window.EventSource || null;

  function noop() {}

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function nowIso() {
    try { return new Date().toISOString(); } catch (e) { return ''; }
  }

  function truncateWords(text, maxWords) {
    var words = String(text == null ? '' : text).split(/\s+/).filter(function (w) { return w.length; });
    if (words.length <= maxWords) { return words.join(' '); }
    return words.slice(0, maxWords).join(' ').replace(/[,;:]$/, '') + '.';
  }

  function safeStr(value, limit) {
    if (value == null) { return null; }
    var text = String(value).trim();
    if (!text) { return null; }
    return limit && text.length > limit ? text.slice(0, limit) : text;
  }

  // -------------------------------------------------------------------------
  // Words-only sanitising (mirrors splatdiff/agent.py strip_keys)
  // -------------------------------------------------------------------------
  var BAD_KEY_PARTS = ['image', 'url', 'path', 'keyframe', 'transcript'];

  function isBadKey(key) {
    var low = String(key).toLowerCase();
    for (var i = 0; i < BAD_KEY_PARTS.length; i++) {
      if (low.indexOf(BAD_KEY_PARTS[i]) !== -1) { return true; }
    }
    return false;
  }

  function stripKeys(obj) {
    var i, keys, out;
    if (Array.isArray(obj)) {
      out = [];
      for (i = 0; i < obj.length; i++) { out.push(stripKeys(obj[i])); }
      return out;
    }
    if (obj && typeof obj === 'object') {
      out = {};
      keys = Object.keys(obj);
      for (i = 0; i < keys.length; i++) {
        if (isBadKey(keys[i])) { continue; }
        out[keys[i]] = stripKeys(obj[keys[i]]);
      }
      return out;
    }
    // Never let an inline data:/blob: payload slip through as a bare string.
    if (typeof obj === 'string' && (obj.indexOf('data:') === 0 || obj.indexOf('blob:') === 0)) {
      return null;
    }
    return obj;
  }

  // -------------------------------------------------------------------------
  // Injected CSS (banner, key chip, key dialog — Care dossier styling)
  // -------------------------------------------------------------------------
  var CSS_TEXT = [
    '.sl-banner{position:sticky;top:0;z-index:2147483000;display:block;',
    'background:#2f2a24;color:#f6efe3;font:13px/1.45 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;',
    'padding:7px 14px;text-align:center;letter-spacing:.01em}',
    '.sl-banner a{color:#ffd9a0;font-weight:600;text-decoration:underline;text-underline-offset:2px}',
    '.sl-banner a:focus-visible{outline:2px solid #ffd9a0;outline-offset:2px}',
    '.sl-keychip{position:fixed;right:12px;bottom:12px;z-index:2147483000;display:flex;gap:8px;align-items:center;',
    'background:#fffaf0;color:#2f2a24;border:1px solid #d8c9a8;border-radius:999px;',
    'box-shadow:0 4px 18px rgba(47,42,36,.18);padding:6px 8px 6px 12px;',
    'font:12.5px/1.3 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}',
    '.sl-keychip button{background:#2f2a24;color:#f6efe3;border:0;border-radius:999px;padding:4px 10px;',
    'font:inherit;cursor:pointer}',
    '.sl-keychip button:focus-visible{outline:2px solid #2f2a24;outline-offset:2px}',
    'dialog.sl-keydialog{border:1px solid #d8c9a8;border-radius:14px;padding:0;max-width:480px;width:calc(100vw - 40px);',
    'background:#fffaf0;color:#2f2a24;box-shadow:0 18px 60px rgba(47,42,36,.35);',
    'font:15px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}',
    'dialog.sl-keydialog::backdrop{background:rgba(47,42,36,.5)}',
    '.sl-keydialog-inner{padding:24px 26px 20px}',
    '.sl-keydialog h2{margin:0 0 10px;font-size:20px;line-height:1.3}',
    '.sl-keydialog p{margin:0 0 14px}',
    '.sl-keydialog label{display:block;font-weight:600;margin:0 0 6px}',
    '.sl-keydialog input[type="password"]{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #b8a888;',
    'border-radius:8px;font:inherit;background:#fff}',
    '.sl-keydialog input[type="password"]:focus{outline:2px solid #2f2a24;outline-offset:1px}',
    '.sl-keydialog .sl-keyerror{color:#9c2b1b;min-height:1.4em;margin:8px 0 0;font-weight:600}',
    '.sl-keydialog .sl-keyactions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:16px}',
    '.sl-keydialog button{border-radius:999px;padding:9px 18px;font:inherit;cursor:pointer}',
    '.sl-keydialog .sl-usekey{background:#2f2a24;color:#f6efe3;border:1px solid #2f2a24;font-weight:600}',
    '.sl-keydialog .sl-cancelkey{background:transparent;color:#2f2a24;border:1px solid #b8a888}',
    '.sl-keydialog button:focus-visible{outline:2px solid #2f2a24;outline-offset:2px}',
    '.sl-keydialog a{color:#7a4b12;font-weight:600}',
    '.sl-keydialog button[disabled]{opacity:.6;cursor:wait}'
  ].join('');

  var cssInjected = false;
  function injectCss() {
    if (cssInjected) { return; }
    cssInjected = true;
    try {
      var style = document.createElement('style');
      style.setAttribute('data-sl-static', '1');
      style.textContent = CSS_TEXT;
      (document.head || document.documentElement).appendChild(style);
    } catch (e) { /* styling only */ }
  }

  // -------------------------------------------------------------------------
  // API key handling + dialog + chip
  // -------------------------------------------------------------------------
  var keyDialog = null;
  var keyDialogParts = null;
  var keyRequirePending = null;

  function getKey() {
    try {
      var k = window.sessionStorage.getItem(KEY_STORAGE);
      return k && String(k).trim() ? String(k).trim() : null;
    } catch (e) {
      return null;
    }
  }

  function setKey(k) {
    try { window.sessionStorage.setItem(KEY_STORAGE, String(k)); } catch (e) { /* private mode */ }
    showKeyChip();
  }

  function clearKey() {
    try { window.sessionStorage.removeItem(KEY_STORAGE); } catch (e) { /* ignore */ }
    hideKeyChip();
  }

  function hideKeyChip() {
    try {
      var chip = document.getElementById('sl-keychip');
      if (chip && chip.parentNode) { chip.parentNode.removeChild(chip); }
    } catch (e) { /* ignore */ }
  }

  function showKeyChip() {
    try {
      if (!document.body || !getKey()) { return; }
      if (document.getElementById('sl-keychip')) { return; }
      injectCss();
      var chip = document.createElement('div');
      chip.id = 'sl-keychip';
      chip.className = 'sl-keychip';
      var label = document.createElement('span');
      label.textContent = 'Your key \u00B7 this tab only \u00B7 ';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = 'Forget';
      btn.setAttribute('aria-label', 'Forget the Meta API key stored in this tab');
      btn.addEventListener('click', function () { clearKey(); });
      chip.appendChild(label);
      chip.appendChild(btn);
      document.body.appendChild(chip);
    } catch (e) { /* chip is cosmetic */ }
  }

  function buildKeyDialog() {
    if (keyDialog) { return keyDialogParts; }
    injectCss();
    var dialog = document.createElement('dialog');
    dialog.className = 'sl-keydialog';
    dialog.id = 'sl-keydialog';
    dialog.setAttribute('aria-labelledby', 'sl-keydialog-title');
    dialog.setAttribute('aria-describedby', 'sl-keydialog-desc');

    var inner = document.createElement('div');
    inner.className = 'sl-keydialog-inner';

    var title = document.createElement('h2');
    title.id = 'sl-keydialog-title';
    title.textContent = 'Use your own Meta API key for this session';

    var desc = document.createElement('p');
    desc.id = 'sl-keydialog-desc';
    desc.textContent = "Live features call Meta's models directly from this browser. " +
      "Your key stays in this tab only (sessionStorage) and is sent only to api.meta.ai \u2014 never to us. " +
      "Close the tab and it's gone.";

    var label = document.createElement('label');
    label.setAttribute('for', 'sl-keydialog-input');
    label.textContent = 'Meta API key';

    var input = document.createElement('input');
    input.type = 'password';
    input.id = 'sl-keydialog-input';
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('placeholder', 'Paste your key here');

    var error = document.createElement('p');
    error.className = 'sl-keyerror';
    error.id = 'sl-keydialog-error';
    error.setAttribute('role', 'alert');
    error.setAttribute('aria-live', 'polite');

    var actions = document.createElement('div');
    actions.className = 'sl-keyactions';

    var useBtn = document.createElement('button');
    useBtn.type = 'button';
    useBtn.className = 'sl-usekey';
    useBtn.textContent = 'Use key';

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'sl-cancelkey';
    cancelBtn.textContent = 'Cancel';

    var link = document.createElement('a');
    link.href = GET_KEY_URL;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Get a key';

    actions.appendChild(useBtn);
    actions.appendChild(cancelBtn);
    actions.appendChild(link);

    inner.appendChild(title);
    inner.appendChild(desc);
    inner.appendChild(label);
    inner.appendChild(input);
    inner.appendChild(error);
    inner.appendChild(actions);
    dialog.appendChild(inner);
    document.body.appendChild(dialog);

    keyDialog = dialog;
    keyDialogParts = {
      dialog: dialog, input: input, error: error, useBtn: useBtn, cancelBtn: cancelBtn
    };
    return keyDialogParts;
  }

  function validateKey(candidate) {
    return nativeFetch(API_ORIGIN + '/v1/models', {
      method: 'GET',
      headers: { 'Authorization': 'Bearer ' + candidate }
    }).then(function (resp) {
      return { ok: !!(resp && resp.ok), status: resp ? resp.status : 0 };
    }, function () {
      return { ok: false, status: 0 };
    });
  }

  function requireKey(reason) {
    var existing = getKey();
    if (existing) {
      showKeyChip();
      return Promise.resolve(existing);
    }
    if (keyRequirePending) { return keyRequirePending; }

    keyRequirePending = new Promise(function (resolve, reject) {
      function settle(fn, value) {
        keyRequirePending = null;
        fn(value);
      }
      function start() {
        var parts;
        try {
          parts = buildKeyDialog();
        } catch (e) {
          settle(reject, new Error('Could not open the key dialog.'));
          return;
        }
        var dialog = parts.dialog;
        parts.error.textContent = '';
        parts.input.value = '';
        if (reason) {
          try { dialog.setAttribute('aria-label', String(reason)); } catch (e) { /* ignore */ }
        }

        function cleanup() {
          parts.useBtn.removeEventListener('click', onUse);
          parts.cancelBtn.removeEventListener('click', onCancel);
          dialog.removeEventListener('cancel', onNativeCancel);
          parts.input.removeEventListener('keydown', onKeydown);
        }
        function closeDialog() {
          try { if (dialog.open) { dialog.close(); } } catch (e) { /* ignore */ }
        }
        function onCancel() {
          cleanup();
          closeDialog();
          settle(reject, new Error('Meta API key entry was cancelled.'));
        }
        function onNativeCancel(ev) {
          if (ev) { try { ev.preventDefault(); } catch (e) { /* ignore */ } }
          onCancel();
        }
        function onKeydown(ev) {
          if (ev && ev.key === 'Enter') {
            try { ev.preventDefault(); } catch (e) { /* ignore */ }
            onUse();
          }
        }
        function onUse() {
          var candidate = String(parts.input.value || '').trim();
          if (!candidate) {
            parts.error.textContent = "That key didn't work.";
            try { parts.input.focus(); } catch (e) { /* ignore */ }
            return;
          }
          parts.useBtn.disabled = true;
          parts.cancelBtn.disabled = true;
          parts.error.textContent = 'Checking\u2026';
          validateKey(candidate).then(function (result) {
            parts.useBtn.disabled = false;
            parts.cancelBtn.disabled = false;
            if (result.ok) {
              setKey(candidate);
              parts.input.value = '';
              cleanup();
              closeDialog();
              settle(resolve, candidate);
            } else if (result.status === 401 || result.status === 403) {
              parts.error.textContent = "That key didn't work.";
              try { parts.input.focus(); parts.input.select(); } catch (e) { /* ignore */ }
            } else if (result.status === 0) {
              parts.error.textContent = 'Could not reach api.meta.ai to check that key.';
            } else {
              parts.error.textContent = "That key didn't work.";
            }
          });
        }

        parts.useBtn.addEventListener('click', onUse);
        parts.cancelBtn.addEventListener('click', onCancel);
        dialog.addEventListener('cancel', onNativeCancel);
        parts.input.addEventListener('keydown', onKeydown);
        try {
          if (typeof dialog.showModal === 'function') { dialog.showModal(); }
          else { dialog.setAttribute('open', ''); }
        } catch (e) {
          try { dialog.setAttribute('open', ''); } catch (e2) { /* ignore */ }
        }
        try { parts.input.focus(); } catch (e) { /* ignore */ }
      }

      if (document.body) { start(); }
      else {
        document.addEventListener('DOMContentLoaded', start, { once: true });
      }
    });
    return keyRequirePending;
  }

  // -------------------------------------------------------------------------
  // Baked static data (docs/static/*.json)
  // -------------------------------------------------------------------------
  var bakedCache = {};

  function bakedJson(name) {
    if (Object.prototype.hasOwnProperty.call(bakedCache, name)) {
      return bakedCache[name];
    }
    bakedCache[name] = nativeFetch(BASE + '/static/' + name, { method: 'GET' })
      .then(function (resp) {
        if (!resp || !resp.ok) { throw new Error('Missing baked data: ' + name); }
        return resp.json();
      });
    return bakedCache[name];
  }

  function bakedOr(name, fallback) {
    return bakedJson(name).then(function (data) { return data; }, function () { return fallback; });
  }

  // -------------------------------------------------------------------------
  // Local (this-tab) state: feed entries, history, runs
  // -------------------------------------------------------------------------
  var localFeedEntries = [];      // newest appended last (chronological)
  var localResultsById = {};      // run_id -> full pipeline result
  var localHistoryList = [];      // newest first, history-shaped rows
  var localRuns = {};             // run_id -> run record
  var feedListeners = [];         // FakeEventSource instances for /api/feed/events
  var pendingRunListeners = {};   // run_id -> [FakeEventSource] waiting for run creation

  function historyRowFromResult(result) {
    if (!result || typeof result !== 'object') { return null; }
    return {
      run_id: result.run_id || null,
      room: result.room || null,
      filmed_by: result.filmed_by || null,
      ts: result.ts || result.date || result.created_at || null,
      summary: typeof result.summary === 'string' ? result.summary : null,
      local: true
    };
  }

  function registerLocalResult(result) {
    if (!result || typeof result !== 'object' || !result.run_id) { return; }
    localResultsById[String(result.run_id)] = result;
    var row = historyRowFromResult(result);
    if (row) {
      localHistoryList = localHistoryList.filter(function (r) { return r.run_id !== row.run_id; });
      localHistoryList.unshift(row);
    }
  }

  function notifyFeedListeners(entry) {
    var snapshot = feedListeners.slice();
    for (var i = 0; i < snapshot.length; i++) {
      try { snapshot[i]._dispatch({ type: 'entry', entry: entry }); } catch (e) { /* ignore */ }
    }
  }

  function addLocalFeedEntry(entry) {
    if (!entry || typeof entry !== 'object') { return null; }
    var copy = {};
    var keys = Object.keys(entry);
    for (var i = 0; i < keys.length; i++) { copy[keys[i]] = entry[keys[i]]; }
    if (!copy.id && !copy.run_id) { copy.id = 'local-' + Date.now(); }
    if (!copy.ts) { copy.ts = nowIso(); }
    copy.local = true;
    localFeedEntries.push(copy);
    notifyFeedListeners(copy);
    return copy;
  }

  function feedEntriesOf(baked) {
    if (Array.isArray(baked)) { return baked.slice(); }
    if (baked && Array.isArray(baked.entries)) { return baked.entries.slice(); }
    if (baked && Array.isArray(baked.feed)) { return baked.feed.slice(); }
    return [];
  }

  function mergedFeed(baked) {
    var entries = feedEntriesOf(baked).concat(localFeedEntries);
    if (Array.isArray(baked)) { return entries; }
    if (baked && typeof baked === 'object') {
      var out = {};
      var keys = Object.keys(baked);
      for (var i = 0; i < keys.length; i++) { out[keys[i]] = baked[keys[i]]; }
      out.entries = entries;
      return out;
    }
    return { entries: entries };
  }

  function mergedHistory(baked) {
    var bakedList = [];
    var rest = null;
    if (Array.isArray(baked)) { bakedList = baked.slice(); }
    else if (baked && Array.isArray(baked.history)) { bakedList = baked.history.slice(); rest = baked; }
    else if (baked && Array.isArray(baked.runs)) { bakedList = baked.runs.slice(); rest = baked; }
    var seen = {};
    var merged = [];
    var i, id;
    for (i = 0; i < localHistoryList.length; i++) {
      id = localHistoryList[i].run_id;
      if (id) { seen[id] = true; }
      merged.push(localHistoryList[i]);
    }
    for (i = 0; i < bakedList.length; i++) {
      id = bakedList[i] && (bakedList[i].run_id || bakedList[i].id);
      if (id && seen[id]) { continue; }
      merged.push(bakedList[i]);
    }
    if (rest) {
      var out = {};
      var keys = Object.keys(rest);
      for (i = 0; i < keys.length; i++) { out[keys[i]] = rest[keys[i]]; }
      if (Array.isArray(rest.history)) { out.history = merged; } else { out.runs = merged; }
      return out;
    }
    return merged;
  }

  // -------------------------------------------------------------------------
  // Meta API client
  // -------------------------------------------------------------------------
  function metaFetch(path, options) {
    return getKey() ? Promise.resolve(getKey()) : requireKey('Live features need a Meta API key.');
    // (returns key promise; actual request built by caller wrappers below)
  }
  // metaFetch above is only a key gate helper; real requests:
  function authedFetch(path, options) {
    var gate = getKey() ? Promise.resolve(getKey()) : requireKey('Live features need a Meta API key.');
    return gate.then(function (key) {
      var opts = options || {};
      var headers = {};
      var src = opts.headers || {};
      Object.keys(src).forEach(function (k) { headers[k] = src[k]; });
      headers['Authorization'] = 'Bearer ' + key;
      var init = { method: opts.method || 'GET', headers: headers };
      if (opts.body !== undefined) { init.body = opts.body; }
      return nativeFetch(API_ORIGIN + path, init);
    });
  }

  function responses(body) {
    var payload;
    try { payload = JSON.stringify(body || {}); } catch (e) {
      return Promise.reject(new Error('Could not encode the model request.'));
    }
    var attempt = 0;
    function tryOnce() {
      attempt += 1;
      return authedFetch('/v1/responses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
      }).then(function (resp) {
        var status = resp ? resp.status : 0;
        if ((status === 429 || status >= 500) && attempt <= 3) {
          return sleep(600 * Math.pow(2, attempt - 1)).then(tryOnce);
        }
        if (!resp || !resp.ok) {
          return resp.text().then(function (txt) {
            throw new Error('Meta API request failed (' + status + ')' + (txt ? ': ' + String(txt).slice(0, 300) : ''));
          }, function () {
            throw new Error('Meta API request failed (' + status + ')');
          });
        }
        return resp.json();
      }, function (err) {
        if (attempt <= 3) {
          return sleep(600 * Math.pow(2, attempt - 1)).then(tryOnce);
        }
        throw err;
      });
    }
    return tryOnce();
  }

  function extractText(resp) {
    var out = '';
    try {
      var items = (resp && resp.output) || [];
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (!item || item.type !== 'message') { continue; }
        var content = item.content || [];
        for (var j = 0; j < content.length; j++) {
          var part = content[j];
          if (part && part.type === 'output_text' && typeof part.text === 'string') {
            out += part.text;
          }
        }
      }
    } catch (e) { /* return what we have */ }
    return out;
  }

  function parseJsonLoose(text) {
    if (text == null) { return null; }
    if (typeof text === 'object') { return text; }
    var s = String(text).trim();
    s = s.replace(/```(?:json)?/gi, '').trim();
    var first = s.indexOf('{');
    var last = s.lastIndexOf('}');
    if (first === -1 || last === -1 || last < first) {
      // Maybe a bare array.
      var fa = s.indexOf('[');
      var la = s.lastIndexOf(']');
      if (fa !== -1 && la > fa) { return JSON.parse(s.slice(fa, la + 1)); }
      return null;
    }
    return JSON.parse(s.slice(first, last + 1));
  }

  // SAM 3.1 output text grammar: <Nf> markers, then "ordinal <|box;k=v;...|>"
  function parseSamText(text) {
    var detections = [];
    if (!text) { return detections; }
    var parts = String(text).split(/<(\d+)f>/);
    // parts: [pre, frameIdx, segment, frameIdx, segment, ...]
    for (var i = 1; i + 1 < parts.length + 1 && i < parts.length; i += 2) {
      var segment = parts[i + 1] || '';
      var boxRe = /(\d+)\s*<\|box;([^|]*)\|>/g;
      var m;
      while ((m = boxRe.exec(segment)) !== null) {
        var fields = {};
        var pairs = String(m[2]).split(';');
        for (var p = 0; p < pairs.length; p++) {
          var eq = pairs[p].indexOf('=');
          if (eq === -1) { continue; }
          var k = pairs[p].slice(0, eq).trim();
          var v = parseFloat(pairs[p].slice(eq + 1));
          if (k && isFinite(v)) { fields[k] = v; }
        }
        if (fields.x1 == null || fields.y1 == null || fields.x2 == null || fields.y2 == null) { continue; }
        detections.push({
          box: [fields.x1, fields.y1, fields.x2, fields.y2],
          c: fields.c != null ? fields.c : 1,
          w: fields.w != null ? fields.w : 0,
          h: fields.h != null ? fields.h : 0
        });
      }
    }
    return detections;
  }

  function samImage(dataUrl, concept) {
    var body = {
      model: SAM_MODEL,
      input: [{
        type: 'message',
        role: 'user',
        content: [
          { type: 'input_text', text: String(concept || '') },
          { type: 'input_image', image_url: String(dataUrl || '') }
        ]
      }],
      metadata: { include_confidence: 'true', mask_encoding: 'one_bit' },
      store: false
    };
    return responses(body).then(function (resp) {
      return parseSamText(extractText(resp));
    });
  }

  function transcribe(wavBlob) {
    var gate = getKey() ? Promise.resolve(getKey()) : requireKey('Voice notes need a Meta API key.');
    return gate.then(function (key) {
      var form = new FormData();
      var requestBlob = new Blob(
        [JSON.stringify({ model: ASR_MODEL, audioEncoding: 'WAV', mode: 'DIARIZATION' })],
        { type: 'application/json' }
      );
      form.append('request', requestBlob);
      form.append('audio', wavBlob, 'voice-note.wav');
      return nativeFetch(API_ORIGIN + '/v1/asr/transcribe', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + key, 'Accept': 'text/plain' },
        body: form
      }).then(function (resp) {
        if (!resp || !resp.ok) {
          return resp.text().then(function (txt) {
            throw new Error('Transcription failed (' + (resp ? resp.status : 0) + ')' + (txt ? ': ' + String(txt).slice(0, 300) : ''));
          }, function () {
            throw new Error('Transcription failed (' + (resp ? resp.status : 0) + ')');
          });
        }
        return resp.text();
      });
    });
  }

  // -------------------------------------------------------------------------
  // Audio: arbitrary blob -> 16 kHz mono PCM16 WAV
  // -------------------------------------------------------------------------
  function encodeWav16k(samples, sampleRate) {
    var buffer = new ArrayBuffer(44 + samples.length * 2);
    var view = new DataView(buffer);
    function writeStr(offset, s) {
      for (var i = 0; i < s.length; i++) { view.setUint8(offset + i, s.charCodeAt(i)); }
    }
    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);       // PCM
    view.setUint16(22, 1, true);       // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    for (var i = 0; i < samples.length; i++) {
      var s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return new Blob([buffer], { type: 'audio/wav' });
  }

  function toWav16k(blob) {
    if (!blob) { return Promise.reject(new Error('No audio to convert.')); }
    var AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx || !window.OfflineAudioContext) {
      return Promise.reject(new Error("This browser can't convert audio for transcription."));
    }
    return blob.arrayBuffer().then(function (arrayBuffer) {
      var decodeCtx;
      try { decodeCtx = new AudioCtx(); } catch (e) {
        return Promise.reject(new Error("This browser can't decode that audio."));
      }
      var decodedPromise;
      try {
        decodedPromise = decodeCtx.decodeAudioData(arrayBuffer.slice(0));
      } catch (e) {
        if (decodeCtx.close) { try { decodeCtx.close(); } catch (e2) { /* ignore */ } }
        return Promise.reject(e);
      }
      return decodedPromise.then(function (decoded) {
        if (decodeCtx.close) { try { decodeCtx.close(); } catch (e) { /* ignore */ } }
        var targetRate = 16000;
        var length = Math.max(1, Math.ceil(decoded.duration * targetRate));
        var offline = new window.OfflineAudioContext(1, length, targetRate);
        var source = offline.createBufferSource();
        source.buffer = decoded;
        source.connect(offline.destination);
        source.start(0);
        return offline.startRendering().then(function (rendered) {
          return encodeWav16k(rendered.getChannelData(0), targetRate);
        });
      }, function (err) {
        if (decodeCtx.close) { try { decodeCtx.close(); } catch (e) { /* ignore */ } }
        throw err;
      });
    });
  }

  // -------------------------------------------------------------------------
  // Small concurrency pool (max N in flight)
  // -------------------------------------------------------------------------
  function mapLimit(items, limit, worker) {
    return new Promise(function (resolve, reject) {
      var results = new Array(items.length);
      var next = 0;
      var active = 0;
      var done = false;
      if (!items.length) { resolve(results); return; }
      function launch() {
        while (!done && active < limit && next < items.length) {
          (function (idx) {
            active += 1;
            Promise.resolve()
              .then(function () { return worker(items[idx], idx); })
              .then(function (value) {
                results[idx] = value;
                active -= 1;
                if (next >= items.length && active === 0 && !done) {
                  done = true; resolve(results);
                } else { launch(); }
              }, function (err) {
                if (!done) { done = true; reject(err); }
              });
          })(next);
          next += 1;
        }
      }
      launch();
    });
  }

  function sparkText(prompt, maxTokens) {
    var started = Date.now();
    var body = {
      model: SPARK_MODEL,
      input: [{
        type: 'message',
        role: 'user',
        content: [{ type: 'input_text', text: String(prompt || '') }]
      }],
      reasoning: { effort: 'low' },
      max_output_tokens: maxTokens || 2500
    };
    return responses(body).then(function (resp) {
      var text = extractText(resp).trim();
      if (!text) {
        body.max_output_tokens = Math.max((maxTokens || 2500) * 3, 4000);
        body.metadata = { retry: '1' };
        return responses(body).then(function (resp2) {
          return { text: extractText(resp2).trim(), latency_s: Math.round((Date.now() - started) / 10) / 100 };
        });
      }
      return { text: text, latency_s: Math.round((Date.now() - started) / 10) / 100 };
    });
  }

  // -------------------------------------------------------------------------
  // Family agent (faithful port of splatdiff/agent.py ask + update; words only)
  // -------------------------------------------------------------------------
  function sourceLookup(context) {
    var lookup = {};
    var i, digest, entry, runId;
    var checks = (context && context.recent_checks) || [];
    for (i = 0; i < checks.length; i++) {
      digest = checks[i];
      if (!digest || typeof digest !== 'object') { continue; }
      runId = digest.run_id;
      if (runId && !lookup[String(runId)]) {
        lookup[String(runId)] = {
          run_id: String(runId),
          room: digest.room || null,
          ts: digest.ts || digest.date || null
        };
      }
    }
    var feed = (context && context.feed) || [];
    for (i = 0; i < feed.length; i++) {
      entry = feed[i];
      if (!entry || typeof entry !== 'object') { continue; }
      runId = entry.run_id || entry.id;
      if (runId && !lookup[String(runId)]) {
        lookup[String(runId)] = {
          run_id: String(runId),
          room: entry.room || null,
          ts: entry.ts || null
        };
      }
    }
    return lookup;
  }

  function digestLocalResult(result) {
    if (!result || typeof result !== 'object') { return null; }
    var kept = [];
    var rawKept = result.kept_claims || result.claims || [];
    if (Array.isArray(rawKept)) {
      rawKept.forEach(function (claim) {
        if (!claim || typeof claim !== 'object') { return; }
        kept.push({
          concept: safeStr(claim.concept || claim.name || claim.item, 120),
          change: safeStr(claim.change || claim.label, 60),
          risk: safeStr(claim.risk, 40),
          explanation: safeStr(claim.explanation || claim.reason, 400)
        });
      });
    }
    var dropped = [];
    var rawDropped = result.dropped || result.dropped_claims || [];
    if (Array.isArray(rawDropped)) {
      rawDropped.forEach(function (claim) {
        if (!claim || typeof claim !== 'object') { return; }
        dropped.push({
          concept: safeStr(claim.concept || claim.name || claim.item, 120),
          change: safeStr(claim.change || claim.label, 60),
          reason: safeStr(claim.reason, 400)
        });
      });
    }
    var watch = [];
    var rawWatch = result.watchlist_status || result.watchlist_results || [];
    if (Array.isArray(rawWatch)) {
      rawWatch.forEach(function (entry) {
        if (!entry || typeof entry !== 'object') { return; }
        watch.push({
          concept: safeStr(entry.concept || entry.name || entry.item, 120),
          status: safeStr(entry.status || entry.state, 60),
          note: safeStr(entry.note || entry.reason || entry.explanation, 300)
        });
      });
    }
    return stripKeys({
      run_id: safeStr(result.run_id, 80),
      room: safeStr(result.room, 80) || 'Bedroom',
      filmed_by: safeStr(result.filmed_by, 80),
      date: safeStr(result.ts || result.date || result.created_at, 80),
      ts: safeStr(result.ts || result.date || result.created_at, 80),
      summary: safeStr(result.summary, 600),
      kept_claims: kept,
      dropped_claims: dropped,
      watchlist_status: watch
    });
  }

  function agentContext() {
    return bakedOr('agent_context.json', { feed: [], rooms: [], recent_checks: [] })
      .then(function (base) {
        var context = stripKeys(base && typeof base === 'object' ? base : {});
        if (!Array.isArray(context.feed)) { context.feed = []; }
        if (!Array.isArray(context.rooms)) { context.rooms = []; }
        if (!Array.isArray(context.recent_checks)) { context.recent_checks = []; }
        // Local feed entries (words only) go in newest-first, like the server.
        var localFeed = localFeedEntries.slice().reverse().map(function (e) { return stripKeys(e); });
        context.feed = localFeed.concat(context.feed).slice(0, 30);
        // Local pipeline results from this tab, newest first.
        var localDigests = [];
        Object.keys(localResultsById).forEach(function (id) {
          var d = digestLocalResult(localResultsById[id]);
          if (d) { localDigests.push(d); }
        });
        context.recent_checks = localDigests.concat(context.recent_checks).slice(0, 3);
        return stripKeys(context);
      });
  }

  function agentAsk(question) {
    var q = String(question == null ? '' : question).trim();
    if (!q) { return Promise.reject(new Error('question is required')); }
    if (q.length > 500) { return Promise.reject(new Error('question must be at most 500 characters')); }
    return agentContext().then(function (context) {
      var lookup = sourceLookup(context);
      var prompt =
        "You are the family assistant for Second Look, which checks on Dad's rooms " +
        "from short walkthrough videos. You are given RECORDS ONLY (words, never pictures).\n\n" +
        "RULES \u2014 follow all of them:\n" +
        "1. Answer ONLY from the records below. Never invent, guess or use outside knowledge.\n" +
        "2. If the records don't say, your answer must include the exact sentence " +
        "\"The checks don't show that yet\" and suggest re-filming the room.\n" +
        "3. Cite the checks you use inline, like [Bedroom, Nov 4 7:15 PM], using each " +
        "check's room and date (recent_checks have a ready-made 'citation' field \u2014 copy it).\n" +
        "4. Use plain, warm language a family member would use.\n" +
        "5. Never give medical advice.\n" +
        "6. Never claim something is reachable, safe or unsafe beyond what was actually seen " +
        "in a check; only report what the records say changed or was seen. Say 'seen where it " +
        "was' (never 'where it should be', 'fine' or 'safe') and note that a check shows " +
        "presence, not whether Dad can reach it.\n" +
        "7. Keep the answer to at most 120 words.\n" +
        "8. Return STRICT JSON only, no markdown fences: " +
        "{\"answer\": \"<your answer>\", \"source_run_ids\": [\"<run_id of each check cited>\"]}. " +
        "source_run_ids must only contain run_id values that appear in the records.\n\n" +
        "RECORDS (JSON):\n" + JSON.stringify(context) + "\n\n" +
        "QUESTION: " + q;
      return sparkText(prompt, 2500).then(function (out) {
        var answer = '';
        var sourceIds = [];
        try {
          var parsed = parseJsonLoose(out.text);
          if (parsed && typeof parsed === 'object') {
            answer = String(parsed.answer || '').trim();
            var rawIds = parsed.source_run_ids || parsed.sources || [];
            if (Array.isArray(rawIds)) {
              rawIds.forEach(function (item) {
                var v = item;
                if (v && typeof v === 'object') { v = v.run_id || v.id; }
                if (v != null && String(v).trim()) { sourceIds.push(String(v).trim()); }
              });
            }
          }
        } catch (e) {
          answer = out.text;
        }
        if (!answer) {
          answer = out.text || "The checks don't show that yet. It may help to re-film the room.";
        }
        answer = truncateWords(answer, 120);
        var sources = [];
        var seen = {};
        sourceIds.forEach(function (runId) {
          if (seen[runId]) { return; }
          seen[runId] = true;
          if (lookup[runId]) { sources.push(lookup[runId]); }
        });
        return { answer: answer, sources: sources, model: SPARK_MODEL, latency_s: out.latency_s };
      });
    });
  }

  var UPDATE_RULES = {
    nearby:
      "Write for the family member who lives NEARBY and will visit next. " +
      "Give practical to-dos for the next visit, based only on the records. " +
      "Tell them to ask Dad first, and to put things back together with him " +
      "(not for him) where the records mention a change. Warm and concrete.",
    far:
      "Write for the family member who lives FAR away. Say what changed, who " +
      "is handling it (use filmed_by / the nearby person if the records say), " +
      "and what, if anything, they can do from afar (for example: call Dad, " +
      "or thank the person nearby). Do not alarm them; be calm and clear.",
    dad:
      "Write directly TO Dad, in the second person (\"you\"). Be respectful " +
      "and short. Use NO risk words (never say risk, danger, hazard, safety, " +
      "fall or unsafe). Ask for his view on any change, in the spirit of: " +
      "\"Did you move the lamp to read by your chair? If you like it there, " +
      "we'll keep it that way.\" Never mention cameras, filming, videos, " +
      "checks, AI or models."
  };

  function agentUpdate(kind, name) {
    var audience = String(kind == null ? '' : kind).trim().toLowerCase();
    if (!UPDATE_RULES[audience]) {
      return Promise.reject(new Error('for must be one of: nearby, far, dad'));
    }
    var recipient = null;
    if (name != null) {
      recipient = String(name).trim() || null;
      if (recipient && recipient.length > 100) {
        return Promise.reject(new Error('name must be at most 100 characters'));
      }
    }
    return agentContext().then(function (context) {
      var nameLine = '';
      if (recipient) {
        if (audience === 'dad') {
          nameLine = "Dad's name is " + recipient + "; you may greet him by name.\n";
        } else {
          nameLine = "The reader's name is " + recipient + "; you may use it naturally.\n";
        }
      }
      var prompt =
        "You write short family updates for Second Look, which checks on Dad's rooms. " +
        "You are given RECORDS ONLY (words, never pictures).\n\n" +
        "AUDIENCE: " + UPDATE_RULES[audience] + "\n" +
        nameLine +
        "RULES \u2014 follow all of them:\n" +
        "1. Use ONLY what the records say. Never invent changes, people or plans.\n" +
        "2. If the records show no changes at all, simply say things look as they were.\n" +
        "3. Plain, warm language. No medical advice. Never claim something is reachable, " +
        "safe or unsafe beyond what was seen.\n" +
        "4. At most 110 words. Plain text only \u2014 no JSON, no markdown, no bullet symbols " +
        "unless a short list genuinely helps (nearby audience only).\n\n" +
        "RECORDS (JSON):\n" + JSON.stringify(context);
      return sparkText(prompt, 2500).then(function (out) {
        var cleaned = String(out.text || '').trim();
        if (cleaned.indexOf('```') === 0) {
          cleaned = cleaned.replace(/`/g, '').trim();
          if (cleaned.toLowerCase().indexOf('json') === 0) { cleaned = cleaned.slice(4).trim(); }
          try {
            var parsed = JSON.parse(cleaned);
            if (parsed && typeof parsed === 'object') {
              cleaned = String(parsed.text || parsed.answer || cleaned).trim();
            }
          } catch (e) { /* keep as plain text */ }
        }
        cleaned = truncateWords(cleaned, 110);
        return { text: cleaned, model: SPARK_MODEL, latency_s: out.latency_s };
      });
    });
  }

  // -------------------------------------------------------------------------
  // HTTP-ish helpers for the fetch shim
  // -------------------------------------------------------------------------
  function jsonResponse(obj, status) {
    var bodyText;
    try { bodyText = JSON.stringify(obj == null ? {} : obj); } catch (e) { bodyText = '{}'; }
    return new Response(bodyText, {
      status: status || 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  function textResponse(text, status, contentType) {
    return new Response(String(text == null ? '' : text), {
      status: status || 200,
      headers: { 'Content-Type': contentType || 'text/plain; charset=utf-8' }
    });
  }

  function errorResponse(message, status) {
    return jsonResponse({ error: String(message || 'Something went wrong.') }, status || 400);
  }

  function readBody(init, input) {
    // Returns a promise of {json, form, text} best-effort.
    var result = { json: null, form: null, text: '' };
    var body = init && init.body !== undefined ? init.body : null;
    if (body == null && input && typeof Request !== 'undefined' && input instanceof Request) {
      return input.clone().text().then(function (txt) {
        result.text = txt || '';
        try { result.json = JSON.parse(result.text); } catch (e) { /* not json */ }
        return result;
      }, function () { return result; });
    }
    if (typeof FormData !== 'undefined' && body instanceof FormData) {
      result.form = body;
      return Promise.resolve(result);
    }
    if (typeof body === 'string') {
      result.text = body;
      try { result.json = JSON.parse(body); } catch (e) { /* not json */ }
      return Promise.resolve(result);
    }
    if (body && typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams) {
      result.text = body.toString();
      var form = new FormData();
      body.forEach(function (v, k) { form.append(k, v); });
      result.form = form;
      return Promise.resolve(result);
    }
    if (body && typeof Blob !== 'undefined' && body instanceof Blob) {
      return body.text().then(function (txt) {
        result.text = txt || '';
        try { result.json = JSON.parse(result.text); } catch (e) { /* ignore */ }
        return result;
      }, function () { return result; });
    }
    if (body && typeof body === 'object') {
      result.json = body;
      try { result.text = JSON.stringify(body); } catch (e) { /* ignore */ }
      return Promise.resolve(result);
    }
    return Promise.resolve(result);
  }

  function formGet(form, names) {
    if (!form) { return null; }
    for (var i = 0; i < names.length; i++) {
      try {
        var v = form.get(names[i]);
        if (v != null && String(v).trim() !== '') { return v; }
      } catch (e) { /* ignore */ }
    }
    return null;
  }

  function formGetAll(form, name) {
    if (!form) { return []; }
    try {
      var all = form.getAll(name);
      return all || [];
    } catch (e) { return []; }
  }

  function parseWatchlist(raw) {
    var items = [];
    function push(v) {
      if (v == null) { return; }
      if (Array.isArray(v)) { v.forEach(push); return; }
      if (typeof v === 'object') {
        var c = v.concept || v.name || v.item;
        if (c) { push(c); }
        return;
      }
      String(v).split(/[,\n;]/).forEach(function (piece) {
        var t = piece.trim();
        if (t) { items.push(t); }
      });
    }
    if (Array.isArray(raw)) { raw.forEach(push); }
    else if (typeof raw === 'string') {
      var trimmed = raw.trim();
      if (trimmed.charAt(0) === '[') {
        try { push(JSON.parse(trimmed)); } catch (e) { push(raw); }
      } else { push(raw); }
    } else if (raw != null) { push(raw); }
    var seen = {};
    return items.filter(function (item) {
      var key = item.toLowerCase();
      if (seen[key]) { return false; }
      seen[key] = true;
      return true;
    });
  }

  function watchlistFrom(form, json) {
    var items = [];
    if (form) {
      ['watchlist', 'watch', 'watch_list', 'items'].forEach(function (name) {
        formGetAll(form, name).forEach(function (v) { items = items.concat(parseWatchlist(v)); });
      });
    }
    if (json && typeof json === 'object') {
      ['watchlist', 'watch', 'watch_list', 'items'].forEach(function (name) {
        if (json[name] != null) { items = items.concat(parseWatchlist(json[name])); }
      });
    }
    return parseWatchlist(items);
  }

  function fileToDataUrl(file) {
    return new Promise(function (resolve, reject) {
      if (typeof file === 'string') { resolve(file); return; }
      if (!file || typeof FileReader === 'undefined') {
        reject(new Error('Could not read that image.'));
        return;
      }
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result || '')); };
      reader.onerror = function () { reject(new Error('Could not read that image.')); };
      try { reader.readAsDataURL(file); } catch (e) { reject(e); }
    });
  }

  function icsEscape(s) {
    return String(s == null ? '' : s)
      .replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,')
      .replace(/\r?\n/g, '\\n');
  }

  function icsDate(d) {
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    return d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) +
      'T' + pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + '00Z';
  }

  function buildReminderIcs(searchParams) {
    var room = 'the room';
    var who = '';
    try {
      room = (searchParams && (searchParams.get('room') || searchParams.get('name'))) || room;
      who = (searchParams && (searchParams.get('for') || searchParams.get('filmed_by'))) || '';
    } catch (e) { /* defaults fine */ }
    var start = new Date(Date.now() + 24 * 60 * 60 * 1000);
    start.setUTCHours(10, 0, 0, 0);
    var end = new Date(start.getTime() + 30 * 60 * 1000);
    var summary = 'Film a Second Look check of ' + room;
    var description = 'Take a short (under 30s) walkthrough video of ' + room +
      ' for Second Look.' + (who ? ' Filmed by: ' + who + '.' : '') +
      ' Keep it slow and steady so the objects can be checked.';
    return [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//Second Look//Static//EN',
      'CALSCALE:GREGORIAN',
      'BEGIN:VEVENT',
      'UID:second-look-' + Date.now() + '@splatdiff.static',
      'DTSTAMP:' + icsDate(new Date()),
      'DTSTART:' + icsDate(start),
      'DTEND:' + icsDate(end),
      'SUMMARY:' + icsEscape(summary),
      'DESCRIPTION:' + icsEscape(description),
      'END:VEVENT',
      'END:VCALENDAR',
      ''
    ].join('\r\n');
  }

  // -------------------------------------------------------------------------
  // Local browser-pipeline runs
  // -------------------------------------------------------------------------
  function emitRunEvent(run, event) {
    if (!run || !event || typeof event !== 'object') { return; }
    run.events.push(event);
    if (event.stage === 'result' && event.result) {
      run.result = event.result;
      run.status = 'done';
      registerLocalResult(event.result);
    }
    if (event.stage === 'done' || event.stage === 'result') {
      if (event.result && !run.result) { run.result = event.result; }
      run.status = 'done';
      if (run.result) { registerLocalResult(run.result); }
    }
    if (event.stage === 'error') {
      run.status = 'error';
      run.error = event.message || event.error || 'The check failed.';
    }
    var listeners = run.listeners.slice();
    for (var i = 0; i < listeners.length; i++) {
      try { listeners[i]._dispatch(event); } catch (e) { /* ignore */ }
    }
    if (run.status === 'done' || run.status === 'error') {
      for (var j = 0; j < listeners.length; j++) {
        try { listeners[j]._scheduleClose(400); } catch (e) { /* ignore */ }
      }
    }
  }

  function findFormFiles(form) {
    var before = null;
    var after = null;
    var others = [];
    if (!form) { return { before: before, after: after }; }
    try {
      form.forEach(function (value, key) {
        var isFile = typeof Blob !== 'undefined' && value instanceof Blob &&
          !(typeof File !== 'undefined' && value instanceof File && value.size === 0 && !value.name);
        var low = String(key).toLowerCase();
        if (value && typeof value === 'object' && typeof Blob !== 'undefined' && value instanceof Blob) {
          if (!isFile && value.size === 0) { return; }
          if (low.indexOf('before') !== -1 && !before) { before = value; return; }
          if (low.indexOf('after') !== -1 && !after) { after = value; return; }
          others.push(value);
        }
      });
    } catch (e) { /* fall through */ }
    if (!before && others.length) { before = others.shift(); }
    if (!after && others.length) { after = others.shift(); }
    return { before: before, after: after };
  }

  function startLocalRun(body) {
    var form = body.form;
    var json = body.json || {};
    var files = findFormFiles(form);
    var beforeFile = files.before || json.before_file || json.before || null;
    var afterFile = files.after || json.after_file || json.after || null;
    var watchlist = watchlistFrom(form, json);
    var roomVal = formGet(form, ['room', 'room_name']) || json.room || null;
    var filmedByVal = formGet(form, ['filmed_by', 'filmedBy', 'filmedby', 'by']) || json.filmed_by || json.filmedBy || null;
    var runId = 'local-' + Date.now();
    var run = {
      run_id: runId,
      status: 'running',
      events: [],
      result: null,
      error: null,
      listeners: [],
      started_at: nowIso()
    };
    localRuns[runId] = run;

    // Attach any EventSources that arrived before the run existed.
    var waiting = pendingRunListeners[runId] || [];
    delete pendingRunListeners[runId];
    waiting.forEach(function (es) { run.listeners.push(es); es._run = run; });

    var gate = getKey() ? Promise.resolve(getKey()) : requireKey('Running a check on your own videos needs a Meta API key.');
    gate.then(function () {
      if (!window.SLBrowserPipeline || typeof window.SLBrowserPipeline.run !== 'function') {
        emitRunEvent(run, {
          stage: 'error',
          message: 'The in-browser checker did not load, so this check cannot run here.'
        });
        return;
      }
      var opts = {
        beforeFile: beforeFile,
        afterFile: afterFile,
        watchlist: watchlist,
        room: roomVal ? String(roomVal) : undefined,
        filmedBy: filmedByVal ? String(filmedByVal) : undefined,
        onEvent: function (event) { emitRunEvent(run, event); }
      };
      var promise;
      try {
        promise = window.SLBrowserPipeline.run(opts);
      } catch (e) {
        emitRunEvent(run, { stage: 'error', message: 'The check could not start in this browser.' });
        return;
      }
      Promise.resolve(promise).then(function (result) {
        if (result && typeof result === 'object') {
          if (!result.run_id) {
            try { result.run_id = runId; } catch (e) { /* ignore */ }
          }
          run.result = result;
          run.status = 'done';
          registerLocalResult(result);
          // Ensure listeners see a terminal result event even if the
          // pipeline only resolved (its own events normally include it).
          var hasTerminal = run.events.some(function (ev) {
            return ev && (ev.stage === 'result' || ev.stage === 'done');
          });
          if (!hasTerminal) {
            emitRunEvent(run, { stage: 'result', result: result });
          } else {
            var ls = run.listeners.slice();
            for (var i = 0; i < ls.length; i++) {
              try { ls[i]._scheduleClose(400); } catch (e) { /* ignore */ }
            }
          }
        } else if (run.status === 'running') {
          run.status = 'done';
        }
      }, function () {
        if (run.status === 'running') {
          emitRunEvent(run, { stage: 'error', message: 'The check failed. Please try again.' });
        }
      });
    }, function () {
      emitRunEvent(run, { stage: 'error', message: 'A Meta API key is needed to run a check.' });
    });

    return runId;
  }

  function handlePostRuns(body) {
    var form = body.form;
    var json = body.json || {};
    var sampleVal = formGet(form, ['sample']) || json.sample;
    if (String(sampleVal) === '1' || sampleVal === true) {
      return jsonResponse({ run_id: 'replay' }, 200);
    }
    if (!form && !json) {
      return errorResponse('Expected the before/after videos as form data.', 400);
    }
    // Key is required before we claim a run exists.
    var gate = getKey() ? Promise.resolve(getKey()) : requireKey('Running a check on your own videos needs a Meta API key.');
    return gate.then(function () {
      var runId = startLocalRun(body);
      return jsonResponse({ run_id: runId }, 200);
    }, function () {
      return errorResponse('A Meta API key is needed to run a check.', 401);
    });
  }

  // -------------------------------------------------------------------------
  // Glasses frame: SAM per watchlist item (max 4 concurrent) + whisper
  // -------------------------------------------------------------------------
  function whisperFor(concept, det) {
    var box = det.box || [];
    var w = det.w || box[2] || 0;
    var h = det.h || box[3] || 0;
    var direction = 'straight ahead';
    var distance = 'across the room';
    if (w > 0 && box.length === 4) {
      var cx = ((box[0] + box[2]) / 2) / w;
      if (cx < 1 / 3) { direction = 'on your left'; }
      else if (cx > 2 / 3) { direction = 'on your right'; }
    }
    if (h > 0 && box.length === 4) {
      var frac = (box[3] - box[1]) / h;
      if (frac > 0.55) { distance = 'close'; }
      else if (frac > 0.25) { distance = 'a few steps away'; }
      else { distance = 'across the room'; }
    }
    return concept + ': ' + direction + ', ' + distance;
  }

  function handleGlassesFrame(body) {
    var form = body.form;
    var json = body.json || {};
    var started = Date.now();
    var imageVal = form ? formGet(form, ['image', 'frame', 'photo', 'file']) : null;
    if (!imageVal && form) {
      form.forEach(function (value) {
        if (!imageVal && value && typeof Blob !== 'undefined' && value instanceof Blob) { imageVal = value; }
      });
    }
    if (!imageVal && json.image) { imageVal = json.image; }
    var watchlist = watchlistFrom(form, json);
    if (!imageVal) { return errorResponse('image is required', 400); }
    if (!watchlist.length) { return errorResponse('watchlist is required', 400); }

    var gate = getKey() ? Promise.resolve(getKey()) : requireKey('Live glasses checks need a Meta API key.');
    return gate.then(function () {
      return fileToDataUrl(imageVal);
    }).then(function (dataUrl) {
      return mapLimit(watchlist, 4, function (concept) {
        return samImage(dataUrl, concept).then(function (dets) {
          var best = null;
          (dets || []).forEach(function (d) {
            if (!best || (d.c || 0) > (best.c || 0)) { best = d; }
          });
          if (!best) {
            return {
              concept: concept, item: concept, name: concept,
              found: false, box: null, c: 0, confidence: 0, w: 0, h: 0
            };
          }
          return {
            concept: concept, item: concept, name: concept,
            found: true, box: best.box, c: best.c, confidence: best.c,
            w: best.w, h: best.h
          };
        }, function () {
          return {
            concept: concept, item: concept, name: concept,
            found: false, box: null, c: 0, confidence: 0, w: 0, h: 0
          };
        });
      });
    }).then(function (detections) {
      var sentences = [];
      detections.forEach(function (det) {
        if (det && det.found) { sentences.push(whisperFor(det.concept, det)); }
      });
      var whisper = sentences.length
        ? sentences.join('; ') + '.'
        : "I don't see those things in this frame.";
      return jsonResponse({
        detections: detections,
        whisper: whisper,
        latency_s: Math.round((Date.now() - started) / 10) / 100
      }, 200);
    }, function () {
      return errorResponse('A Meta API key is needed for live glasses checks.', 401);
    });
  }

  function handleGlassesFall(body) {
    var json = body.json || {};
    var form = body.form;
    function field(name) {
      var v = formGet(form, [name]) || json[name];
      return v == null ? null : String(v);
    }
    var room = field('room');
    var entry = addLocalFeedEntry({
      type: 'fall',
      kind: 'fall',
      event: 'fall',
      room: room,
      ts: field('ts') || nowIso(),
      message: field('message') || 'A possible fall was reported by the glasses demo.',
      note: field('note') || undefined,
      source: 'glasses'
    });
    return jsonResponse({ ok: true, entry: entry }, 200);
  }

  function handleVoiceNote(body) {
    var form = body.form;
    var json = body.json || {};
    var started = Date.now();
    var audioVal = form ? formGet(form, ['audio', 'voice', 'file', 'recording']) : null;
    if (!audioVal && form) {
      form.forEach(function (value) {
        if (!audioVal && value && typeof Blob !== 'undefined' && value instanceof Blob) { audioVal = value; }
      });
    }
    if (!audioVal) { return errorResponse('audio is required', 400); }

    var gate = getKey() ? Promise.resolve(getKey()) : requireKey('Voice notes need a Meta API key.');
    return gate.then(function () {
      return toWav16k(audioVal);
    }).then(function (wav) {
      return transcribe(wav);
    }).then(function (transcriptText) {
      var transcript = String(transcriptText || '').trim();
      // The transcript itself is sent only to Spark for extraction, never stored.
      var prompt =
        "You extract structured notes from a short voice note left after filming a room check " +
        "for Second Look. Use ONLY words in the transcript. Never invent items.\n\n" +
        "Return STRICT JSON only, no markdown fences: " +
        "{\"items\": [\"<thing mentioned as moved, added, removed or to watch>\"], " +
        "\"intentional\": \"<anything the speaker says was deliberate, in their words, or null>\"}.\n\n" +
        "TRANSCRIPT:\n" + transcript;
      return sparkText(prompt, 1500).then(function (out) {
        var items = [];
        var intentional = null;
        try {
          var parsed = parseJsonLoose(out.text);
          if (parsed && typeof parsed === 'object') {
            if (Array.isArray(parsed.items)) {
              parsed.items.forEach(function (it) {
                var s = safeStr(it, 120);
                if (s) { items.push(s); }
              });
            }
            intentional = safeStr(parsed.intentional, 400);
          }
        } catch (e) { /* empty extraction is fine */ }
        return jsonResponse({
          transcript: transcript,
          items: items,
          intentional: intentional,
          latency_s: Math.round((Date.now() - started) / 10) / 100
        }, 200);
      });
    }, function () {
      return errorResponse('A Meta API key is needed for voice notes.', 401);
    }).catch(function () {
      return errorResponse('That voice note could not be processed.', 502);
    });
  }

  // -------------------------------------------------------------------------
  // Fetch shim routing
  // -------------------------------------------------------------------------
  function handleApi(path, searchParams, method, body) {
    var seg;
    if (method === 'GET' && path === '/api/sample') {
      return bakedOr('sample.json', {}).then(function (d) { return jsonResponse(d, 200); });
    }
    if (method === 'GET' && path === '/api/history') {
      return bakedOr('history.json', []).then(function (d) { return jsonResponse(mergedHistory(d), 200); });
    }
    if (method === 'GET' && path.indexOf('/api/history/') === 0) {
      seg = decodeURIComponent(path.slice('/api/history/'.length));
      if (localResultsById[seg]) { return jsonResponse(localResultsById[seg], 200); }
      return bakedOr('history/' + seg + '.json', null).then(function (d) {
        if (d == null) { return errorResponse('That check was not found.', 404); }
        return jsonResponse(d, 200);
      });
    }
    if (method === 'GET' && path === '/api/rooms') {
      return bakedOr('rooms.json', []).then(function (d) { return jsonResponse(d, 200); });
    }
    if (method === 'GET' && path === '/api/feed') {
      return bakedOr('feed.json', []).then(function (d) { return jsonResponse(mergedFeed(d), 200); });
    }
    if (method === 'POST' && path === '/api/runs') {
      return handlePostRuns(body);
    }
    if (method === 'GET' && path.indexOf('/api/runs/') === 0) {
      seg = decodeURIComponent(path.slice('/api/runs/'.length));
      if (seg === 'replay') {
        return bakedOr('replay.json', null).then(function (replay) {
          var result = null;
          var events = [];
          if (replay && Array.isArray(replay.events)) {
            events = replay.events;
            for (var i = events.length - 1; i >= 0; i--) {
              if (events[i] && events[i].stage === 'result' && events[i].result) { result = events[i].result; break; }
            }
          }
          return jsonResponse({ run_id: 'replay', status: result ? 'done' : 'running', events: events, result: result }, 200);
        });
      }
      var run = localRuns[seg];
      if (!run) { return errorResponse('That run was not found.', 404); }
      return jsonResponse({
        run_id: run.run_id,
        status: run.status,
        events: run.events,
        result: run.result || null,
        error: run.error || null
      }, 200);
    }
    if (method === 'POST' && path === '/api/ask') {
      var question = body.json && body.json.question != null
        ? body.json.question
        : formGet(body.form, ['question']);
      if (question == null || String(question).trim() === '') {
        return errorResponse('question is required', 400);
      }
      if (String(question).length > 500) {
        return errorResponse('question must be at most 500 characters', 400);
      }
      return requireKey('Answering family questions needs a Meta API key.').then(function () {
        return agentAsk(String(question));
      }).then(function (out) {
        return jsonResponse(out, 200);
      }, function () {
        return errorResponse('A Meta API key is needed to answer questions.', 401);
      });
    }
    if (method === 'POST' && path === '/api/update') {
      var kind = body.json && (body.json['for'] != null ? body.json['for'] : body.json.kind);
      if (kind == null) { kind = formGet(body.form, ['for', 'kind', 'audience']); }
      var name = body.json ? body.json.name : null;
      if (name == null) { name = formGet(body.form, ['name']); }
      if (kind == null || !UPDATE_RULES[String(kind).trim().toLowerCase()]) {
        return errorResponse('for must be one of: nearby, far, dad', 400);
      }
      return requireKey('Writing family updates needs a Meta API key.').then(function () {
        return agentUpdate(String(kind), name == null ? null : String(name));
      }).then(function (out) {
        return jsonResponse(out, 200);
      }, function () {
        return errorResponse('A Meta API key is needed to write updates.', 401);
      });
    }
    if (method === 'POST' && path === '/api/glasses/frame') {
      return handleGlassesFrame(body);
    }
    if (method === 'POST' && path === '/api/glasses/fall') {
      return handleGlassesFall(body);
    }
    if (method === 'POST' && path === '/api/voice-note') {
      return handleVoiceNote(body);
    }
    if (method === 'POST' && path === '/api/baseline') {
      return jsonResponse({ error: FRIENDLY_501 }, 501);
    }
    if (method === 'DELETE' && (path === '/api/history' || path.indexOf('/api/history/') === 0)) {
      return jsonResponse({ error: FRIENDLY_501 }, 501);
    }
    if (path === '/api/reminder.ics') {
      return textResponse(buildReminderIcs(searchParams), 200, 'text/calendar; charset=utf-8');
    }
    return null; // not ours
  }

  function resolveRequestUrl(input) {
    try {
      if (typeof input === 'string') { return new URL(input, window.location.href); }
      if (input && typeof input.url === 'string') { return new URL(input.url, window.location.href); }
      if (input && input.href) { return new URL(input.href, window.location.href); }
    } catch (e) { /* ignore */ }
    return null;
  }

  function stripBase(pathname) {
    if (BASE && (pathname === BASE || pathname.indexOf(BASE + '/') === 0)) {
      return pathname.slice(BASE.length) || '/';
    }
    return pathname;
  }

  function installFetchShim() {
    if (!nativeFetch) { return; }
    window.fetch = function (input, init) {
      var url = resolveRequestUrl(input);
      if (!url) { return nativeFetch(input, init); }
      var sameOrigin = url.origin === window.location.origin;
      if (!sameOrigin) { return nativeFetch(input, init); }

      var apiPath = stripBase(url.pathname);
      var method = 'GET';
      try {
        method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      } catch (e) { /* default GET */ }

      if (apiPath.indexOf('/api/') === 0 || apiPath === '/api') {
        return readBody(init, input).then(function (body) {
          var handled;
          try {
            handled = handleApi(apiPath, url.searchParams, method, body);
          } catch (e) {
            return errorResponse('Something went wrong handling that request.', 500);
          }
          if (handled && typeof handled.then === 'function') {
            return handled.then(function (resp) {
              return resp || errorResponse('Not available in the static demo.', 404);
            }, function () {
              return errorResponse('Something went wrong handling that request.', 500);
            });
          }
          return handled || errorResponse('Not available in the static demo.', 404);
        });
      }

      // Same-origin absolute path that is not already under BASE: prefix it.
      if (typeof input === 'string' && input.charAt(0) === '/' && input.indexOf('//') !== 0 &&
          url.pathname !== apiPath) {
        // Already had BASE stripped for the API check but was not /api: keep as-is.
        return nativeFetch(input, init);
      }
      if (typeof input === 'string' && input.charAt(0) === '/' && input.indexOf('//') !== 0 &&
          !(BASE && (url.pathname === BASE || url.pathname.indexOf(BASE + '/') === 0))) {
        return nativeFetch(BASE + input, init);
      }
      return nativeFetch(input, init);
    };
  }

  // -------------------------------------------------------------------------
  // EventSource shim
  // -------------------------------------------------------------------------
  function FakeEventSource(url) {
    var self = this;
    this.url = String(url == null ? '' : url);
    this.readyState = 0; // CONNECTING
    this.onmessage = null;
    this.onerror = null;
    this.onopen = null;
    this._listeners = { message: [], error: [], open: [] };
    this._closed = false;
    this._timers = [];
    this._run = null;

    var parsed = null;
    try { parsed = new URL(this.url, window.location.href); } catch (e) { /* ignore */ }
    var path = parsed ? stripBase(parsed.pathname) : '';

    if (path === '/api/runs/replay/events') {
      this._startReplay();
    } else if (path.indexOf('/api/runs/') === 0 && path.slice(-7) === '/events') {
      var runId = decodeURIComponent(path.slice('/api/runs/'.length, path.length - '/events'.length));
      this._startLocalRun(runId);
    } else if (path === '/api/feed/events') {
      this._startFeed();
    } else if (NativeEventSource) {
      // Not one of ours: behave like a real EventSource.
      var real = new NativeEventSource(url);
      this._real = real;
      real.onmessage = function (ev) { self._emit('message', ev); };
      real.onerror = function (ev) { self._emit('error', ev); };
      real.onopen = function (ev) { self.readyState = 1; self._emit('open', ev); };
    } else {
      this._later(function () { self._emitError(); });
    }
  }

  FakeEventSource.prototype._later = function (fn, delay) {
    var self = this;
    var id = setTimeout(function () {
      if (!self._closed) { try { fn(); } catch (e) { /* ignore */ } }
    }, delay || 0);
    this._timers.push(id);
    return id;
  };

  FakeEventSource.prototype._emit = function (type, event) {
    if (this._closed && type !== 'error') { return; }
    var ev = event || { type: type, data: '' };
    if (typeof ev.data !== 'string') {
      try { ev = { type: type, data: JSON.stringify(ev.data == null ? {} : ev.data) }; }
      catch (e) { ev = { type: type, data: '{}' }; }
    }
    if (type === 'message' && typeof this.onmessage === 'function') {
      try { this.onmessage(ev); } catch (e) { /* listener errors are theirs */ }
    }
    if (type === 'error' && typeof this.onerror === 'function') {
      try { this.onerror(ev); } catch (e) { /* ignore */ }
    }
    if (type === 'open' && typeof this.onopen === 'function') {
      try { this.onopen(ev); } catch (e) { /* ignore */ }
    }
    var list = this._listeners[type] || [];
    for (var i = 0; i < list.length; i++) {
      try { list[i].call(this, ev); } catch (e) { /* ignore */ }
    }
  };

  FakeEventSource.prototype._dispatch = function (payload) {
    this._emit('message', { type: 'message', data: payload });
  };

  FakeEventSource.prototype._emitError = function () {
    if (this._closed) { return; }
    this.readyState = 2;
    this._emit('error', { type: 'error', data: '' });
  };

  FakeEventSource.prototype._scheduleClose = function (delay) {
    var self = this;
    this._later(function () { self.close(); }, delay || 0);
  };

  FakeEventSource.prototype._startReplay = function () {
    var self = this;
    this._later(function () {
      self.readyState = 1;
      self._emit('open', { type: 'open', data: '' });
      bakedOr('replay.json', null).then(function (replay) {
        if (self._closed) { return; }
        var events = replay && Array.isArray(replay.events) ? replay.events : [];
        if (!events.length) { self._emitError(); self.close(); return; }
        events.forEach(function (event) {
          var t = 0;
          try { t = Number(event && event.t) || 0; } catch (e) { t = 0; }
          var delay = Math.max(0, (t * 1000) / 1.5);
          self._later(function () { self._dispatch(event); }, delay);
        });
        var lastT = 0;
        try { lastT = Number(events[events.length - 1].t) || 0; } catch (e) { /* ignore */ }
        self._later(function () { self.close(); }, Math.max(0, (lastT * 1000) / 1.5) + 300);
      });
    }, 0);
  };

  FakeEventSource.prototype._startLocalRun = function (runId) {
    var self = this;
    this._later(function () {
      self.readyState = 1;
      self._emit('open', { type: 'open', data: '' });
      var run = localRuns[runId];
      if (!run) {
        if (!pendingRunListeners[runId]) { pendingRunListeners[runId] = []; }
        pendingRunListeners[runId].push(self);
        return;
      }
      self._run = run;
      run.listeners.push(self);
      // Replay everything emitted so far, then live events follow.
      var existing = run.events.slice();
      existing.forEach(function (event) { self._dispatch(event); });
      if (run.status === 'done' || run.status === 'error') {
        self._scheduleClose(400);
      }
    }, 0);
  };

  FakeEventSource.prototype._startFeed = function () {
    var self = this;
    feedListeners.push(self);
    this._later(function () {
      self.readyState = 1;
      self._emit('open', { type: 'open', data: '' });
      Promise.all([
        bakedOr('feed.json', []),
        bakedOr('rooms.json', [])
      ]).then(function (pair) {
        if (self._closed) { return; }
        var entries = feedEntriesOf(pair[0]).concat(localFeedEntries);
        self._dispatch({ type: 'snapshot', entries: entries, rooms: pair[1] });
        // Any local entries that arrived while loading were already
        // dispatched live by addLocalFeedEntry; nothing else to do.
      });
    }, 0);
  };

  FakeEventSource.prototype.addEventListener = function (type, listener) {
    if (typeof listener !== 'function') { return; }
    if (!this._listeners[type]) { this._listeners[type] = []; }
    this._listeners[type].push(listener);
    if (this._real && this._real.addEventListener) {
      try { this._real.addEventListener(type, listener); } catch (e) { /* ignore */ }
    }
  };

  FakeEventSource.prototype.removeEventListener = function (type, listener) {
    var list = this._listeners[type] || [];
    this._listeners[type] = list.filter(function (fn) { return fn !== listener; });
    if (this._real && this._real.removeEventListener) {
      try { this._real.removeEventListener(type, listener); } catch (e) { /* ignore */ }
    }
  };

  FakeEventSource.prototype.close = function () {
    if (this._closed) { return; }
    this._closed = true;
    this.readyState = 2;
    for (var i = 0; i < this._timers.length; i++) {
      try { clearTimeout(this._timers[i]); } catch (e) { /* ignore */ }
    }
    this._timers = [];
    if (this._real) { try { this._real.close(); } catch (e) { /* ignore */ } }
    if (this._run) {
      this._run.listeners = this._run.listeners.filter(function (es) { return es !== this; }, this);
      // The filter callback needs `this`; do it plainly below instead.
    }
    var self = this;
    if (self._run) {
      self._run.listeners = self._run.listeners.filter(function (es) { return es !== self; });
      self._run = null;
    }
    feedListeners = feedListeners.filter(function (es) { return es !== self; });
    Object.keys(pendingRunListeners).forEach(function (id) {
      pendingRunListeners[id] = pendingRunListeners[id].filter(function (es) { return es !== self; });
    });
  };
  FakeEventSource.CONNECTING = 0;
  FakeEventSource.OPEN = 1;
  FakeEventSource.CLOSED = 2;

  function installEventSourceShim() {
    try { window.EventSource = FakeEventSource; } catch (e) { /* ignore */ }
  }

  // -------------------------------------------------------------------------
  // Banner
  // -------------------------------------------------------------------------
  function insertBanner() {
    try {
      if (!document.body || document.getElementById('sl-static-banner')) { return; }
      injectCss();
      var banner = document.createElement('div');
      banner.id = 'sl-static-banner';
      banner.className = 'sl-banner';
      banner.setAttribute('role', 'note');
      var text = document.createTextNode(
        'Static demo on GitHub Pages \u00B7 sample checks replay a real recorded run \u00B7 ' +
        'your own videos use your Meta API key in this tab only \u00B7 '
      );
      var link = document.createElement('a');
      link.href = GITHUB_URL;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Run it yourself \u2192';
      banner.appendChild(text);
      banner.appendChild(link);
      document.body.insertBefore(banner, document.body.firstChild);
      showKeyChip();
    } catch (e) { /* banner is cosmetic */ }
  }

  // -------------------------------------------------------------------------
  // Public surface
  // -------------------------------------------------------------------------
  var SL = {
    base: BASE,
    isStatic: true,
    key: {
      get: getKey,
      clear: clearKey,
      require: requireKey
    },
    meta: {
      responses: responses,
      text: extractText,
      json: parseJsonLoose,
      samImage: samImage,
      transcribe: transcribe
    },
    audio: {
      toWav16k: toWav16k
    },
    // Exposed for the browser pipeline / debugging without the key.
    _parseSamText: parseSamText,
    _stripKeys: stripKeys,
    _addFeedEntry: addLocalFeedEntry,
    _registerResult: registerLocalResult
  };
  window.SL = SL;

  installFetchShim();
  installEventSourceShim();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', insertBanner);
  } else {
    insertBanner();
  }
})();
