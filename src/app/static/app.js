"use strict";

const $ = (s) => document.querySelector(s);
const state = { level: localStorage.getItem("level") || "N3", grammar: null, cards: [], cardIdx: 0, words: [] };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : res.statusText);
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 4500);
}

async function busy(btn, label, fn) {
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>${label}`;
  try { return await fn(); }
  catch (e) { toast(e.message); }
  finally { btn.disabled = false; btn.innerHTML = orig; }
}

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "cards") loadCards();
  if (name === "vocab") loadVocab();
  if (name === "history") loadHistory();
}

// ---------- levels ----------
async function initLevels() {
  const { levels, all } = await api("/api/levels");
  if (!levels.includes(state.level)) state.level = levels[0];
  $("#level").innerHTML = all.map((l) =>
    `<option value="${l}" ${levels.includes(l) ? "" : "disabled"} ${l === state.level ? "selected" : ""}>${l}${levels.includes(l) ? "" : " (soon)"}</option>`
  ).join("");
  $("#level").addEventListener("change", (e) => {
    state.level = e.target.value;
    localStorage.setItem("level", state.level);
    loadToday();
  });
}

// ---------- today ----------
function renderGrammar(g) {
  state.grammar = g;
  $("#g-date").textContent = `${g.level} · grammar of the day · ${new Date().toLocaleDateString()}`;
  $("#g-pattern").textContent = g.pattern;
  $("#g-meaning").textContent = g.meaning;
  $("#g-formation").textContent = g.formation;
  $("#g-explanation").textContent = g.explanation;
  $("#g-prompt").textContent = `Prompt: ${g.prompt} Try to use ${g.pattern}.`;
  $("#g-examples").innerHTML = g.examples.map((e) =>
    `<li><div class="jp">${esc(e.japanese)}</div><div class="en">${esc(e.english)}</div></li>`).join("");
}

async function loadToday() {
  try { renderGrammar(await api(`/api/today?level=${state.level}`)); }
  catch (e) { toast(e.message); }
}

$("#reroll").addEventListener("click", (e) =>
  busy(e.currentTarget, "", async () => renderGrammar(await api(`/api/today/reroll?level=${state.level}`, { method: "POST" }))));

const entryEl = $("#entry");
const DRAFT_KEY = () => `draft-${new Date().toISOString().slice(0, 10)}`;
entryEl.value = localStorage.getItem(DRAFT_KEY()) || "";
const updateCount = () => ($("#char-count").textContent = `${entryEl.value.trim().length} characters`);
updateCount();
entryEl.addEventListener("input", () => { localStorage.setItem(DRAFT_KEY(), entryEl.value); updateCount(); });

$("#submit").addEventListener("click", (e) => {
  const text = entryEl.value.trim();
  if (!text) return toast("Write something first!");
  busy(e.currentTarget, "Checking…", async () => {
    const r = await api("/api/entries", { method: "POST", body: { text, grammar_id: state.grammar.id, level: state.level } });
    renderFeedback(r);
    localStorage.removeItem(DRAFT_KEY());
    refreshDue();
  });
});

function feedbackHTML(r, { showWords = true } = {}) {
  const errors = r.errors?.length
    ? r.errors.map((x) => `<div class="error-item"><del>${esc(x.original)}</del> → <ins>${esc(x.correction)}</ins><div class="en">${esc(x.explanation)}</div></div>`).join("")
    : `<p class="hint">No errors found. 素晴らしい！</p>`;
  const words = showWords && r.words?.length
    ? `<h2 style="margin-top:16px">Words saved to your flashcards</h2>
       <div class="chips">${r.words.map((w) => `<span class="chip ${w.new ? "new" : ""}" title="${esc(w.reading)} — ${esc(w.meaning)}">${esc(w.word)}</span>`).join("")}</div>
       <p class="hint">Green = new word.</p>`
    : "";
  return `
    <div class="row space">
      <h2>Feedback</h2>
      <span class="verdict ${r.is_correct ? "ok" : "warn"}">${r.is_correct ? "✓ Grammatically correct" : `${r.errors.length} issue${r.errors.length === 1 ? "" : "s"} found`}</span>
    </div>
    <p>${esc(r.overall_feedback)}</p>
    <div class="compare">
      <div><div class="label">Corrected</div><div class="jp">${esc(r.corrected_text)}</div></div>
      <div><div class="label">Natural version</div><div class="jp">${esc(r.natural_version)}</div></div>
    </div>
    <h2>${r.grammar_point_used ? "✓" : "✗"} Grammar point ${esc(r.grammar?.pattern || state.grammar?.pattern || "")}</h2>
    <p>${esc(r.grammar_point_feedback)}</p>
    <h2>Corrections</h2>
    ${errors}
    ${words}`;
}

function renderFeedback(r) {
  const fb = $("#feedback");
  fb.innerHTML = feedbackHTML(r);
  fb.hidden = false;
  fb.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- suggestions ----------
async function doSuggest(btn) {
  const query = $("#suggest-q").value.trim();
  if (!query) return;
  await busy(btn, "", async () => {
    const { suggestions } = await api("/api/suggest", { method: "POST", body: { query, grammar_id: state.grammar?.id, level: state.level } });
    $("#suggestions").innerHTML = suggestions.map((s) => `
      <div class="suggestion">
        <div class="sug-head">
          <span class="sug-word">${esc(s.word)}</span><span class="reading">${esc(s.reading)}</span>
          <span class="pos">${esc(s.part_of_speech)}</span>
          <button class="small insert" data-word="${esc(s.word)}" title="Insert into your entry">＋ insert</button>
        </div>
        <div>${esc(s.meaning)}</div>
        <div class="hint">${esc(s.usage_note)}</div>
        ${s.examples.map((x) => `<div class="sug-ex"><div class="jp">${esc(x.japanese)}</div><div class="reading">${esc(x.reading)}</div><div class="en">${esc(x.english)}</div></div>`).join("")}
      </div>`).join("") || `<p class="hint">No suggestions.</p>`;
  });
}
$("#suggest-btn").addEventListener("click", (e) => doSuggest(e.currentTarget));
$("#suggest-q").addEventListener("keydown", (e) => { if (e.key === "Enter") doSuggest($("#suggest-btn")); });
$("#suggestions").addEventListener("click", (e) => {
  const b = e.target.closest(".insert");
  if (!b) return;
  const { selectionStart: s, selectionEnd: t, value } = entryEl;
  entryEl.value = value.slice(0, s) + b.dataset.word + value.slice(t);
  entryEl.focus();
  entryEl.selectionStart = entryEl.selectionEnd = s + b.dataset.word.length;
  entryEl.dispatchEvent(new Event("input"));
});

// ---------- flashcards ----------
async function refreshDue() {
  try {
    const { cards } = await api("/api/flashcards/due");
    const b = $("#due-badge");
    b.textContent = cards.length;
    b.hidden = cards.length === 0;
  } catch { /* ignore */ }
}

async function loadCards() {
  const { cards, total_words } = await api("/api/flashcards/due");
  state.cards = cards;
  state.cardIdx = 0;
  state.totalWords = total_words;
  renderCard();
}

function renderCard() {
  const area = $("#cards-area");
  const c = state.cards[state.cardIdx];
  if (!c) {
    area.innerHTML = `<div class="card empty">${state.totalWords
      ? "🎉 All caught up! No cards due right now."
      : "No words yet. Write a journal entry and the words you use will appear here."}</div>`;
    refreshDue();
    return;
  }
  area.innerHTML = `
    <div class="flash-wrap">
      <div class="progress">${state.cardIdx + 1} / ${state.cards.length} due</div>
      <div class="card flash" id="flash">
        <div class="front">${esc(c.word)}</div>
        <div class="back" hidden>
          <div class="reading">${esc(c.reading)}</div>
          <div class="meaning">${esc(c.meaning)}</div>
          <span class="pos">${esc(c.pos)}</span>
          ${c.example ? `<p class="jp">${esc(c.example)}</p>` : ""}
        </div>
        <p class="hint" id="flip-hint">Click or press Space to reveal</p>
      </div>
      <div class="grades" id="grades" hidden>
        <button class="again" data-g="again">Again</button>
        <button data-g="hard">Hard</button>
        <button data-g="good">Good</button>
        <button data-g="easy">Easy</button>
      </div>
    </div>`;
  $("#flash").addEventListener("click", flip);
  $("#grades").addEventListener("click", (e) => { const g = e.target.dataset.g; if (g) grade(g); });
}

function flip() {
  const back = document.querySelector("#flash .back");
  if (!back) return;
  back.hidden = false;
  $("#flip-hint").hidden = true;
  $("#grades").hidden = false;
}

async function grade(g) {
  const c = state.cards[state.cardIdx];
  try {
    await api(`/api/flashcards/${c.id}/review`, { method: "POST", body: { grade: g } });
    if (g === "again") state.cards.push(c); // see it again this session
    state.cardIdx++;
    renderCard();
  } catch (e) { toast(e.message); }
}

document.addEventListener("keydown", (e) => {
  if (!$("#tab-cards").classList.contains("active") || ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  const grades = $("#grades");
  if (e.code === "Space") { e.preventDefault(); flip(); }
  else if (grades && !grades.hidden && ["1", "2", "3", "4"].includes(e.key)) grade(["again", "hard", "good", "easy"][+e.key - 1]);
});

// ---------- vocabulary ----------
async function loadVocab() {
  state.words = await api("/api/words");
  renderVocab();
}
function renderVocab() {
  const f = $("#vocab-filter").value.trim().toLowerCase();
  const rows = state.words.filter((w) => !f || [w.word, w.reading, w.meaning].some((x) => (x || "").toLowerCase().includes(f)));
  $("#vocab-count").textContent = `(${state.words.length})`;
  $("#vocab-body").innerHTML = rows.map((w) => `
    <tr><td>${esc(w.word)}</td><td>${esc(w.reading)}</td><td>${esc(w.meaning)}<div class="hint">${esc(w.example)}</div></td>
    <td>${w.seen_count}×</td><td>${esc(w.due)}</td>
    <td><button class="small ghost del-word" data-id="${w.id}" title="Delete">✕</button></td></tr>`).join("")
    || `<tr><td colspan="6" class="empty">No words yet.</td></tr>`;
}
$("#vocab-filter").addEventListener("input", renderVocab);
$("#vocab-body").addEventListener("click", async (e) => {
  const b = e.target.closest(".del-word");
  if (!b || !confirm("Delete this word from your flashcards?")) return;
  await api(`/api/words/${b.dataset.id}`, { method: "DELETE" });
  loadVocab();
  refreshDue();
});

// ---------- history ----------
async function loadHistory() {
  const entries = await api("/api/entries");
  $("#history-list").innerHTML = entries.map((en) => `
    <details class="card hist">
      <summary>
        <div class="hist-meta"><span>${esc(en.day)}</span><span class="pos">${esc(en.grammar.pattern)}</span>
          ${en.feedback ? `<span class="verdict ${en.feedback.is_correct ? "ok" : "warn"}">${en.feedback.is_correct ? "✓" : en.feedback.errors.length + " issues"}</span>` : ""}</div>
        <div class="jp" style="margin-top:6px">${esc(en.text)}</div>
      </summary>
      ${en.feedback ? `<div style="margin-top:14px">${feedbackHTML({ ...en.feedback, grammar: en.grammar }, { showWords: false })}</div>` : ""}
    </details>`).join("") || `<div class="card empty">No entries yet. Your journal history will show up here.</div>`;
}

// ---------- boot ----------
(async () => {
  await initLevels();
  await loadToday();
  refreshDue();
})();
