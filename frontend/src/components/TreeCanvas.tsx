import { useState } from "react";

import { childrenOf, kindLabel, risksForActivity, safeguardsForRisk, topLevel } from "../lookups";
import type { Activity, MutationResult, Risk, Safeguard, ViewModel } from "../types";
import type { ModalTarget } from "../App";

type Run = (path: string, body?: Record<string, unknown>) => Promise<MutationResult | null>;

const INDENT = 20;

/** The dominant surface: one tree where activities, the risks they face, and the safeguards that
 *  mitigate them read as a single outline. Rows are differentiated by entity type; clicking a row
 *  opens its inspector modal, and hover exposes the fast add/delete actions. */
export function TreeCanvas({
  model,
  run,
  open,
  onImport,
}: {
  model: ViewModel;
  run: Run;
  open: (t: ModalTarget) => void;
  onImport: () => void;
}) {
  // Collapse state keyed per entity: `a:<id>` for an activity's body, `r:<aid>:<rid>` for a risk's
  // safeguards. Absent = expanded, so the whole model is visible by default (that's the point).
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const tops = topLevel(model);

  const addRoot = async () => {
    const res = await run("/api/activity/add", { parent_id: null, label: "New activity" });
    if (res?.created_id) open({ kind: "activity", activityId: res.created_id });
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Activity model</h2>
        <div className="canvas-tools">
          <button className="btn ghost small" onClick={addRoot}>
            ＋ Root activity
          </button>
          <button className="btn ghost small" onClick={onImport}>
            ⤵ Import…
          </button>
        </div>
      </div>
      <p className="sub">
        Activities, the <b>risks</b> each faces, and the <b>safeguards</b> that mitigate them — one
        outline. Click any item to inspect or edit it.
      </p>

      {tops.length === 0 ? (
        <div className="empty">
          <p>No activities yet.</p>
          <button className="btn primary" onClick={addRoot}>
            Add your first activity
          </button>
        </div>
      ) : (
        <div className="tree">
          {tops.map((a) => (
            <ActivityNode
              key={a.id}
              model={model}
              activity={a}
              depth={0}
              run={run}
              open={open}
              collapsed={collapsed}
              toggle={toggle}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ActivityNode({
  model,
  activity,
  depth,
  run,
  open,
  collapsed,
  toggle,
}: {
  model: ViewModel;
  activity: Activity;
  depth: number;
  run: Run;
  open: (t: ModalTarget) => void;
  collapsed: Set<string>;
  toggle: (key: string) => void;
}) {
  const kids = childrenOf(model, activity.id);
  const risks = risksForActivity(model, activity.id);
  const key = `a:${activity.id}`;
  const isCollapsed = collapsed.has(key);
  const hasBody = kids.length > 0 || risks.length > 0;

  const addChild = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const res = await run("/api/activity/add", { parent_id: activity.id, label: "New activity" });
    if (res?.created_id) open({ kind: "activity", activityId: res.created_id });
  };
  const del = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const n = activity.child_ids.length;
    const what = n
      ? `"${activity.label}" and its ${n} sub-activit${n === 1 ? "y" : "ies"}`
      : `"${activity.label}"`;
    if (confirm(`Delete ${what}? This also removes its risk and mitigation links.`))
      await run("/api/activity/delete", { id: activity.id });
  };

  return (
    <>
      <div
        className="entity-row activity"
        style={{ paddingLeft: 8 + depth * INDENT }}
        onClick={() => open({ kind: "activity", activityId: activity.id })}
      >
        <Caret shown={hasBody} collapsed={isCollapsed} onClick={() => toggle(key)} />
        <span className="etype activity">▣</span>
        <span className="entity-label">{activity.label || "(untitled)"}</span>
        <span className="badges">
          {activity.risk_count > 0 && (
            <span className="badge risk" title="risks faced">
              ⚠ {activity.risk_count}
            </span>
          )}
          {activity.mitigation_count > 0 && (
            <span className="badge mit" title="mitigations">
              ✓ {activity.mitigation_count}
            </span>
          )}
        </span>
        <span className="row-actions">
          <button className="icon-btn" title="Add sub-activity" onClick={addChild}>
            ＋
          </button>
          <button className="icon-btn danger" title="Delete" onClick={del}>
            ✕
          </button>
        </span>
      </div>

      {!isCollapsed && (
        <>
          {risks.map((r) => (
            <RiskNode
              key={r.id}
              model={model}
              activity={activity}
              risk={r}
              depth={depth + 1}
              open={open}
              collapsed={collapsed}
              toggle={toggle}
            />
          ))}
          {kids.map((c) => (
            <ActivityNode
              key={c.id}
              model={model}
              activity={c}
              depth={depth + 1}
              run={run}
              open={open}
              collapsed={collapsed}
              toggle={toggle}
            />
          ))}
        </>
      )}
    </>
  );
}

function RiskNode({
  model,
  activity,
  risk,
  depth,
  open,
  collapsed,
  toggle,
}: {
  model: ViewModel;
  activity: Activity;
  risk: Risk;
  depth: number;
  open: (t: ModalTarget) => void;
  collapsed: Set<string>;
  toggle: (key: string) => void;
}) {
  const sgs = safeguardsForRisk(model, activity.id, risk.id);
  const key = `r:${activity.id}:${risk.id}`;
  const isCollapsed = collapsed.has(key);

  return (
    <>
      <div
        className="entity-row risk"
        style={{ paddingLeft: 8 + depth * INDENT }}
        onClick={() => open({ kind: "risk", activityId: activity.id, riskId: risk.id })}
      >
        <Caret shown={sgs.length > 0} collapsed={isCollapsed} onClick={() => toggle(key)} />
        <span className="etype risk">⚠</span>
        <span className="entity-label">{risk.label}</span>
        <span className="entity-sub">
          {sgs.length ? `${sgs.length} safeguard${sgs.length === 1 ? "" : "s"}` : "unmitigated"}
        </span>
        <span className="row-actions" aria-hidden />
      </div>

      {!isCollapsed &&
        sgs.map((s) => (
          <SafeguardNode key={s.id} safeguard={s} depth={depth + 1} onClick={() => open({ kind: "safeguard", activityId: activity.id, riskId: risk.id, safeguardId: s.id })} />
        ))}
    </>
  );
}

function SafeguardNode({
  safeguard,
  depth,
  onClick,
}: {
  safeguard: Safeguard;
  depth: number;
  onClick: () => void;
}) {
  return (
    <div className="entity-row safeguard" style={{ paddingLeft: 8 + depth * INDENT }} onClick={onClick}>
      <span className="caret spacer" />
      <span className="etype safeguard">✓</span>
      <span className="entity-label">{safeguard.label}</span>
      <span className={`pill ${safeguard.kind}`}>{kindLabel(safeguard.kind)}</span>
      <span className={`pill ${safeguard.measures}`}>{safeguard.measures}</span>
      <span className={`reuse${safeguard.used_by > 1 ? " shared" : ""}`}>reused ×{safeguard.used_by}</span>
      <span className="row-actions" aria-hidden />
    </div>
  );
}

function Caret({ shown, collapsed, onClick }: { shown: boolean; collapsed: boolean; onClick: () => void }) {
  if (!shown) return <span className="caret spacer" />;
  return (
    <button
      className={`caret${collapsed ? " collapsed" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      ▾
    </button>
  );
}
