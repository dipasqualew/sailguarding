"""Renders the single, self-contained dashboard page.

One string of HTML with inline CSS and JS — no build step, no external assets, no CDN — matching
the engine's stdlib-only, offline-friendly posture. Server-computed initial state is embedded as
``window.__INITIAL__`` so the first paint is fully populated before any fetch runs; moving a slider
re-scores against the live API.

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
<title>sailguarding — delegation scoring</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #0f1216; --panel: #171b21; --panel-2: #1e242c; --line: #2a323c;
  --ink: #e7edf3; --muted: #9aa7b4; --accent: #5ac8fa; --good: #4ade80;
  --warn: #fbbf24; --bad: #f87171; --bar-bg: #232b34;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f4f6f9; --panel: #ffffff; --panel-2: #f0f3f7; --line: #dce2ea;
    --ink: #16202b; --muted: #5c6b7a; --accent: #0a84c2; --good: #16a34a;
    --warn: #b45309; --bad: #dc2626; --bar-bg: #e6ebf1;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 1040px; margin: 0 auto; padding: 32px 20px 64px; }
header h1 { margin: 0 0 4px; font-size: 22px; letter-spacing: -0.01em; }
header p { margin: 0; color: var(--muted); }
.tag { display: inline-block; font-size: 12px; color: var(--muted); border: 1px solid var(--line);
  border-radius: 999px; padding: 1px 9px; margin-left: 8px; vertical-align: middle; }
.grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 20px; margin-top: 24px; }
@media (max-width: 820px) { .grid { grid-template-columns: 1fr; } }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 20px; }
.panel h2 { margin: 0 0 2px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted); font-weight: 600; }
.panel .sub { margin: 0 0 16px; color: var(--muted); font-size: 13px; }

.floatbox { display: flex; align-items: baseline; gap: 14px; margin: 6px 0 4px; }
.floatbox .num { font-size: 54px; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.floatbox .of { color: var(--muted); font-size: 15px; }
.binding { color: var(--muted); font-size: 13px; margin: 0 0 18px; }
.binding b { color: var(--ink); }

.control { margin: 14px 0; }
.control label { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; }
.control label .val { font-variant-numeric: tabular-nums; color: var(--accent); font-weight: 600; }
input[type=range] { width: 100%; accent-color: var(--accent); }

.bars { margin-top: 18px; display: grid; gap: 10px; }
.bar { display: grid; grid-template-columns: 150px 1fr 48px; align-items: center; gap: 10px; font-size: 13px; }
.bar .name { color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar .name.bind { color: var(--ink); font-weight: 600; }
.track { display: block; background: var(--bar-bg); border-radius: 6px; height: 14px; overflow: hidden; }
.fill { display: block; height: 100%; border-radius: 6px; background: var(--good); transition: width .18s ease; }
.fill.bind { background: var(--accent); }
.fill.low { background: var(--bad); }
.cap { text-align: right; font-variant-numeric: tabular-nums; }
.rationale { font-size: 11px; color: var(--muted); grid-column: 2 / 4; margin-top: -4px; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
td code { font-size: 12px; color: var(--ink); }
.pill { font-size: 11px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line); }
.pill.matched { color: var(--good); border-color: color-mix(in srgb, var(--good) 45%, transparent); }
.pill.unmatched { color: var(--muted); }
.pill.ambiguous { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 45%, transparent); }
.pill.structural { color: var(--good); border-color: color-mix(in srgb, var(--good) 45%, transparent); }
.pill.human_dependent { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 45%, transparent); }
.pill.health { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.pill.efficacy { color: var(--ink); border-color: var(--muted); }

.sg-list { display: grid; gap: 10px; }
.sg { display: grid; grid-template-columns: 20px 1fr auto; align-items: center; gap: 12px;
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 10px;
  padding: 11px 13px; cursor: pointer; transition: opacity .15s ease; }
.sg.off { opacity: 0.45; }
.sg input[type=checkbox] { width: 16px; height: 16px; accent-color: var(--accent); cursor: pointer; }
.sg .sg-name { font-weight: 600; }
.sg .sg-sel { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }
.sg .sg-sel code { font-size: 12px; }
.sg .sg-tags { display: flex; gap: 6px; white-space: nowrap; }

.log { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; max-height: 320px; overflow: auto; }
.log li { display: flex; justify-content: space-between; align-items: center; gap: 10px;
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 8px 11px; }
.log .s { font-weight: 700; font-variant-numeric: tabular-nums; }
.log .meta { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.count { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
footer { margin-top: 28px; color: var(--muted); font-size: 12px; }
footer code { color: var(--ink); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>sailguarding <span class="tag">delegation scoring demo</span></h1>
    <p>How much of this action should the agent do? The float is computed by the team's scoring
      function — the platform only assembles the inputs and logs the decision.</p>
  </header>

  <div class="panel" style="margin-top:24px">
    <h2>Observe → classify <span class="tag">tasks 01–04</span></h2>
    <p class="sub">Raw tool events resolved to actions by the deterministic selector engine.</p>
    <table id="pipeline"><thead><tr><th>Tool</th><th>Input</th><th>Outcome</th><th>Action</th></tr></thead>
      <tbody></tbody></table>
  </div>

  <div class="panel" style="margin-top:20px">
    <h2>Govern → safeguards <span class="tag">task 06</span></h2>
    <p class="sub">The binding registry resolves which safeguards govern
      <code>write-tests</code> in <code>repo=checkout</code>. Each carries its structural /
      human-dependent tag and health / efficacy label. Toggle one off to remove its ceiling from
      the score — proof that the registry decides what reaches the scorer.</p>
    <div class="sg-list" id="safeguards"></div>
  </div>

  <div class="grid">
    <div class="panel">
      <h2>Score → delegation float <span class="tag">task 05</span></h2>
      <p class="sub">min-composition: each safeguard sets a ceiling; the weakest binds. Move the
        inputs — watch impact cap hard and budget pull the float down.</p>

      <div class="floatbox"><span class="num" id="score">0.00</span><span class="of">/ 1.00 delegation</span></div>
      <p class="binding">Binding constraint: <b id="binding">—</b> · <span id="fn">min-composition</span></p>

      <div class="control">
        <label>Blast radius <span class="val"><span id="impact-v"></span> svc</span></label>
        <input type="range" id="impact" min="0" max="__IMPACT_MAX__" step="1">
      </div>
      <div class="control">
        <label>Flakiness <span class="val"><span id="flakiness-v"></span>%</span></label>
        <input type="range" id="flakiness" min="0" max="__FLAKINESS_MAX_PCT__" step="0.1">
      </div>
      <div class="control">
        <label>Remaining error budget <span class="val"><span id="budget-v"></span>%</span></label>
        <input type="range" id="budget" min="0" max="100" step="1">
      </div>

      <div class="bars" id="bars"></div>
    </div>

    <div class="panel">
      <h2>Decision log <span class="tag">auditable</span></h2>
      <p class="sub">Every score is logged with its inputs, function version, and timestamp — so
        "why 0.90?" is answerable months later.</p>
      <p class="count"><span id="count">0</span> decisions this session</p>
      <ul class="log" id="log"></ul>
    </div>
  </div>

  <footer>
    Stdlib-only, zero-dependency. Served by <code>python -m sailguarding.web</code>. The scorer,
    classifier, and decision log are the real engine — this page is only a view.
  </footer>
</div>

<script>
const INITIAL = window.__INITIAL__ = __INITIAL_JSON__;
const PIPELINE = __PIPELINE_JSON__;
const FLAKINESS_MAX = __FLAKINESS_MAX__;   // fraction
const SAFEGUARDS = __SAFEGUARDS_JSON__;

function renderPipeline() {
  const tb = document.querySelector("#pipeline tbody");
  tb.innerHTML = PIPELINE.map(r => `<tr>
    <td><code>${r.tool}</code></td>
    <td><code>${r.input}</code></td>
    <td><span class="pill ${r.outcome}">${r.outcome}</span></td>
    <td>${r.action_id ? "<code>"+r.action_id+"</code>" : "—"}</td></tr>`).join("");
}

const disabled = new Set();  // safeguard ids toggled off; drives which ceilings reach the scorer

function kindLabel(k) { return k === "human_dependent" ? "human-dependent" : k; }

function renderSafeguards(list) {
  document.getElementById("safeguards").innerHTML = (list || []).map(s => `
    <label class="sg ${s.enabled ? "" : "off"}">
      <input type="checkbox" data-sg="${s.id}" ${s.enabled ? "checked" : ""}>
      <span class="sg-main">
        <span class="sg-name">${s.label}</span>
        <span class="sg-sel"><code>${s.selector}</code> · metric <code>${s.metric}</code></span>
      </span>
      <span class="sg-tags">
        <span class="pill ${s.kind}">${kindLabel(s.kind)}</span>
        <span class="pill ${s.measures}">${s.measures}</span>
      </span>
    </label>`).join("");
  document.querySelectorAll("#safeguards input[type=checkbox]").forEach(cb =>
    cb.addEventListener("change", onToggle));
}

function onToggle(e) {
  const id = e.target.getAttribute("data-sg");
  if (e.target.checked) disabled.delete(id); else disabled.add(id);
  rescore();
}

function renderScore(d) {
  document.getElementById("score").textContent = d.score.toFixed(2);
  document.getElementById("binding").textContent = d.binding;
  document.getElementById("fn").textContent = d.function.name + " v" + d.function.version;
  document.getElementById("count").textContent = d.decisions_logged;
  renderSafeguards(d.safeguards);

  const bars = d.ceilings.map(c => {
    const pct = Math.round(c.ceiling * 100);
    const cls = c.binding ? "bind" : (c.ceiling < 0.34 ? "low" : "");
    const val = c.id === "remaining-budget" || c.unit === "%"
      ? Math.round(c.value * (c.id === "remaining-budget" ? 100 : 100)) + c.unit
      : (c.value + c.unit);
    return `<div class="bar">
      <span class="name ${c.binding ? "bind" : ""}">${c.label}</span>
      <span class="track"><span class="fill ${cls}" style="width:${pct}%"></span></span>
      <span class="cap">${c.ceiling.toFixed(2)}</span>
      <span class="rationale">${c.rationale}</span>
    </div>`;
  }).join("");
  document.getElementById("bars").innerHTML = bars;
}

let logItems = [];
function renderLog() {
  document.getElementById("log").innerHTML = logItems.map(i => `<li>
    <span class="s">${i.score.toFixed(2)}</span>
    <span class="meta">budget ${Math.round(i.budget*100)}% · v${i.v} · ${i.ts.slice(11,19)}Z</span>
  </li>`).join("");
}
function seedLog(recent) {
  logItems = (recent || []).map(r => ({ score: r.score, v: r.function_version,
    ts: r.timestamp, budget: r.remaining_budget }));
  renderLog();
}
function pushLog(d) {
  logItems.unshift({ score: d.score, v: d.function.version, ts: d.timestamp,
                     budget: d.features.remaining_budget });
  logItems = logItems.slice(0, 12);
  renderLog();
}

function readInputs() {
  const params = {
    impact: document.getElementById("impact").value,
    flakiness: (parseFloat(document.getElementById("flakiness").value) / 100).toString(),
    budget: (parseInt(document.getElementById("budget").value, 10) / 100).toString(),
  };
  if (disabled.size) params.disabled = [...disabled].join(",");
  return params;
}
function syncLabels() {
  document.getElementById("impact-v").textContent = document.getElementById("impact").value;
  document.getElementById("flakiness-v").textContent =
    parseFloat(document.getElementById("flakiness").value).toFixed(1);
  document.getElementById("budget-v").textContent = document.getElementById("budget").value;
}

let timer = null;
async function rescore() {
  syncLabels();
  const q = new URLSearchParams(readInputs()).toString();
  const res = await fetch("/api/score?" + q);
  const d = await res.json();
  renderScore(d); pushLog(d);
}
function onInput() { clearTimeout(timer); syncLabels(); timer = setTimeout(rescore, 90); }

// Seed sliders from the server-computed initial features, then paint from embedded state.
(function init() {
  const f = INITIAL.features;
  const impact = f.signals.find(s => s.safeguard_id === "impact");
  const flak = f.signals.find(s => s.safeguard_id === "no-flaky-tests");
  document.getElementById("impact").value = impact ? impact.value : 1;
  document.getElementById("flakiness").value = flak ? (flak.value * 100).toFixed(1) : 0.4;
  document.getElementById("budget").value = Math.round(f.remaining_budget * 100);
  syncLabels();
  renderPipeline();
  renderScore(INITIAL);
  seedLog(INITIAL.recent);
  ["impact", "flakiness", "budget"].forEach(id =>
    document.getElementById(id).addEventListener("input", onInput));
})();
</script>
</body>
</html>
"""


def render_page(
    *,
    initial_score: dict[str, Any],
    pipeline: list[dict[str, Any]],
    safeguards: list[dict[str, Any]],
    flakiness_max: float,
    impact_max: float,
) -> str:
    """Fill the template with server-computed state and return the full HTML document."""
    subs = {
        "__INITIAL_JSON__": json.dumps(initial_score),
        "__PIPELINE_JSON__": json.dumps(pipeline),
        "__SAFEGUARDS_JSON__": json.dumps(safeguards),
        "__FLAKINESS_MAX__": json.dumps(flakiness_max),
        "__FLAKINESS_MAX_PCT__": _trim(flakiness_max * 100),
        "__IMPACT_MAX__": _trim(impact_max),
    }
    html = _TEMPLATE
    for token, value in subs.items():
        html = html.replace(token, value)
    return html


def _trim(value: float) -> str:
    """Render a float without a trailing ``.0`` for clean HTML attributes."""
    return str(int(value)) if value == int(value) else str(value)
