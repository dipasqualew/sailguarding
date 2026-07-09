"""Renders the single, self-contained activity-model editor page.

One string of HTML with inline CSS and JS — no build step, no external assets, no CDN — matching the
engine's stdlib-only, offline-friendly posture. The current view model is embedded as
``window.__MODEL__`` so the first paint is fully populated before any fetch runs; every edit POSTs a
mutation and re-renders from the model the server returns.

The template uses opaque ``__TOKEN__`` placeholders filled by :func:`render_page`, so the CSS/JS
braces need no escaping.
"""

from __future__ import annotations

import json
from typing import Any

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sailguarding — activity model</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #0f1216; --panel: #171b21; --panel-2: #1e242c; --line: #2a323c;
  --ink: #e7edf3; --muted: #9aa7b4; --accent: #5ac8fa; --good: #4ade80;
  --warn: #fbbf24; --bad: #f87171; --sel: #22303c; --chip: #202832;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f4f6f9; --panel: #ffffff; --panel-2: #f0f3f7; --line: #dce2ea;
    --ink: #16202b; --muted: #5c6b7a; --accent: #0a84c2; --good: #16a34a;
    --warn: #b45309; --bad: #dc2626; --sel: #e2edf6; --chip: #eef2f7;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0f1216; --panel: #171b21; --panel-2: #1e242c; --line: #2a323c;
  --ink: #e7edf3; --muted: #9aa7b4; --accent: #5ac8fa; --good: #4ade80;
  --warn: #fbbf24; --bad: #f87171; --sel: #22303c; --chip: #202832;
}
:root[data-theme="light"] {
  color-scheme: light;
  --bg: #f4f6f9; --panel: #ffffff; --panel-2: #f0f3f7; --line: #dce2ea;
  --ink: #16202b; --muted: #5c6b7a; --accent: #0a84c2; --good: #16a34a;
  --warn: #b45309; --bad: #dc2626; --sel: #e2edf6; --chip: #eef2f7;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 28px 20px 72px; }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
header h1 { margin: 0 0 4px; font-size: 22px; letter-spacing: -0.01em; }
header h1 .tag { font-size: 12px; color: var(--muted); border: 1px solid var(--line);
  border-radius: 999px; padding: 1px 9px; margin-left: 8px; vertical-align: middle; font-weight: 400; }
header p { margin: 0; color: var(--muted); max-width: 74ch; }
.theme-toggle { flex: none; background: var(--panel); color: var(--muted); border: 1px solid var(--line);
  border-radius: 999px; padding: 6px 13px; font: inherit; font-size: 13px; cursor: pointer; }
.theme-toggle:hover { color: var(--ink); border-color: var(--accent); }

.toast { position: fixed; left: 50%; bottom: 26px; transform: translateX(-50%) translateY(20px);
  background: var(--bad); color: #fff; padding: 9px 16px; border-radius: 10px; font-size: 13px;
  box-shadow: 0 8px 30px rgba(0,0,0,.28); opacity: 0; pointer-events: none; transition: all .2s ease; z-index: 50; }
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

.grid { display: grid; grid-template-columns: 1fr 1.15fr; gap: 20px; margin-top: 22px; align-items: start; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px 18px 20px; }
.panel > h2 { margin: 0 0 2px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted); font-weight: 600; }
.panel > .sub { margin: 0 0 14px; color: var(--muted); font-size: 13px; }

/* --- Tree ------------------------------------------------------------------------------------- */
.tree { display: flex; flex-direction: column; gap: 3px; }
.node-row { display: flex; align-items: center; gap: 6px; border-radius: 9px; padding: 6px 8px;
  cursor: pointer; border: 1px solid transparent; transition: background .12s ease; }
.node-row:hover { background: var(--panel-2); }
.node-row.selected { background: var(--sel); border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.caret { flex: none; width: 16px; height: 16px; display: inline-flex; align-items: center; justify-content: center;
  color: var(--muted); font-size: 10px; border: 0; background: none; cursor: pointer; transition: transform .12s ease; }
.caret.spacer { visibility: hidden; }
.caret.collapsed { transform: rotate(-90deg); }
.node-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.node-badges { display: flex; gap: 5px; flex: none; }
.badge { font-size: 11px; font-variant-numeric: tabular-nums; border-radius: 999px; padding: 0 7px;
  line-height: 18px; border: 1px solid var(--line); color: var(--muted); background: var(--chip); }
.badge.risk { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 40%, transparent); }
.badge.mit { color: var(--good); border-color: color-mix(in srgb, var(--good) 40%, transparent); }
.badge:empty { display: none; }
.node-actions { display: none; gap: 2px; flex: none; }
.node-row:hover .node-actions, .node-row.selected .node-actions { display: flex; }
.icon-btn { border: 0; background: none; color: var(--muted); cursor: pointer; font-size: 13px;
  width: 24px; height: 24px; border-radius: 6px; line-height: 1; }
.icon-btn:hover { background: var(--panel); color: var(--ink); }
.icon-btn.danger:hover { color: var(--bad); }
.rename-input, .inline-input { font: inherit; font-size: 14px; background: var(--bg); color: var(--ink);
  border: 1px solid var(--accent); border-radius: 7px; padding: 4px 8px; width: 100%; }
.tree-add { margin-top: 12px; }
.empty { text-align: center; color: var(--muted); padding: 26px 10px; }
.empty p { margin: 0 0 12px; }

.btn { font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; border-radius: 8px;
  border: 1px solid var(--line); background: var(--panel-2); color: var(--ink); padding: 7px 12px; }
.btn:hover { border-color: var(--accent); }
.btn.primary { background: var(--accent); color: #06222f; border-color: var(--accent); }
.btn.primary:hover { filter: brightness(1.07); }
.btn.small { padding: 4px 9px; font-size: 12px; }
.btn.ghost { background: none; border-style: dashed; color: var(--muted); }
.btn.ghost:hover { color: var(--ink); }

/* --- Detail ----------------------------------------------------------------------------------- */
.detail-title { font-size: 18px; font-weight: 700; margin: 0 0 2px; letter-spacing: -0.01em; }
.detail-path { color: var(--muted); font-size: 12px; margin: 0 0 16px; }
.risk-card { border: 1px solid var(--line); border-radius: 11px; background: var(--panel-2); margin-bottom: 10px; }
.risk-head { display: flex; align-items: center; gap: 10px; padding: 11px 13px; cursor: pointer; }
.risk-head .caret { color: var(--muted); }
.risk-name { font-weight: 600; flex: 1; min-width: 0; }
.reuse { font-size: 11px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px;
  padding: 0 8px; line-height: 18px; white-space: nowrap; }
.risk-body { padding: 0 13px 13px 35px; display: none; }
.risk-card.open .risk-body { display: block; }
.risk-card.open .risk-head .caret { transform: none; }
.risk-card .risk-head .caret { transform: rotate(-90deg); }
.sg-row { display: flex; align-items: center; gap: 8px; padding: 7px 0; border-top: 1px solid var(--line); }
.sg-row:first-child { border-top: 0; }
.sg-name { font-weight: 500; }
.sg-none { color: var(--muted); font-size: 13px; padding: 7px 0; }
.pill { font-size: 11px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line);
  white-space: nowrap; color: var(--muted); }
.pill.structural { color: var(--good); border-color: color-mix(in srgb, var(--good) 45%, transparent); }
.pill.human_dependent { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 45%, transparent); }
.pill.health { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.pill.efficacy { color: var(--ink); border-color: var(--muted); }
.spacer-x { flex: 1; }

.picker { margin-top: 8px; padding: 12px; border: 1px dashed var(--line); border-radius: 10px; background: var(--panel); }
.picker.hidden { display: none; }
.picker .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 8px; }
.picker .row:last-child { margin-bottom: 0; }
.picker label { font-size: 12px; color: var(--muted); }
select, input[type=text] { font: inherit; font-size: 13px; background: var(--bg); color: var(--ink);
  border: 1px solid var(--line); border-radius: 8px; padding: 7px 9px; }
input[type=text] { flex: 1; min-width: 150px; }
select { flex: 1; min-width: 140px; }
.picker-tabs { display: flex; gap: 4px; margin-bottom: 10px; }
.picker-tabs button { font: inherit; font-size: 12px; font-weight: 600; padding: 5px 11px; border-radius: 7px;
  border: 1px solid var(--line); background: none; color: var(--muted); cursor: pointer; }
.picker-tabs button.active { background: var(--panel-2); color: var(--ink); border-color: var(--accent); }

/* --- Library ---------------------------------------------------------------------------------- */
.lib-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
@media (max-width: 720px) { .lib-grid { grid-template-columns: 1fr; } }
.lib-list { display: flex; flex-direction: column; gap: 8px; }
.lib-item { display: flex; align-items: center; gap: 10px; background: var(--panel-2); border: 1px solid var(--line);
  border-radius: 10px; padding: 9px 12px; }
.lib-item .lib-name { font-weight: 600; }
.lib-item .lib-desc { color: var(--muted); font-size: 12px; margin-top: 1px; }
.lib-item .lib-tags { display: flex; gap: 6px; }
.usedby { font-size: 11px; font-variant-numeric: tabular-nums; color: var(--muted);
  border: 1px solid var(--line); border-radius: 999px; padding: 0 8px; line-height: 18px; white-space: nowrap; }
.usedby.shared { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.lib-empty { color: var(--muted); font-size: 13px; }

/* --- Model switcher --------------------------------------------------------------------------- */
.models { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 18px; }
.model-pill { font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; border-radius: 999px;
  border: 1px solid var(--line); background: var(--panel); color: var(--muted); padding: 6px 13px;
  display: inline-flex; align-items: center; gap: 7px; }
.model-pill:hover { color: var(--ink); border-color: var(--accent); }
.model-pill.active { background: var(--sel); color: var(--ink);
  border-color: color-mix(in srgb, var(--accent) 55%, transparent); }
.model-pill .model-count { font-size: 11px; font-variant-numeric: tabular-nums; color: var(--muted);
  background: var(--chip); border-radius: 999px; padding: 0 6px; line-height: 16px; }
.model-pill.add { border-style: dashed; }
.model-actions { display: inline-flex; gap: 6px; margin-left: 4px; }

/* --- "Applies when" scope strip --------------------------------------------------------------- */
.scope-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-top: 12px;
  padding: 11px 13px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; }
.scope-lead { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted);
  font-weight: 600; margin-right: 3px; }
.scope-any { color: var(--muted); font-size: 13px; font-style: italic; }
.scope-dim { display: inline-flex; align-items: center; gap: 5px; background: var(--panel-2);
  border: 1px solid var(--line); border-radius: 10px; padding: 4px 6px 4px 9px; }
.scope-name { font-size: 12px; font-weight: 600; color: var(--accent); }
.scope-name::after { content: "∈"; color: var(--muted); margin-left: 5px; font-weight: 400; }
.scope-chip { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; background: var(--chip);
  border: 1px solid var(--line); border-radius: 999px; padding: 1px 5px 1px 9px; }
.scope-chip.any { color: var(--muted); font-style: italic; padding-right: 9px; }
.chip-x { border: 0; background: none; color: var(--muted); cursor: pointer; font-size: 13px;
  line-height: 1; padding: 0 2px; border-radius: 4px; }
.chip-x:hover { color: var(--bad); }
.scope-add { font: inherit; font-size: 12px; background: var(--bg); color: var(--ink);
  border: 1px dashed var(--line); border-radius: 8px; padding: 3px 7px; width: 84px; min-width: 0; flex: none; }
.scope-add:focus { border-color: var(--accent); outline: none; }

/* --- Import modal ----------------------------------------------------------------------------- */
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex;
  align-items: center; justify-content: center; z-index: 60; padding: 20px; }
.modal-backdrop.hidden { display: none; }
.modal { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 22px;
  width: 100%; max-width: 520px; box-shadow: 0 24px 60px rgba(0,0,0,.4); }
.modal h3 { margin: 0 0 4px; font-size: 17px; }
.modal .sub { margin: 0 0 16px; color: var(--muted); font-size: 13px; }
.modal .row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.modal .row > label { font-size: 12px; color: var(--muted); min-width: 74px; }
.modal select { flex: 1; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
.import-preview { font-size: 12px; color: var(--muted); background: var(--panel-2);
  border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; margin-bottom: 14px; }
.import-preview b { color: var(--ink); }

footer { margin-top: 30px; color: var(--muted); font-size: 12px; }
footer code { color: var(--ink); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>sailguarding <span class="tag">activity models</span></h1>
      <p>Model the work you hand to agents as a tree of activities, the risks each faces, and the
        safeguards that mitigate them. Keep a separate model per domain — switch between them, scope
        each to where it applies, and import activities, risks, or safeguards from one into another.</p>
    </div>
    <button class="theme-toggle" id="theme-toggle">Theme</button>
  </header>

  <div class="models" id="models"></div>
  <div class="scope-strip" id="scope-strip"></div>

  <div class="grid">
    <section class="panel">
      <h2>Activity tree</h2>
      <p class="sub">Click a node to inspect it. Hover for add / rename / delete.</p>
      <div class="tree" id="tree"></div>
      <div class="tree-add">
        <button class="btn ghost small" id="add-root">＋ Add root activity</button>
        <button class="btn ghost small" id="import-open">⤵ Import from another model…</button>
      </div>
    </section>

    <section class="panel" id="detail">
      <h2>Selected activity</h2>
      <p class="sub">Its risks, and the safeguards assigned to each.</p>
      <div id="detail-body"></div>
    </section>
  </div>

  <section class="lib-grid">
    <div class="panel">
      <h2>Risk library</h2>
      <p class="sub">Named once, faced by many. The count is how many activities reference each.</p>
      <div class="lib-list" id="risk-lib"></div>
    </div>
    <div class="panel">
      <h2>Safeguard library</h2>
      <p class="sub">One control can mitigate a risk across many activities — that is reuse.</p>
      <div class="lib-list" id="safeguard-lib"></div>
    </div>
  </section>

  <footer>
    Stdlib-only, zero-dependency. Served by <code>python -m sailguarding.web</code>. Every edit runs a
    real <code>ActivityModel</code> transform on the server and re-renders from the result.
  </footer>
</div>

<div class="modal-backdrop hidden" id="import-modal"></div>
<div class="toast" id="toast"></div>

<script>
"use strict";
let MODEL = window.__MODEL__ = __MODEL_JSON__;
let selectedId = null;
let activeId = MODEL.active_id;     // which model is showing; a change resets tree/selection state
const collapsed = new Set();       // activity ids whose children are hidden
const openRisks = new Set();       // "activityId::riskId" rows expanded in the detail pane

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 2600);
}

// --- API: every mutation POSTs JSON and re-renders from the returned model. --------------------
async function api(path, body) {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.error || ("request failed (" + res.status + ")")); return null; }
    MODEL = window.__MODEL__ = data.model;
    render();
    return data;
  } catch (e) {
    toast("network error — is the server still running?");
    return null;
  }
}

// --- Lookups over the flat view model. ---------------------------------------------------------
const activityById = (id) => MODEL.activities.find((a) => a.id === id) || null;
const riskById = (id) => MODEL.risks.find((r) => r.id === id) || null;
const safeguardById = (id) => MODEL.safeguards.find((s) => s.id === id) || null;
const topLevel = () => MODEL.activities.filter((a) => a.parent_id === null);
const childrenOf = (id) => MODEL.activities.filter((a) => a.parent_id === id);
const risksForActivity = (aid) =>
  MODEL.activity_risks.filter((e) => e[0] === aid).map((e) => riskById(e[1])).filter(Boolean);
const safeguardsForRisk = (aid, rid) =>
  MODEL.mitigations.filter((e) => e[0] === aid && e[1] === rid)
    .map((e) => safeguardById(e[2])).filter(Boolean);
const kindLabel = (k) => (k === "human_dependent" ? "human-dependent" : k);

// --- Tree pane. --------------------------------------------------------------------------------
function renderTree() {
  const root = $("tree");
  const tops = topLevel();
  if (!tops.length) {
    root.innerHTML =
      '<div class="empty"><p>No activities yet.</p>' +
      '<button class="btn primary" id="empty-add">Add your first activity</button></div>';
    $("empty-add").onclick = () => addActivity(null);
    return;
  }
  root.innerHTML = "";
  tops.forEach((n) => root.appendChild(nodeEl(n)));
}

function nodeEl(node) {
  const wrap = document.createElement("div");
  const row = document.createElement("div");
  row.className = "node-row" + (node.id === selectedId ? " selected" : "");
  row.style.paddingLeft = (8 + node.depth * 18) + "px";
  row.onclick = () => selectActivity(node.id);

  const kids = childrenOf(node.id);
  const isCollapsed = collapsed.has(node.id);
  const caret = document.createElement("button");
  caret.className = "caret" + (kids.length ? "" : " spacer") + (isCollapsed ? " collapsed" : "");
  caret.textContent = "▾";
  caret.onclick = (e) => { e.stopPropagation(); toggleCollapse(node.id); };

  const label = document.createElement("span");
  label.className = "node-label";
  label.textContent = node.label || "(untitled)";

  const badges = document.createElement("span");
  badges.className = "node-badges";
  badges.innerHTML =
    (node.risk_count ? '<span class="badge risk" title="risks faced">⚠ ' + node.risk_count + "</span>" : "") +
    (node.mitigation_count ? '<span class="badge mit" title="mitigations">✓ ' + node.mitigation_count + "</span>" : "");

  const actions = document.createElement("span");
  actions.className = "node-actions";
  actions.appendChild(iconBtn("＋", "Add child", (e) => { e.stopPropagation(); addActivity(node.id); }));
  actions.appendChild(iconBtn("✎", "Rename", (e) => { e.stopPropagation(); beginRename(row, node); }));
  actions.appendChild(iconBtn("✕", "Delete", (e) => { e.stopPropagation(); deleteActivity(node); }, true));

  row.append(caret, label, badges, actions);
  wrap.appendChild(row);

  if (kids.length && !isCollapsed) {
    kids.forEach((c) => wrap.appendChild(nodeEl(c)));
  }
  return wrap;
}

function iconBtn(glyph, title, onClick, danger) {
  const b = document.createElement("button");
  b.className = "icon-btn" + (danger ? " danger" : "");
  b.textContent = glyph;
  b.title = title;
  b.onclick = onClick;
  return b;
}

function toggleCollapse(id) {
  if (collapsed.has(id)) collapsed.delete(id); else collapsed.add(id);
  renderTree();
}

function selectActivity(id) { selectedId = id; render(); }

function beginRename(row, node) {
  const input = document.createElement("input");
  input.className = "rename-input";
  input.value = node.label;
  row.innerHTML = "";
  row.style.paddingLeft = (8 + node.depth * 18) + "px";
  row.appendChild(input);
  input.focus();
  input.select();
  let done = false;
  const commit = async () => {
    if (done) return; done = true;
    const label = input.value.trim();
    if (label && label !== node.label) await api("/api/activity/rename", { id: node.id, label });
    else render();
  };
  input.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    else if (e.key === "Escape") { done = true; render(); }
  };
  input.onblur = commit;
}

async function addActivity(parentId) {
  const data = await api("/api/activity/add", { parent_id: parentId, label: "New activity" });
  if (data && data.created_id) {
    if (parentId) collapsed.delete(parentId);
    selectedId = data.created_id;
    render();
    // Drop the fresh node straight into rename so the placeholder is never left behind.
    const row = document.querySelector(".node-row.selected");
    const node = activityById(data.created_id);
    if (row && node) beginRename(row, node);
  }
}

async function deleteActivity(node) {
  const kids = childrenOf(node.id).length;
  const warn = kids
    ? '"' + node.label + '" and its ' + kids + " sub-activit" + (kids === 1 ? "y" : "ies")
    : '"' + node.label + '"';
  if (!confirm("Delete " + warn + "? This also removes its risk and mitigation links.")) return;
  if (selectedId === node.id) selectedId = null;
  await api("/api/activity/delete", { id: node.id });
}

// --- Detail pane. ------------------------------------------------------------------------------
function renderDetail() {
  const body = $("detail-body");
  const activity = selectedId ? activityById(selectedId) : null;
  if (!activity) {
    body.innerHTML = '<div class="empty"><p>Select an activity to see its risks and safeguards.</p></div>';
    return;
  }
  const risks = risksForActivity(activity.id);
  const ancestry = pathLabels(activity).join("  ›  ");
  let html = '<div class="detail-title">' + esc(activity.label || "(untitled)") + "</div>";
  html += '<div class="detail-path">' + (ancestry ? esc(ancestry) : "top-level activity") + "</div>";

  if (!risks.length) {
    html += '<div class="sg-none">No risks recorded for this activity yet.</div>';
  } else {
    html += risks.map((r) => riskCard(activity.id, r)).join("");
  }
  html += '<div style="margin-top:12px"><button class="btn ghost small" id="add-risk-btn">＋ Add risk</button></div>';
  html += '<div class="picker hidden" id="risk-picker"></div>';
  body.innerHTML = html;

  // Wire risk cards.
  risks.forEach((r) => {
    const key = activity.id + "::" + r.id;
    $("risk-head-" + r.id).onclick = () => {
      if (openRisks.has(key)) openRisks.delete(key); else openRisks.add(key);
      renderDetail();
    };
    $("detach-risk-" + r.id).onclick = (e) => {
      e.stopPropagation();
      api("/api/activity/risk/detach", { activity_id: activity.id, risk_id: r.id });
    };
    if (openRisks.has(key)) {
      $("assign-sg-btn-" + r.id).onclick = () => toggleSafeguardPicker(activity.id, r.id);
      safeguardsForRisk(activity.id, r.id).forEach((s) => {
        $("remove-mit-" + r.id + "-" + s.id).onclick = () =>
          api("/api/mitigation/remove", { activity_id: activity.id, risk_id: r.id, safeguard_id: s.id });
      });
    }
  });
  $("add-risk-btn").onclick = () => toggleRiskPicker(activity.id);
}

function pathLabels(activity) {
  const labels = [];
  let cur = activity;
  while (cur && cur.parent_id) { cur = activityById(cur.parent_id); if (cur) labels.unshift(cur.label); }
  return labels;
}

function riskCard(activityId, risk) {
  const key = activityId + "::" + risk.id;
  const open = openRisks.has(key);
  const sgs = safeguardsForRisk(activityId, risk.id);
  const body = open
    ? '<div class="risk-body">' +
        (sgs.length
          ? sgs.map((s) => sgRow(risk.id, s)).join("")
          : '<div class="sg-none">No safeguards assigned.</div>') +
        '<div style="margin-top:8px"><button class="btn ghost small" id="assign-sg-btn-' + risk.id + '">＋ Assign safeguard</button></div>' +
        '<div class="picker hidden" id="sg-picker-' + risk.id + '"></div>' +
      "</div>"
    : "";
  return (
    '<div class="risk-card' + (open ? " open" : "") + '">' +
      '<div class="risk-head" id="risk-head-' + risk.id + '">' +
        '<button class="caret">▾</button>' +
        '<span class="risk-name">' + esc(risk.label) + "</span>" +
        '<span class="reuse">used in ' + risk.used_by + " activit" + (risk.used_by === 1 ? "y" : "ies") + "</span>" +
        '<button class="icon-btn danger" id="detach-risk-' + risk.id + '" title="Detach risk">✕</button>' +
      "</div>" + body +
    "</div>"
  );
}

function sgRow(riskId, sg) {
  return (
    '<div class="sg-row">' +
      '<span class="sg-name">' + esc(sg.label) + "</span>" +
      '<span class="pill ' + sg.kind + '">' + kindLabel(sg.kind) + "</span>" +
      '<span class="pill ' + sg.measures + '">' + sg.measures + "</span>" +
      '<span class="usedby' + (sg.used_by > 1 ? " shared" : "") + '">reused ×' + sg.used_by + "</span>" +
      '<span class="spacer-x"></span>' +
      '<button class="icon-btn danger" id="remove-mit-' + riskId + "-" + sg.id + '" title="Unassign">✕</button>' +
    "</div>"
  );
}

// --- Add-risk picker: pick an existing library risk, or create a new one. ----------------------
function toggleRiskPicker(activityId) {
  const el = $("risk-picker");
  if (!el.classList.contains("hidden")) { el.classList.add("hidden"); return; }
  const attached = new Set(risksForActivity(activityId).map((r) => r.id));
  const available = MODEL.risks.filter((r) => !attached.has(r.id));
  const options = available.map((r) => '<option value="' + r.id + '">' + esc(r.label) +
    " (used ×" + r.used_by + ")</option>").join("");
  el.innerHTML =
    '<div class="picker-tabs">' +
      '<button class="active" data-mode="existing"' + (available.length ? "" : " disabled") + ">Existing</button>" +
      '<button data-mode="new">New risk</button>' +
    "</div>" +
    '<div data-pane="existing"' + (available.length ? "" : ' style="display:none"') + '>' +
      '<div class="row"><select id="risk-existing">' + options + "</select>" +
      '<button class="btn primary small" id="risk-attach">Attach</button></div></div>' +
    '<div data-pane="new"' + (available.length ? ' style="display:none"' : "") + '>' +
      '<div class="row"><input type="text" id="risk-new-label" placeholder="Risk name, e.g. Data loss"></div>' +
      '<div class="row"><input type="text" id="risk-new-desc" placeholder="Description (optional)">' +
      '<button class="btn primary small" id="risk-create">Create &amp; attach</button></div></div>';
  el.classList.remove("hidden");
  pickerTabs(el);
  const attach = $("risk-attach");
  if (attach) attach.onclick = () => {
    const rid = $("risk-existing").value;
    if (rid) api("/api/activity/risk/attach", { activity_id: activityId, risk_id: rid });
  };
  $("risk-create").onclick = async () => {
    const label = $("risk-new-label").value.trim();
    if (!label) { toast("Give the risk a name."); return; }
    const created = await api("/api/risk/create", { label, description: $("risk-new-desc").value.trim() });
    if (created && created.created_id)
      await api("/api/activity/risk/attach", { activity_id: activityId, risk_id: created.created_id });
  };
}

// --- Assign-safeguard picker: pick an existing safeguard, or create a new one. ------------------
function toggleSafeguardPicker(activityId, riskId) {
  const el = $("sg-picker-" + riskId);
  if (!el.classList.contains("hidden")) { el.classList.add("hidden"); return; }
  const assigned = new Set(safeguardsForRisk(activityId, riskId).map((s) => s.id));
  const available = MODEL.safeguards.filter((s) => !assigned.has(s.id));
  const options = available.map((s) => '<option value="' + s.id + '">' + esc(s.label) +
    " · " + kindLabel(s.kind) + " · " + s.measures + " (reused ×" + s.used_by + ")</option>").join("");
  el.innerHTML =
    '<div class="picker-tabs">' +
      '<button class="active" data-mode="existing"' + (available.length ? "" : " disabled") + ">Existing</button>" +
      '<button data-mode="new">New safeguard</button>' +
    "</div>" +
    '<div data-pane="existing"' + (available.length ? "" : ' style="display:none"') + '>' +
      '<div class="row"><select id="sg-existing-' + riskId + '">' + options + "</select>" +
      '<button class="btn primary small" id="sg-assign-' + riskId + '">Assign</button></div></div>' +
    '<div data-pane="new"' + (available.length ? ' style="display:none"' : "") + '>' +
      '<div class="row"><input type="text" id="sg-new-label-' + riskId + '" placeholder="Safeguard name"></div>' +
      '<div class="row"><label>Kind</label><select id="sg-new-kind-' + riskId + '">' +
        '<option value="structural">structural</option>' +
        '<option value="human_dependent">human-dependent</option></select>' +
        '<label>Measures</label><select id="sg-new-measures-' + riskId + '">' +
        '<option value="health">health</option><option value="efficacy">efficacy</option></select>' +
      "</div>" +
      '<div class="row"><button class="btn primary small" id="sg-create-' + riskId + '">Create &amp; assign</button></div></div>';
  el.classList.remove("hidden");
  pickerTabs(el);
  const assign = $("sg-assign-" + riskId);
  if (assign) assign.onclick = () => {
    const sid = $("sg-existing-" + riskId).value;
    if (sid) api("/api/mitigation/add", { activity_id: activityId, risk_id: riskId, safeguard_id: sid });
  };
  $("sg-create-" + riskId).onclick = async () => {
    const label = $("sg-new-label-" + riskId).value.trim();
    if (!label) { toast("Give the safeguard a name."); return; }
    const created = await api("/api/safeguard/create", {
      label,
      kind: $("sg-new-kind-" + riskId).value,
      measures: $("sg-new-measures-" + riskId).value,
    });
    if (created && created.created_id)
      await api("/api/mitigation/add", { activity_id: activityId, risk_id: riskId, safeguard_id: created.created_id });
  };
}

// Local existing/new tab switch inside a picker (no re-render, so typing state survives).
function pickerTabs(el) {
  const tabs = el.querySelectorAll(".picker-tabs button");
  tabs.forEach((btn) => {
    btn.onclick = () => {
      if (btn.disabled) return;
      tabs.forEach((b) => b.classList.toggle("active", b === btn));
      el.querySelectorAll("[data-pane]").forEach((p) => {
        p.style.display = p.getAttribute("data-pane") === btn.dataset.mode ? "" : "none";
      });
    };
  });
}

// --- Library section. --------------------------------------------------------------------------
function renderLibraries() {
  const rl = $("risk-lib");
  rl.innerHTML = MODEL.risks.length
    ? MODEL.risks.map((r) =>
        '<div class="lib-item"><div style="flex:1;min-width:0">' +
          '<div class="lib-name">' + esc(r.label) + "</div>" +
          (r.description ? '<div class="lib-desc">' + esc(r.description) + "</div>" : "") +
        "</div>" +
        '<span class="usedby' + (r.used_by > 1 ? " shared" : "") + '">used ×' + r.used_by + "</span></div>"
      ).join("")
    : '<div class="lib-empty">No risks yet — add one from an activity.</div>';

  const sl = $("safeguard-lib");
  sl.innerHTML = MODEL.safeguards.length
    ? MODEL.safeguards.map((s) =>
        '<div class="lib-item"><div style="flex:1;min-width:0">' +
          '<div class="lib-name">' + esc(s.label) + "</div>" +
          '<div class="lib-tags" style="margin-top:4px">' +
            '<span class="pill ' + s.kind + '">' + kindLabel(s.kind) + "</span>" +
            '<span class="pill ' + s.measures + '">' + s.measures + "</span>" +
          "</div></div>" +
        '<span class="usedby' + (s.used_by > 1 ? " shared" : "") + '">reused ×' + s.used_by + "</span></div>"
      ).join("")
    : '<div class="lib-empty">No safeguards yet — assign one to a risk.</div>';
}

// --- Model switcher. ---------------------------------------------------------------------------
const activeModelMeta = () => MODEL.models.find((m) => m.id === MODEL.active_id) || null;

function renderModels() {
  const bar = $("models");
  const pills = MODEL.models.map((m) =>
    '<button class="model-pill' + (m.id === MODEL.active_id ? " active" : "") + '" data-model="' + m.id + '">' +
      esc(m.name || "(unnamed model)") +
      '<span class="model-count" title="activities">' + m.activity_count + "</span>" +
    "</button>").join("");
  bar.innerHTML = pills +
    '<button class="model-pill add" id="model-add">＋ New model</button>' +
    '<span class="model-actions">' +
      '<button class="btn small ghost" id="model-rename">Rename</button>' +
      '<button class="btn small ghost" id="model-delete">Delete</button>' +
    "</span>";
  MODEL.models.forEach((m) => {
    bar.querySelector('.model-pill[data-model="' + m.id + '"]').onclick = () => {
      if (m.id !== MODEL.active_id) api("/api/model/select", { id: m.id });
    };
  });
  $("model-add").onclick = createModel;
  $("model-rename").onclick = renameActiveModel;
  $("model-delete").onclick = deleteActiveModel;
}

async function createModel() {
  const name = (prompt("Name the new activity model (e.g. Data Science):") || "").trim();
  if (name) await api("/api/model/add", { name });
}
async function renameActiveModel() {
  const meta = activeModelMeta();
  if (!meta) return;
  const name = (prompt("Rename this model:", meta.name) || "").trim();
  if (name && name !== meta.name) await api("/api/model/rename", { id: meta.id, name });
}
async function deleteActiveModel() {
  const meta = activeModelMeta();
  if (!meta) return;
  if (MODEL.models.length <= 1) { toast("Keep at least one model."); return; }
  if (confirm('Delete the "' + meta.name + '" model and everything in it?'))
    await api("/api/model/delete", { id: meta.id });
}

// --- "Applies when" scope strip. ---------------------------------------------------------------
const currentDimensions = () => (MODEL.applies_when.dimensions || []).map((d) => ({ name: d.name, values: [...d.values] }));
const saveScope = (dims) => api("/api/model/scope/set", { id: MODEL.active_id, dimensions: dims });

function renderScope() {
  const el = $("scope-strip");
  if (!MODEL.active_id) { el.innerHTML = ""; return; }
  const dims = MODEL.applies_when.dimensions || [];
  let html = '<span class="scope-lead">Applies when</span>';
  if (!dims.length) html += '<span class="scope-any">everywhere — no context restriction</span>';
  html += dims.map((d, i) =>
    '<span class="scope-dim">' +
      '<span class="scope-name">' + esc(d.name) + "</span>" +
      (d.values.length
        ? d.values.map((v, j) =>
            '<span class="scope-chip">' + esc(v) +
            '<button class="chip-x" data-dim="' + i + '" data-val="' + j + '" title="Remove value">×</button></span>').join("")
        : '<span class="scope-chip any">any value</span>') +
      '<input class="scope-add" data-dim="' + i + '" placeholder="+ value" autocomplete="off">' +
      '<button class="chip-x dim-x" data-dim="' + i + '" title="Remove dimension">✕</button>' +
    "</span>").join("");
  html += '<button class="btn small ghost" id="scope-add-dim">＋ dimension</button>';
  el.innerHTML = html;

  el.querySelectorAll(".chip-x:not(.dim-x)").forEach((b) => b.onclick = () => {
    const d = currentDimensions(); d[+b.dataset.dim].values.splice(+b.dataset.val, 1); saveScope(d);
  });
  el.querySelectorAll(".dim-x").forEach((b) => b.onclick = () => {
    const d = currentDimensions(); d.splice(+b.dataset.dim, 1); saveScope(d);
  });
  el.querySelectorAll(".scope-add").forEach((inp) => inp.onkeydown = (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const v = inp.value.trim();
    if (!v) return;
    const d = currentDimensions();
    if (d[+inp.dataset.dim].values.includes(v)) { toast("That value is already listed."); return; }
    d[+inp.dataset.dim].values.push(v); saveScope(d);
  });
  $("scope-add-dim").onclick = () => {
    const name = (prompt("Context dimension this model is scoped to (e.g. repo, team, environment):") || "").trim();
    if (!name) return;
    const d = currentDimensions();
    if (d.some((x) => x.name === name)) { toast("That dimension is already set."); return; }
    d.push({ name, values: [] }); saveScope(d);
  };
}

// --- Import-from-another-model dialog. ---------------------------------------------------------
function openImport() {
  const others = MODEL.models.filter((m) => m.id !== MODEL.active_id);
  if (!others.length) { toast("Add another model to import from."); return; }
  const target = activeModelMeta();
  const modal = $("import-modal");
  let sourceId = others[0].id;
  let kind = "activity";

  const sourceModel = () => MODEL.models.find((m) => m.id === sourceId);
  const entities = () => {
    const s = sourceModel();
    return kind === "activity" ? s.activities : kind === "risk" ? s.risks : s.safeguards;
  };

  function draw() {
    const list = entities();
    const sourceOpts = others.map((m) =>
      '<option value="' + m.id + '"' + (m.id === sourceId ? " selected" : "") + ">" + esc(m.name) + "</option>").join("");
    const entOpts = list.map((e) => {
      const pad = e.depth ? "\\u00a0\\u00a0".repeat(e.depth) + "↳ " : "";
      return '<option value="' + e.id + '">' + pad + esc(e.label) + "</option>";
    }).join("");
    modal.innerHTML =
      '<div class="modal">' +
        "<h3>Import into “" + esc(target ? target.name : "") + "”</h3>" +
        '<p class="sub">Copies the item in. The source model is left untouched.</p>' +
        '<div class="row"><label>From model</label><select id="imp-source">' + sourceOpts + "</select></div>" +
        '<div class="picker-tabs" id="imp-kinds">' +
          '<button data-kind="activity"' + (kind === "activity" ? ' class="active"' : "") + ">Activity</button>" +
          '<button data-kind="risk"' + (kind === "risk" ? ' class="active"' : "") + ">Risk</button>" +
          '<button data-kind="safeguard"' + (kind === "safeguard" ? ' class="active"' : "") + ">Safeguard</button>" +
        "</div>" +
        '<div class="row"><label>Item</label><select id="imp-entity">' +
          (entOpts || "<option value=''>— nothing to import —</option>") + "</select></div>" +
        (kind === "activity"
          ? '<div class="import-preview">Imports the activity <b>and</b> its sub-activities, the risks &amp; ' +
            "safeguards it references, and the edges wiring them — so it lands fully governed.</div>"
          : "") +
        '<div class="modal-foot">' +
          '<button class="btn" id="imp-cancel">Cancel</button>' +
          '<button class="btn primary" id="imp-go"' + (list.length ? "" : " disabled") + ">Import</button>" +
        "</div>" +
      "</div>";
    $("imp-source").onchange = (e) => { sourceId = e.target.value; draw(); };
    modal.querySelectorAll("#imp-kinds button").forEach((b) =>
      b.onclick = () => { kind = b.dataset.kind; draw(); });
    $("imp-cancel").onclick = closeImport;
    $("imp-go").onclick = async () => {
      const eid = $("imp-entity").value;
      if (!eid) return;
      const res = await api("/api/model/import",
        { target_id: MODEL.active_id, source_id: sourceId, kind, entity_id: eid });
      if (res) { closeImport(); toast("Imported into " + (target ? target.name : "model") + "."); }
    };
  }
  draw();
  modal.classList.remove("hidden");
  modal.onclick = (e) => { if (e.target === modal) closeImport(); };
}
function closeImport() { const m = $("import-modal"); m.classList.add("hidden"); m.innerHTML = ""; }

// --- Top-level render + boot. ------------------------------------------------------------------
function render() {
  // A model switch resets per-model view state and opens onto the new model's first activity.
  if (MODEL.active_id !== activeId) {
    activeId = MODEL.active_id;
    collapsed.clear();
    openRisks.clear();
    const first = topLevel()[0];
    selectedId = first ? first.id : null;
  }
  renderModels();
  renderScope();
  renderTree();
  renderDetail();
  renderLibraries();
}

(function init() {
  // Theme toggle: stamp data-theme so it wins over the prefers-color-scheme default in both directions.
  const toggle = $("theme-toggle");
  toggle.onclick = () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : cur === "light" ? "dark"
      : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
    document.documentElement.setAttribute("data-theme", next);
  };
  $("add-root").onclick = () => addActivity(null);
  $("import-open").onclick = openImport;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeImport(); });
  // Open onto the first top-level activity so the detail pane is populated on first paint.
  const first = topLevel()[0];
  if (first) selectedId = first.id;
  render();
})();
</script>
</body>
</html>
"""


def render_page(model: dict[str, Any]) -> str:
    """Fill the template with the embedded view model and return the full HTML document."""
    return _TEMPLATE.replace("__MODEL_JSON__", json.dumps(model))
