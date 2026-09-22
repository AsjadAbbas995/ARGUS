/* ARGUS Operator Dashboard client (Phase 11).
 * Dependency-free vanilla JS. Every action is a single, explicit operator step:
 * Approve or Reject a specific hypothesis. There is deliberately NO "approve all"
 * or bulk control on this page, in this client, or in the API (by design).
 */
(function () {
  "use strict";

  var KEY_STORE = "argus.dashboard.key";
  var keyInput = document.getElementById("apiKey");
  var connectBtn = document.getElementById("connect");
  var statusEl = document.getElementById("authStatus");
  var runBox = document.getElementById("auth");
  var runsEl = document.getElementById("runs");
  var runList = document.getElementById("runList");
  var hySec = document.getElementById("hypotheses");
  var hyList = document.getElementById("hypoList");
  var runTitle = document.getElementById("currentRun");

  var apiKey = "";
  var base = "/api/v1";
  var currentRun = null;

  function warn(msg) {
    statusEl.textContent = msg;
    statusEl.classList.add("err");
  }

  function clearWarn() {
    statusEl.textContent = "";
    statusEl.classList.remove("err");
  }

  function request(method, path, body, key) {
    var opts = {
      method: method,
      headers: { "Authorization": "Bearer " + (key || apiKey), "Accept": "application/json" }
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(base + path, opts).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.detail) || ("HTTP " + res.status));
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function connect() {
    var k = keyInput.value.trim();
    if (!k) { warn("API key required"); return; }
    apiKey = k;
    clearWarn();
    request("GET", "/runs", undefined, k)
      .then(renderRuns)
      .catch(function (e) { warn(e.message); apiKey = ""; });
  }

  function renderRuns(data) {
    keyInput.disabled = true;
    connectBtn.disabled = true;
    localStorage.setItem(KEY_STORE, apiKey);
    runBox.hidden = true;
    runsEl.hidden = false;
    runList.innerHTML = "";
    (data.runs || []).forEach(function (r) {
      var li = document.createElement("li");
      var btn = document.createElement("button");
      btn.className = "run";
      btn.type = "button";
      btn.textContent = "Run " + r.id + " -- " + r.status;
      btn.addEventListener("click", function () { openRun(r.id, r.status); });
      li.appendChild(btn);
      runList.appendChild(li);
    });
  }

  function openRun(runId, status) {
    currentRun = runId;
    runTitle.textContent = "Run " + runId + " (" + status + ")";
    hySec.hidden = false;
    request("GET", "/runs/" + runId + "/hypotheses")
      .then(renderHypotheses)
      .catch(function (e) { warn(e.message); });
  }

  function renderHypotheses(data) {
    hyList.innerHTML = "";
    (data.hypotheses || []).forEach(function (h) {
      hyList.appendChild(hypothesisCard(h));
    });
  }

  function hypothesisCard(h) {
    var card = document.createElement("article");
    card.className = "card " + h.status;
    card.dataset.hid = h.id;

    var head = document.createElement("div");
    head.className = "meta";
    head.textContent = h.id + " -- step " + h.validation_step + " -- confidence " + h.confidence;

    var st = document.createElement("p");
    st.className = "stmt";
    st.textContent = h.statement;

    var meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = "truth label: " + h.truth_label + " -- severity: " + h.severity + " -- target: " + h.target;

    var acts = document.createElement("div");
    acts.className = "actrow";

    var approve = document.createElement("button");
    approve.type = "button";
    approve.className = "approve";
    approve.textContent = "Approve this validation step";
    approve.addEventListener("click", function () {
      approve.disabled = true;
      request("POST", "/runs/" + currentRun + "/hypotheses/" + h.id + "/approve", {})
        .then(function (r) { refreshReview(card, r); })
        .catch(function (e) { warn(e.message); approve.disabled = false; });
    });

    var reject = document.createElement("button");
    reject.type = "button";
    reject.className = "reject";
    reject.textContent = "Reject this validation step";
    reject.addEventListener("click", function () {
      var reason = window.prompt("Reason for rejection:", "operator review: confidence insufficient");
      if (reason === null) { return; }
      reject.disabled = true;
      request("POST", "/runs/" + currentRun + "/hypotheses/" + h.id + "/reject", { reason: reason || "operator review: rejected" })
        .then(function (r) { refreshReview(card, r); })
        .catch(function (e) { warn(e.message); reject.disabled = false; });
    });

    acts.appendChild(approve);
    acts.appendChild(reject);

    card.appendChild(head);
    card.appendChild(st);
    card.appendChild(meta);
    card.appendChild(acts);
    return card;
  }

  function refreshReview(card, payload) {
    if (!payload) { return; }
    card.className = "card " + payload.status;
    card.dataset.hid = payload.id;
    var acts = card.querySelectorAll(".actrow button");
    for (var i = 0; i < acts.length; i += 1) { acts[i].disabled = true; }
    var p = document.createElement("p");
    p.className = "meta";
    p.textContent = "recorded: " + payload.status + (payload.reason ? " -- " + payload.reason : "");
    card.appendChild(p);
    clearWarn();
  }

  function boot() {
    var saved = localStorage.getItem(KEY_STORE);
    if (saved) {
      keyInput.value = saved;
      apiKey = saved;
      keyInput.disabled = true;
      connectBtn.disabled = true;
      request("GET", "/runs")
        .then(renderRuns)
        .catch(function () {
          keyInput.disabled = false;
          connectBtn.disabled = false;
          warn("Saved key rejected; re-enter the key to connect.");
        });
    }
    connectBtn.addEventListener("click", connect);
    keyInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { connect(); } });
  }

  boot();
})();
