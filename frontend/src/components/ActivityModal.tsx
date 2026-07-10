import { useState } from "react";

import { pathLabels, risksForActivity } from "../lookups";
import type { MutationResult, ViewModel } from "../types";
import { Modal } from "./Modal";

type Run = (path: string, body?: Record<string, unknown>) => Promise<MutationResult | null>;

/** The activity inspector: rename, add a sub-activity, delete, and manage the risks it faces. */
export function ActivityModal({
  model,
  activityId,
  run,
  notify,
  openActivity,
  onClose,
}: {
  model: ViewModel;
  activityId: string;
  run: Run;
  notify: (msg: string) => void;
  openActivity: (id: string) => void;
  onClose: () => void;
}) {
  const activity = model.activities.find((a) => a.id === activityId);
  const [name, setName] = useState(activity?.label ?? "");
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [pick, setPick] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newDesc, setNewDesc] = useState("");

  // The activity vanished from under us (e.g. deleted) — close rather than render a stale shell.
  if (!activity) {
    onClose();
    return null;
  }

  const breadcrumb = pathLabels(model, activity).join("  ›  ") || "top-level activity";
  const attached = risksForActivity(model, activity.id);
  const attachedIds = new Set(attached.map((r) => r.id));
  const available = model.risks.filter((r) => !attachedIds.has(r.id));
  // No library risks left to attach → the "new risk" pane is the only useful one.
  const effectiveMode = available.length === 0 ? "new" : mode;

  const saveName = async () => {
    const label = name.trim();
    if (label && label !== activity.label) await run("/api/activity/rename", { id: activity.id, label });
  };

  const addChild = async () => {
    const res = await run("/api/activity/add", { parent_id: activity.id, label: "New activity" });
    if (res?.created_id) openActivity(res.created_id);
  };

  const del = async () => {
    const kids = activity.child_ids.length;
    const what = kids
      ? `"${activity.label}" and its ${kids} sub-activit${kids === 1 ? "y" : "ies"}`
      : `"${activity.label}"`;
    if (!confirm(`Delete ${what}? This also removes its risk and mitigation links.`)) return;
    const res = await run("/api/activity/delete", { id: activity.id });
    if (res) onClose();
  };

  const attachExisting = async () => {
    if (pick) await run("/api/activity/risk/attach", { activity_id: activity.id, risk_id: pick });
  };

  const createAndAttach = async () => {
    const label = newLabel.trim();
    if (!label) return notify("Give the risk a name.");
    const created = await run("/api/risk/create", { label, description: newDesc.trim() });
    if (created?.created_id) {
      await run("/api/activity/risk/attach", { activity_id: activity.id, risk_id: created.created_id });
      setNewLabel("");
      setNewDesc("");
    }
  };

  return (
    <Modal
      icon={<span className="etype activity">▣</span>}
      title="Activity"
      sub={breadcrumb}
      onClose={onClose}
      footer={
        <>
          <button className="btn danger" onClick={del}>
            Delete
          </button>
          <button className="btn" onClick={addChild}>
            ＋ Sub-activity
          </button>
          <button className="btn primary" onClick={onClose}>
            Done
          </button>
        </>
      }
    >
      <div className="row">
        <label>Name</label>
        <input
          type="text"
          value={name}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          onBlur={saveName}
          onKeyDown={(e) => e.key === "Enter" && (e.currentTarget.blur(), saveName())}
        />
      </div>

      <div className="modal-section">
        <h4>Risks faced ({attached.length})</h4>
        {attached.length === 0 && <div className="assigned-none">No risks attached yet.</div>}
        {attached.map((r) => (
          <div className="assigned-row" key={r.id}>
            <span className="etype risk">⚠</span>
            <span>{r.label}</span>
            <span className="reuse">used ×{r.used_by}</span>
            <span className="spacer-x" />
            <button
              className="icon-btn danger"
              title="Detach risk"
              onClick={() => run("/api/activity/risk/detach", { activity_id: activity.id, risk_id: r.id })}
            >
              ✕
            </button>
          </div>
        ))}

        <div className="picker-tabs" style={{ marginTop: 12 }}>
          <button
            className={effectiveMode === "existing" ? "active" : ""}
            disabled={available.length === 0}
            onClick={() => setMode("existing")}
          >
            Attach existing
          </button>
          <button className={effectiveMode === "new" ? "active" : ""} onClick={() => setMode("new")}>
            New risk
          </button>
        </div>

        {effectiveMode === "existing" && (
          <div className="row">
            <select value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">— choose a risk —</option>
              {available.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label} (used ×{r.used_by})
                </option>
              ))}
            </select>
            <button className="btn primary small" onClick={attachExisting}>
              Attach
            </button>
          </div>
        )}

        {effectiveMode === "new" && (
          <>
            <div className="row">
              <input
                type="text"
                placeholder="Risk name, e.g. Data loss"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
              />
            </div>
            <div className="row">
              <input
                type="text"
                placeholder="Description (optional)"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
              />
              <button className="btn primary small" onClick={createAndAttach}>
                Create &amp; attach
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
