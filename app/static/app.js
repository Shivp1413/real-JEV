// ---------------------------------------------------------------------------
// JevLocal front-end
// ---------------------------------------------------------------------------
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = async (url, opts) => {
  const r = await fetch(url, opts);
  const t = await r.text();
  let j; try { j = JSON.parse(t); } catch { j = { raw: t }; }
  if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
  return j;
};

// ---- Tabs -----------------------------------------------------------------
$$(".tab").forEach(t => t.addEventListener("click", () => switchTab(t.dataset.tab)));
function switchTab(name) {
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $$(".panel").forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
  const nav = $(`.tab[data-tab="${name}"]`);
  if (nav) {
    $("#sectionTitle").textContent = nav.dataset.title || "";
    $("#sectionDesc").textContent = nav.dataset.desc || "";
  }
  if (name === "models") loadModels();
  if (name === "websearch") loadSettings();
}
document.addEventListener("click", e => {
  const g = e.target.closest("[data-goto]");
  if (g) { e.preventDefault(); switchTab(g.dataset.goto); }
});

// ---- Status ---------------------------------------------------------------
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    const active = s.backend.active;
    const pill = $("#backendPill");
    const chip = $("#modeChip");
    if (active === "mock") {
      pill.textContent = "demo mode"; pill.className = "pill demo";
      $("#demoBanner").classList.remove("hidden");
      chip.textContent = "demo mode"; chip.className = "modechip demo";
    } else {
      pill.textContent = active === "ollama" ? "Ollama · running" : active + " · running";
      pill.className = "pill ok";
      $("#demoBanner").classList.add("hidden");
      chip.textContent = "running locally"; chip.className = "modechip ok";
    }
    $("#modelPill").textContent = s.model || "—";
  } catch (e) { $("#backendPill").textContent = "server error"; }
}

// ---- Question builder -----------------------------------------------------
let qCounter = 0;
function optionRow(key = "", desc = "") {
  const div = document.createElement("div");
  div.className = "opt";
  div.innerHTML = `<input class="optkey" placeholder="option" value="${esc(key)}">
    <input class="optdesc" placeholder="description (optional)" value="${esc(desc)}">
    <button title="remove">✕</button>`;
  div.querySelector("button").onclick = () => div.remove();
  return div;
}
function addQuestion(preset) {
  qCounter++;
  const p = preset || { id: "q" + qCounter, type: "choice", instructions: "", options: [["", ""]] };
  const card = document.createElement("div");
  card.className = "qcard";
  card.innerHTML = `
    <div class="qhead">
      <input class="qid" value="${esc(p.id)}" placeholder="id">
      <select class="qtype">
        <option value="choice">Choice</option>
        <option value="score">Score</option>
        <option value="noul">Noul (yes/no)</option>
      </select>
      <button class="del" title="delete question">🗑</button>
    </div>
    <input class="qinstr" placeholder="Instructions, e.g. Which team should handle this?" value="${esc(p.instructions)}">
    <div class="opts"></div>
    <button class="btn ghost small addopt">+ option</button>`;
  card.querySelector(".qtype").value = p.type;
  const optsBox = card.querySelector(".opts");
  const addBtn = card.querySelector(".addopt");
  (p.options || []).forEach(([k, d]) => optsBox.appendChild(optionRow(k, d)));
  addBtn.onclick = () => optsBox.appendChild(optionRow());
  card.querySelector(".del").onclick = () => card.remove();
  const syncType = () => {
    const t = card.querySelector(".qtype").value;
    const isNoul = t === "noul";
    optsBox.classList.toggle("hidden", isNoul);
    addBtn.classList.toggle("hidden", isNoul);
  };
  card.querySelector(".qtype").onchange = syncType;
  syncType();
  $("#questions").appendChild(card);
}
$("#addQuestion").onclick = () => addQuestion();

function collectQuestions() {
  const out = {};
  $$(".qcard").forEach(card => {
    const id = card.querySelector(".qid").value.trim() || "q";
    const type = card.querySelector(".qtype").value;
    const instructions = card.querySelector(".qinstr").value.trim();
    if (type === "noul") { out[id] = { type, instructions }; return; }
    const crit = {};
    const keys = [];
    $$(".opt", card).forEach(o => {
      const k = o.querySelector(".optkey").value.trim();
      const d = o.querySelector(".optdesc").value.trim();
      if (k) { crit[k] = d; keys.push([k, d]); }
    });
    if (type === "score") out[id] = { type, instructions, criteria: keys.map(x => x[0]) };
    else out[id] = { type, instructions, criteria: crit };
  });
  return out;
}

// ---- Example --------------------------------------------------------------
$("#loadExample").onclick = () => {
  $("#stateInput").value = "Hi, I've been trying to connect Stripe but keep getting a 403 error and I'm on a deadline.";
  $("#questions").innerHTML = ""; qCounter = 0;
  addQuestion({ id: "department", type: "choice", instructions: "Which team should handle this?",
    options: [["billing", "Payment or subscription issues"], ["technical", "Bugs or integration problems"], ["sales", "Pricing or account questions"]] });
  addQuestion({ id: "frustration", type: "score", instructions: "How frustrated does the customer appear?",
    options: [["Calm", ""], ["Frustrated but civil", ""], ["Very angry", ""]] });
  addQuestion({ id: "urgent", type: "noul", instructions: "Does this require an immediate response?", options: [] });
};

// ---- Run ------------------------------------------------------------------
$("#runBtn").onclick = async () => {
  const questions = collectQuestions();
  if (!Object.keys(questions).length) { alert("Add at least one question."); return; }
  const btn = $("#runBtn"); btn.disabled = true; btn.textContent = "⏳ Deciding…";
  $("#results").innerHTML = `<p class="muted empty">Running…</p>`;
  try {
    const res = await api("/api/decide", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: $("#stateInput").value, questions, use_web: $("#useWeb").checked })
    });
    renderResults(res);
    $("#rawJson").textContent = JSON.stringify(res, null, 2);
  } catch (e) {
    $("#results").innerHTML = `<p style="color:var(--red)">Error: ${esc(e.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = "▶ Run decision"; }
};

function bar(label, p, win) {
  const pct = Math.round(p * 100);
  return `<div class="bar"><span class="blbl ${win ? "win" : ""}" title="${esc(label)}">${esc(label)}</span>
    <span class="btrack"><span class="bfill ${win ? "win" : ""}" style="width:${pct}%"></span></span>
    <span class="bpct">${pct}%</span></div>`;
}
function confRow(conf, extra) {
  const pct = Math.round(conf * 100);
  return `<div class="conf">${extra ? esc(extra) + " · " : ""}confidence
    <span class="cbar"><span style="width:${pct}%"></span></span> ${pct}%</div>`;
}
function renderResults(res) {
  const box = $("#results"); box.innerHTML = "";
  if (res.web_search && res.web_search.used)
    box.insertAdjacentHTML("beforeend",
      `<div class="webnote"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"/></svg>
       Web search added ${res.web_search.results.length} result(s) as extra context.</div>`);
  for (const [qid, a] of Object.entries(res.answers)) {
    let body = "";
    if (a.type === "noul") {
      const yes = a.noul >= 0.5;
      body = `<div class="verdict"><span class="yn ${yes ? "yes" : "no"}">${yes ? "YES" : "NO"}</span>${Math.round(a.noul * 100)}% likely yes</div>
        <div class="noulbar">${bar("probability of “yes”", a.noul, yes)}</div>
        ${confRow(a.confidence)}`;
    } else if (a.type === "score") {
      const bars = a.levels.map(l => bar(l, a.probabilities[l], l === a.score)).join("");
      body = `<div class="verdict">${esc(a.score)}</div>${bars}
        ${confRow(a.confidence, "expected level " + a.expected_index.toFixed(2))}`;
    } else {
      const entries = Object.entries(a.probabilities).sort((x, y) => y[1] - x[1]);
      const bars = entries.map(([k, v]) => bar(k, v, k === a.choice)).join("");
      body = `<div class="verdict">${esc(a.choice)}</div>${bars}${confRow(a.confidence)}`;
    }
    box.insertAdjacentHTML("beforeend",
      `<div class="ans"><div class="atop"><span class="qname">${esc(qid)}</span><span class="qtype">${a.type}</span></div>${body}</div>`);
  }
}

// ---- Models ---------------------------------------------------------------
async function loadModels() {
  const box = $("#modelList");
  box.innerHTML = `<p class="muted">Loading…</p>`;
  let data;
  try { data = await api("/api/models"); } catch (e) { box.innerHTML = `<p style="color:var(--red)">${esc(e.message)}</p>`; return; }
  const ollamaUp = data.backend.ollama_available;
  const ramMax = parseInt($("#ramFilter").value, 10);
  box.innerHTML = "";
  if (!ollamaUp) box.insertAdjacentHTML("beforeend",
    `<div class="banner" style="grid-column:1/-1;margin:0"><svg viewBox="0 0 24 24"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg><div>Ollama isn't running, so models can't be downloaded yet. Install it from <a href="https://ollama.com/download" target="_blank">ollama.com</a> and run <code>ollama serve</code>, then reload.</div></div>`);
  data.models
    .filter(m => (typeof m.min_ram_gb === "number" ? m.min_ram_gb <= ramMax : true))
    .forEach(m => box.appendChild(modelCard(m, ollamaUp)));
  if (!box.children.length) box.innerHTML = `<p class="muted">No models fit that RAM limit.</p>`;
}
$("#ramFilter").onchange = loadModels;

function modelCard(m, ollamaUp) {
  const el = document.createElement("div");
  el.className = "mcard" + (m.active ? " active" : "");
  const badges = [];
  if (m.tier === "default") badges.push(`<span class="badge tier-default">recommended</span>`);
  if (m.active) badges.push(`<span class="badge active">active</span>`);
  if (m.installed) badges.push(`<span class="badge installed">installed</span>`);
  badges.push(`<span class="badge">${esc(m.family)}</span>`);
  const ram = m.min_ram_gb === "?" ? "?" : m.min_ram_gb + " GB";
  el.innerHTML = `
    <div class="mtop"><span class="mlabel">${esc(m.label)}</span></div>
    <div class="badges">${badges.join("")}</div>
    <div class="mnotes">${esc(m.notes)}</div>
    <div class="mstats">
      <span class="stat">params <b>${esc(m.params)}</b></span>
      <span class="stat">download <b>~${m.download_gb} GB</b></span>
      <span class="stat">needs <b>${ram}</b> RAM</span>
    </div>
    <div class="progress hidden"><div class="pf"></div></div>
    <div class="pmsg"></div>
    <div class="mactions"></div>`;
  const actions = el.querySelector(".mactions");
  if (m.installed) {
    if (!m.active) actions.appendChild(btn("Use", "primary", () => useModel(m.tag)));
    else actions.appendChild(btnDisabled("In use"));
    actions.appendChild(btn("Remove", "ghost", () => removeModel(m.tag)));
  } else {
    const b = btn("Download", "primary", () => pullModel(m.tag, el));
    if (!ollamaUp) b.disabled = true;
    actions.appendChild(b);
  }
  return el;
}
function btn(label, cls, fn) { const b = document.createElement("button"); b.className = "btn " + cls + " small"; b.textContent = label; b.onclick = fn; return b; }
function btnDisabled(label) { const b = document.createElement("button"); b.className = "btn small"; b.textContent = label; b.disabled = true; return b; }

async function useModel(tag) { await api("/api/models/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tag }) }); await refreshStatus(); loadModels(); }
async function removeModel(tag) { if (!confirm("Remove " + tag + "?")) return; await api("/api/models/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tag }) }); loadModels(); }

async function pullModel(tag, el) {
  const prog = el.querySelector(".progress"); const pf = el.querySelector(".pf"); const msg = el.querySelector(".pmsg");
  el.querySelectorAll(".mactions button").forEach(b => b.disabled = true);
  prog.classList.remove("hidden"); msg.textContent = "starting…";
  const r = await fetch("/api/models/pull", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tag }) });
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  while (true) {
    const { done, value } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n"); buf = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      let ev; try { ev = JSON.parse(line); } catch { continue; }
      if (ev.error) { msg.textContent = "Error: " + ev.error; msg.style.color = "var(--red)"; continue; }
      if (ev.total && ev.completed) { pf.style.width = Math.round(ev.completed / ev.total * 100) + "%"; }
      msg.textContent = ev.status || "downloading…";
    }
  }
  msg.textContent = "✓ installed"; pf.style.width = "100%";
  setTimeout(loadModels, 600);
}

// ---- Settings / web search ------------------------------------------------
async function loadSettings() {
  const s = await api("/api/settings");
  $("#webEnabled").checked = !!s.web_search_enabled;
  $("#webProvider").value = s.web_search_provider || "brave";
  $("#webCount").value = s.web_search_results || 4;
  $("#braveState").textContent = s.brave_api_key_set ? "✓ key saved" : "not set";
  $("#braveState").className = "statechip" + (s.brave_api_key_set ? " set" : "");
  $("#firecrawlState").textContent = s.firecrawl_api_key_set ? "✓ key saved" : "not set";
  $("#firecrawlState").className = "statechip" + (s.firecrawl_api_key_set ? " set" : "");
  $("#backendSel").value = s.backend || "ollama";
  $("#ollamaUrl").value = s.ollama_url || "";
  $("#openaiBase").value = s.openai_base_url || "";
  syncProvider(); syncBackend();
}
function syncProvider() {
  const p = $("#webProvider").value;
  $("#braveField").classList.toggle("hidden", p !== "brave");
  $("#firecrawlField").classList.toggle("hidden", p !== "firecrawl");
}
function syncBackend() { $("#openaiFields").classList.toggle("hidden", $("#backendSel").value !== "openai"); }
$("#webProvider").onchange = syncProvider;
$("#backendSel").onchange = syncBackend;

$("#saveWeb").onclick = async () => {
  const patch = { web_search_enabled: $("#webEnabled").checked, web_search_provider: $("#webProvider").value, web_search_results: parseInt($("#webCount").value, 10) || 4 };
  if ($("#braveKey").value.trim()) patch.brave_api_key = $("#braveKey").value.trim();
  if ($("#firecrawlKey").value.trim()) patch.firecrawl_api_key = $("#firecrawlKey").value.trim();
  await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
  $("#braveKey").value = ""; $("#firecrawlKey").value = "";
  await loadSettings(); await refreshStatus();
  flash("#saveWeb", "Saved ✓");
};
$("#testWeb").onclick = async () => {
  const out = $("#webTestOut"); out.innerHTML = "Testing…";
  // save first so the key is used
  await $("#saveWeb").onclick();
  try {
    const r = await api("/api/websearch/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: "latest AI news" }) });
    out.innerHTML = r.results.map(x => `<div class="r"><a href="${esc(x.url)}" target="_blank">${esc(x.title)}</a><div class="muted">${esc(x.snippet)}</div></div>`).join("") || "No results.";
  } catch (e) { out.innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`; }
};
$("#saveBackend").onclick = async () => {
  const patch = { backend: $("#backendSel").value, ollama_url: $("#ollamaUrl").value.trim(), openai_base_url: $("#openaiBase").value.trim() };
  if ($("#openaiKey").value.trim()) patch.openai_api_key = $("#openaiKey").value.trim();
  await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
  $("#openaiKey").value = "";
  await refreshStatus(); flash("#saveBackend", "Saved ✓");
};
function flash(sel, txt) { const b = $(sel); const o = b.textContent; b.textContent = txt; setTimeout(() => b.textContent = o, 1500); }

// ---- misc -----------------------------------------------------------------
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
$("#apiExample").textContent = `curl ${location.origin}/v1/systemone \\
  -H 'Content-Type: application/json' \\
  -d '{
    "model": "jev-latest",
    "state": "I was charged twice this month.",
    "questions": {
      "billing": { "type": "noul", "instructions": "Is this a billing issue?" },
      "team": { "type": "choice", "instructions": "Route to which team?",
        "criteria": { "billing": "money", "tech": "bugs" } }
    }
  }'`;

// ---- boot -----------------------------------------------------------------
$("#loadExample").click();
refreshStatus();
setInterval(refreshStatus, 15000);
