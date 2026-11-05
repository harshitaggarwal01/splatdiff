"use strict";
/* Family feed: text-only live timeline from /api/feed/events (SSE).
   No images are ever requested or rendered. Browser notifications are
   requested only from the explicit "Notify me on this device" click. */

(function () {
  var STATUS_WORDS = {
    all_clear: "All watched items seen where they were",
    needs_attention: "Needs attention",
    coverage_gap: "Walkthroughs didn't cover the same corners — re-film"
  };
  var CHANGE_WORDS = {
    added: "added",
    removed: "removed",
    moved: "moved",
    on_floor: "on the floor",
    missing: "not seen",
    not_seen: "not seen",
    unchanged: "seen where it was"
  };

  var roomList = document.getElementById("room-list");
  var feedList = document.getElementById("feed-list");
  var feedEmpty = document.getElementById("feed-empty");
  var liveIndicator = document.getElementById("live-indicator");
  var notifyBtn = document.getElementById("notify-btn");
  var notifyNote = document.getElementById("notify-note");
  var baseTitle = document.title;

  /* Ask suggestion chips: with 4+ chips, the walker question leads;
     with only three, keep the three general chips from the markup. */
  var suggestionChips = document.querySelectorAll(".chip[data-question]");
  if (suggestionChips.length >= 4) {
    suggestionChips[0].setAttribute("data-question", "Where was his walker last seen?");
    suggestionChips[0].textContent = "Where was his walker last seen?";
  }

  var entriesById = Object.create(null);
  var entryOrder = [];
  var roomsByName = Object.create(null);
  var attentionSinceLoad = 0;
  var notificationsEnabled = false;
  var fallbackTimer = null;

  function text(value) { return value == null ? "" : String(value); }

  function capitalise(value) {
    var s = text(value);
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  }

  function trendText(value) {
    if (typeof value === "string") return value.trim();
    if (value && typeof value === "object") {
      var t = value.trend || value.sentence || value.text || value.summary || value.line || "";
      return typeof t === "string" ? t.trim() : "";
    }
    return "";
  }

  function el(tag, className, value) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (value != null) node.textContent = value;
    return node;
  }

  function entryKey(entry) {
    if (!entry || typeof entry !== "object") return "";
    if (entry.id) return "id:" + entry.id;
    return "run:" + text(entry.run_id) + "|" + text(entry.ts);
  }

  function formatDate(value) {
    if (!value) return "";
    var d = new Date(value);
    if (isNaN(d.getTime())) return text(value);
    try {
      return d.toLocaleString(undefined, {
        weekday: "short", day: "numeric", month: "short",
        hour: "numeric", minute: "2-digit"
      });
    } catch (e) {
      return d.toString();
    }
  }

  function formatDay(value) {
    if (!value) return "";
    var d = new Date(value);
    if (isNaN(d.getTime())) return text(value);
    try {
      return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
    } catch (e) {
      return d.toString();
    }
  }

  /* 'Wed, Nov 4, 7:20 PM' */
  function formatCheckDate(value) {
    if (!value) return "";
    var d = new Date(value);
    if (isNaN(d.getTime())) return text(value);
    try {
      return d.toLocaleString(undefined, {
        weekday: "short", month: "short", day: "numeric",
        hour: "numeric", minute: "2-digit"
      });
    } catch (e) {
      return formatDate(value);
    }
  }

  function isSimulatedText(value) {
    return /\(simulated\)/i.test(text(value)) || /glasses\s*\(simulated\)/i.test(text(value));
  }

  function cleanSimulatedConcept(value) {
    return text(value).replace(/\s*\(simulated\)\s*/gi, " ").trim();
  }

  function simulationTag() {
    var tag = el("span", "simulation-tag mono", "simulation");
    return tag;
  }

  function statusLine(status) {
    var wrap = el("span", "status-line status-" + (STATUS_WORDS[status] ? status : "unknown"));
    wrap.appendChild(el("span", "status-dot"));
    wrap.setAttribute("aria-hidden", "false");
    wrap.appendChild(el("span", "", capitalise(STATUS_WORDS[status] || "Checked")));
    return wrap;
  }

  function dueText(room) {
    if (!room || !room.due) return "";
    var days = room.days_since;
    if (days == null && room.last_check && room.last_check.date) {
      var then = new Date(room.last_check.date).getTime();
      if (!isNaN(then)) days = Math.max(0, Math.floor((Date.now() - then) / 86400000));
    }
    if (days == null || isNaN(Number(days))) return "Due for a re-film";
    return "Due for a re-film (" + Number(days) + " days)";
  }

  /* ---------------- Rooms ---------------- */

  function renderRooms(rooms) {
    if (!Array.isArray(rooms)) return;
    rooms.forEach(function (room) {
      if (room && room.room) roomsByName[room.room] = room;
      else if (room && room.name) roomsByName[room.name] = room;
    });
    roomList.textContent = "";
    var names = Object.keys(roomsByName);
    if (!names.length) {
      roomList.appendChild(el("p", "family-muted", "No rooms checked yet."));
      return;
    }
    names.sort(function (a, b) { return a.localeCompare(b); });
    names.forEach(function (name) {
      var room = roomsByName[name] || {};
      var row = el("div", "room-row");
      var main = el("div", "room-main");
      main.appendChild(el("h3", "room-name", name));
      var meta = el("p", "room-meta");
      var last = room.last_check || null;
      var filmedBy = "";
      if (last) filmedBy = text(last.filmed_by || last.filmedBy || last.filmed_by_name || "");
      if (!filmedBy) filmedBy = text(room.filmed_by || room.filmedBy || "");
      if (last && last.date) {
        meta.appendChild(document.createTextNode("Last check: " + formatCheckDate(last.date)));
        if (filmedBy) meta.appendChild(document.createTextNode(" · filmed by " + filmedBy));
        meta.appendChild(document.createTextNode(" · "));
      } else if (room.baseline && room.baseline.date) {
        meta.appendChild(document.createTextNode("Saved setup: " + formatDay(room.baseline.date)));
        if (filmedBy) meta.appendChild(document.createTextNode(" · filmed by " + filmedBy));
        meta.appendChild(document.createTextNode(" · "));
      } else {
        meta.appendChild(document.createTextNode("No check yet"));
        if (filmedBy) meta.appendChild(document.createTextNode(" · filmed by " + filmedBy));
        meta.appendChild(document.createTextNode(" · "));
      }
      meta.appendChild(statusLine(last ? last.status : (room.status || "")));
      main.appendChild(meta);
      row.appendChild(main);

      var side = el("div", "room-side");
      var due = dueText(room);
      if (due) side.appendChild(el("span", "due-note", due));
      var reminder = el("a", "room-link", "Add a re-film reminder");
      reminder.href = "/api/reminder.ics?room=" + encodeURIComponent(name) + "&every=14";
      side.appendChild(reminder);
      row.appendChild(side);
      roomList.appendChild(row);
    });
  }

  /* ---------------- Timeline ---------------- */

  function renderEntry(entry, isNew) {
    var li = el("li", "feed-entry" + (isNew ? " is-new" : ""));
    li.appendChild(statusLine(entry.status));

    var headline = el("h3", "feed-headline", text(entry.headline) || (text(entry.room) + " — checked"));
    var entrySimulated = isSimulatedText(entry.filmed_by) || isSimulatedText(entry.source) ||
      isSimulatedText(entry.origin) || isSimulatedText(entry.device) ||
      isSimulatedText(entry.room) || isSimulatedText(entry.headline) ||
      isSimulatedText(entry.concept);
    if (entrySimulated) {
      headline.appendChild(document.createTextNode(" "));
      headline.appendChild(simulationTag());
    }
    li.appendChild(headline);

    var metaParts = [];
    if (entry.room) metaParts.push(text(entry.room));
    if (entry.ts) metaParts.push(formatDate(entry.ts));
    if (entry.filmed_by) metaParts.push("Filmed by " + text(entry.filmed_by));
    if (metaParts.length) li.appendChild(el("p", "feed-meta", metaParts.join(" · ")));

    var trend = trendText(entry.trend);
    if (trend) li.appendChild(el("p", "feed-trend", "Across visits: " + trend));

    var items = Array.isArray(entry.items) ? entry.items : [];
    if (items.length) {
      var list = el("ul", "feed-items");
      var seenConcepts = Object.create(null);
      items.forEach(function (item) {
        if (!item || typeof item !== "object") return;
        var rawConcept = text(item.concept);
        var itemSimulated = isSimulatedText(rawConcept) || isSimulatedText(item.source) || isSimulatedText(item.origin);
        var concept = itemSimulated ? cleanSimulatedConcept(rawConcept) : rawConcept;
        var dedupeKey = (concept || rawConcept).trim().toLowerCase();
        if (!dedupeKey) dedupeKey = text(item.change).trim().toLowerCase() + "|" + text(item.next_step).trim().toLowerCase();
        if (dedupeKey && seenConcepts[dedupeKey]) return;
        if (dedupeKey) seenConcepts[dedupeKey] = true;

        var row = el("li", "feed-item");
        if (concept) row.appendChild(el("span", "feed-item-concept", concept));
        if (itemSimulated) {
          if (concept) row.appendChild(document.createTextNode(" "));
          row.appendChild(simulationTag());
        }
        if (item.next_step && /on purpose/i.test(text(item.next_step))) {
          var tag = el("span", "dad-choice-tag", "Dad's choice");
          if (concept || itemSimulated) row.appendChild(document.createTextNode(" "));
          row.appendChild(tag);
        }
        var change = CHANGE_WORDS[item.change] || text(item.change).replace(/_/g, " ");
        if (change) row.appendChild(document.createTextNode((concept ? " — " : "") + change));
        if (item.risk) row.appendChild(el("span", "feed-item-risk", " · risk: " + text(item.risk)));
        if (item.next_step) {
          var step = el("p", "feed-next-step");
          step.appendChild(el("span", "feed-next-step-label", "Next step: "));
          step.appendChild(document.createTextNode(text(item.next_step)));
          row.appendChild(step);
        }
        list.appendChild(row);
      });
      if (list.childNodes.length) li.appendChild(list);
    }

    var links = el("div", "feed-links");
    var report = el("a", "", "Open full report");
    report.href = entry.run_id ? "/app?run=" + encodeURIComponent(entry.run_id) : "/app";
    links.appendChild(report);
    if (entry.room) {
      var reminder = el("a", "", "Add a re-film reminder");
      reminder.href = "/api/reminder.ics?room=" + encodeURIComponent(entry.room) + "&every=14";
      links.appendChild(reminder);
    }
    li.appendChild(links);
    return li;
  }

  function renderFeed() {
    feedList.textContent = "";
    entryOrder.forEach(function (key) {
      var entry = entriesById[key];
      if (entry) feedList.appendChild(renderEntry(entry, false));
    });
    if (feedEmpty) feedEmpty.hidden = entryOrder.length > 0;
  }

  function addEntry(entry, isLive) {
    var key = entryKey(entry);
    if (!key) return false;
    var isNewEntry = !entriesById[key];
    entriesById[key] = entry;
    if (isNewEntry) {
      entryOrder.unshift(key);
      renderFeed();
      var first = feedList.firstElementChild;
      if (first && isLive) {
        first.classList.add("is-new");
        window.setTimeout(function () { first.classList.remove("is-new"); }, 600);
      }
    } else {
      renderFeed();
    }
    if (isLive && isNewEntry) {
      if (entry.status === "needs_attention") {
        attentionSinceLoad += 1;
        document.title = "(" + attentionSinceLoad + ") " + baseTitle;
      }
      maybeNotify(entry);
    }
    return isNewEntry;
  }

  function applySnapshot(data) {
    if (!data || typeof data !== "object") return;
    if (Array.isArray(data.rooms)) renderRooms(data.rooms);
    if (Array.isArray(data.entries)) {
      var fresh = data.entries.filter(function (e) { return !entriesById[entryKey(e)]; });
      fresh.slice().reverse().forEach(function (e) { addEntry(e, false); });
      if (!fresh.length) renderFeed();
    }
    if (feedEmpty) feedEmpty.hidden = entryOrder.length > 0;
  }

  /* ---------------- Ask about Dad's room ---------------- */

  var askForm = document.getElementById("ask-form");
  var askInput = document.getElementById("ask-input");
  var askSubmit = document.getElementById("ask-submit");
  var askStatus = document.getElementById("ask-status");
  var askError = document.getElementById("ask-error");
  var askAnswerWrap = document.getElementById("ask-answer-wrap");
  var askAnswer = document.getElementById("ask-answer");
  var askSources = document.getElementById("ask-sources");

  function formatSourceWhen(value) {
    if (!value) return "";
    var d = new Date(value);
    if (isNaN(d.getTime())) return text(value);
    try {
      return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    } catch (e) {
      return formatDate(value);
    }
  }

  function sourceLabel(source) {
    if (typeof source === "string") return source;
    if (!source || typeof source !== "object") return "";
    if (source.label) return text(source.label);
    if (source.title) return text(source.title);
    var parts = [];
    if (source.room) parts.push(text(source.room));
    else if (source.room_name) parts.push(text(source.room_name));
    var when = formatSourceWhen(source.ts || source.date || source.time || source.when);
    if (when) parts.push(when);
    if (source.headline) parts.push(text(source.headline));
    return parts.join(" · ");
  }

  function sourceHref(source) {
    if (!source || typeof source !== "object") return "/app";
    if (source.href) return text(source.href);
    if (source.url) return text(source.url);
    if (source.run_id) return "/app?run=" + encodeURIComponent(source.run_id);
    if (source.run) return "/app?run=" + encodeURIComponent(source.run);
    return "/app";
  }

  function renderAskSources(sources) {
    if (!askSources) return;
    askSources.textContent = "";
    var list = Array.isArray(sources) ? sources : [];
    var rendered = 0;
    list.forEach(function (source) {
      var label = sourceLabel(source);
      if (!label) return;
      if (rendered) askSources.appendChild(document.createTextNode("  "));
      var link = el("a", "ask-source-link mono", label);
      link.href = sourceHref(source);
      askSources.appendChild(link);
      rendered += 1;
    });
    askSources.hidden = rendered === 0;
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.text().then(function (bodyText) {
        var data = null;
        if (bodyText) {
          try { data = JSON.parse(bodyText); } catch (e) { data = { text: bodyText }; }
        }
        if (!response.ok) {
          var message = data && (data.error || data.message) ? text(data.error || data.message) : "";
          throw new Error(message || ("Request failed (" + response.status + ")"));
        }
        return data || {};
      });
    });
  }

  function submitAsk(question) {
    var q = text(question).trim();
    if (!q) {
      if (askInput) askInput.focus();
      return;
    }
    if (askInput) askInput.value = q;
    if (askError) { askError.hidden = true; askError.textContent = ""; }
    if (askAnswerWrap) askAnswerWrap.hidden = true;
    if (askStatus) askStatus.textContent = "Reading the checks…";
    if (askSubmit) askSubmit.disabled = true;
    document.querySelectorAll(".chip").forEach(function (chip) { chip.disabled = true; });

    postJson("/api/ask", { question: q })
      .then(function (data) {
        var answer = "";
        if (typeof data === "string") answer = data;
        else answer = text(data.answer || data.text || data.response || data.message || data.result || "").trim();
        if (!answer) throw new Error("Empty answer");
        if (askAnswer) askAnswer.textContent = answer;
        renderAskSources(data.sources || data.citations || data.evidence || data.links || []);
        if (askAnswerWrap) askAnswerWrap.hidden = false;
        if (askStatus) askStatus.textContent = "";
      })
      .catch(function () {
        if (askStatus) askStatus.textContent = "";
        if (askError) {
          askError.textContent = "Sorry — I couldn't read the checks just now. Please try again in a moment.";
          askError.hidden = false;
        }
      })
      .then(function () {
        if (askSubmit) askSubmit.disabled = false;
        document.querySelectorAll(".chip").forEach(function (chip) { chip.disabled = false; });
      });
  }

  if (askForm) {
    askForm.addEventListener("submit", function (event) {
      event.preventDefault();
      submitAsk(askInput ? askInput.value : "");
    });
  }
  document.querySelectorAll(".chip[data-question]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      submitAsk(chip.getAttribute("data-question") || chip.textContent);
    });
  });

  /* ---------------- Write an update ---------------- */

  var updateForm = document.getElementById("update-form");
  var updateName = document.getElementById("update-name");
  var updateSubmit = document.getElementById("update-submit");
  var updateStatus = document.getElementById("update-status");
  var updateError = document.getElementById("update-error");
  var updateDadHelp = document.getElementById("update-dad-help");
  var updateResultWrap = document.getElementById("update-result-wrap");
  var updateText = document.getElementById("update-text");
  var updateCopy = document.getElementById("update-copy");
  var updateSend = document.getElementById("update-send");
  var updateCopyNote = document.getElementById("update-copy-note");
  var updateCopyTimer = null;

  function selectedUpdateFor() {
    var checked = document.querySelector('input[name="update-for"]:checked');
    return checked ? checked.value : "nearby";
  }

  function refreshDadHelp() {
    if (updateDadHelp) updateDadHelp.hidden = selectedUpdateFor() !== "dad";
  }

  document.querySelectorAll('input[name="update-for"]').forEach(function (radio) {
    radio.addEventListener("change", refreshDadHelp);
  });
  refreshDadHelp();

  if (updateForm) {
    updateForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (updateError) { updateError.hidden = true; updateError.textContent = ""; }
      if (updateResultWrap) updateResultWrap.hidden = true;
      if (updateCopyNote) updateCopyNote.textContent = "";
      if (updateStatus) updateStatus.textContent = "Writing…";
      if (updateSubmit) updateSubmit.disabled = true;

      postJson("/api/update", {
        "for": selectedUpdateFor(),
        name: updateName ? updateName.value.trim() : ""
      })
        .then(function (data) {
          var draft = "";
          if (typeof data === "string") draft = data;
          else draft = text(data.text || data.update || data.message || data.draft || data.result || "").trim();
          if (!draft) throw new Error("Empty update");
          if (updateText) updateText.textContent = draft;
          if (updateResultWrap) updateResultWrap.hidden = false;
          if (updateStatus) updateStatus.textContent = "";
        })
        .catch(function () {
          if (updateStatus) updateStatus.textContent = "";
          if (updateError) {
            updateError.textContent = "Sorry — I couldn't write that just now. Please try again in a moment.";
            updateError.hidden = false;
          }
        })
        .then(function () {
          if (updateSubmit) updateSubmit.disabled = false;
        });
    });
  }

  if (updateCopy) {
    updateCopy.addEventListener("click", function () {
      var draft = updateText ? updateText.textContent : "";
      if (!draft) return;
      function copied() {
        if (updateCopyNote) updateCopyNote.textContent = "Copied.";
        updateCopy.textContent = "Copied";
        if (updateCopyTimer) window.clearTimeout(updateCopyTimer);
        updateCopyTimer = window.setTimeout(function () {
          updateCopy.textContent = "Copy";
          if (updateCopyNote) updateCopyNote.textContent = "";
        }, 2000);
      }
      function failed() {
        if (updateCopyNote) updateCopyNote.textContent = "Copy didn't work here — select the text above to copy it by hand.";
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(draft).then(copied).catch(function () {
          if (!fallbackCopy(draft)) failed(); else copied();
        });
      } else if (fallbackCopy(draft)) {
        copied();
      } else {
        failed();
      }
    });
  }

  function fallbackCopy(value) {
    try {
      var area = document.createElement("textarea");
      area.value = value;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(area);
      return !!ok;
    } catch (e) {
      return false;
    }
  }

  if (updateSend) {
    updateSend.addEventListener("click", function () {
      var draft = updateText ? updateText.textContent : "";
      if (!draft) return;
      if (navigator.share) {
        navigator.share({ title: "About Dad's room", text: draft }).catch(function (err) {
          if (err && err.name === "AbortError") return;
          window.location.href = "mailto:?subject=" + encodeURIComponent("About Dad's room") + "&body=" + encodeURIComponent(draft);
        });
      } else {
        window.location.href = "mailto:?subject=" + encodeURIComponent("About Dad's room") + "&body=" + encodeURIComponent(draft);
      }
    });
  }

  /* ---------------- Notifications (explicit click only) ---------------- */

  function maybeNotify(entry) {
    if (!notificationsEnabled) return;
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    try {
      new Notification(text(entry.headline) || "Second Look check finished");
    } catch (e) { /* Notifications are optional; the feed itself still updates. */ }
  }

  function refreshNotifyButton() {
    if (!("Notification" in window)) {
      notifyBtn.disabled = true;
      notifyNote.textContent = "This browser does not support notifications. The feed above still updates live.";
      return;
    }
    if (Notification.permission === "granted") {
      notificationsEnabled = true;
      notifyBtn.textContent = "Notifications on for this device";
      notifyNote.textContent = "You will get the headline of each new check on this device — words only.";
    } else if (Notification.permission === "denied") {
      notifyBtn.disabled = true;
      notifyNote.textContent = "Notifications are blocked in this browser. The feed above still updates live.";
    }
  }

  if (notifyBtn) {
    notifyBtn.addEventListener("click", function () {
      if (!("Notification" in window)) { refreshNotifyButton(); return; }
      if (Notification.permission === "granted") { refreshNotifyButton(); return; }
      Notification.requestPermission().then(function () { refreshNotifyButton(); }).catch(function () {
        notifyNote.textContent = "Notification permission was not granted. The feed above still updates live.";
      });
    });
    refreshNotifyButton();
  }

  /* ---------------- Live connection ---------------- */

  function setLive(isLive) {
    liveIndicator.textContent = isLive ? "live" : "reconnecting…";
    liveIndicator.classList.toggle("is-live", !!isLive);
  }

  function fallbackFetch() {
    if (!window.fetch) return;
    fetch("/api/feed", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var entries = Array.isArray(data) ? data : (data && data.entries);
        if (Array.isArray(entries)) applySnapshot({ entries: entries });
      })
      .catch(function () { /* The next SSE retry remains the source of truth. */ });
    fetch("/api/rooms", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var rooms = Array.isArray(data) ? data : (data && data.rooms);
        if (Array.isArray(rooms)) renderRooms(rooms);
      })
      .catch(function () { /* Ignore; rooms refresh on the next snapshot. */ });
  }

  function scheduleFallback() {
    if (fallbackTimer) return;
    fallbackTimer = window.setTimeout(function () {
      fallbackTimer = null;
      fallbackFetch();
    }, 1200);
  }

  function connect() {
    if (!("EventSource" in window)) {
      setLive(false);
      fallbackFetch();
      window.setInterval(fallbackFetch, 60000);
      return;
    }
    var source = new EventSource("/api/feed/events");
    source.onopen = function () { setLive(true); };
    source.onerror = function () {
      setLive(false);
      scheduleFallback();
    };
    source.onmessage = function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (e) { return; }
      if (!data || typeof data !== "object") return;
      if (data.type === "snapshot") {
        applySnapshot(data);
        setLive(true);
      } else if (data.type === "entry" && data.entry) {
        addEntry(data.entry, true);
      } else if (data.type === "due") {
        if (Array.isArray(data.rooms)) renderRooms(data.rooms);
      } else if (data.type === "ping") {
        setLive(true);
      }
    };
  }

  renderRooms([]);
  renderFeed();
  setLive(false);
  connect();
})();
