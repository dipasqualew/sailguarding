import { useState } from "react";

import { kindLabel, riskById, safeguardsForRisk } from "../lookups";
import type { Measurement, MutationResult, SafeguardKind, ViewModel } from "../types";
import { Modal } from "./Modal";

type Run = (path: string, body?: Record<string, unknown>) => Promise<MutationResult | null>;

/** The risk inspector, scoped to one activity: assign/remove safeguards, or detach the risk. */
export function RiskModal({
  model,
  activityId,
  riskId,
  run,
  notify,
  onClose,
}: {
  model: ViewModel;
  activityId: string;
  riskId: string;
  run: Run;
  notify: (msg: string) => void;
  onClose: () => void;
}) {
  const risk = riskById(model, riskId);
  const activity = model.activities.find((a) => a.id === activityId);
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [pick, setPick] = useState("");
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<SafeguardKind>("structural");
  const [measures, setMeasures] = useState<Measurement>("health");

  if (!risk || !activity) {
    onClose();
    return null;
  }

  const assigned = safeguardsForRisk(model, activityId, riskId);
  const assignedIds = new Set(assigned.map((s) => s.id));
  const available = model.safeguards.filter((s) => !assignedIds.has(s.id));
  const effectiveMode = available.length === 0 ? "new" : mode;

  const assignExisting = async () => {
    if (pick) await run("/api/mitigation/add", { activity_id: activityId, risk_id: riskId, safeguard_id: pick });
  };

  const createAndAssign = async () => {
    const name = label.trim();
    if (!name) return notify("Give the safeguard a name.");
    const created = await run("/api/safeguard/create", { label: name, kind, measures });
    if (created?.created_id) {
      await run("/api/mitigation/add", {
        activity_id: activityId,
        risk_id: riskId,
        safeguard_id: created.created_id,
      });
      setLabel("");
    }
  };

  const detachRisk = async () => {
    const res = await run("/api/activity/risk/detach", { activity_id: activityId, risk_id: riskId });
    if (res) onClose();
  };

  return (
    <Modal
      icon={<span className="etype risk">⚠</span>}
      title={risk.label}
      sub={
        <>
          On <b>{activity.label}</b>
          {risk.description ? ` — ${risk.description}` : ""} · used across {risk.used_by} activit
          {risk.used_by === 1 ? "y" : "ies"}
        </>
      }
      onClose={onClose}
      footer={
        <>
          <button className="btn danger" onClick={detachRisk}>
            Detach risk
          </button>
          <button className="btn primary" onClick={onClose}>
            Done
          </button>
        </>
      }
    >
      <div className="modal-section" style={{ borderTop: 0, marginTop: 0, paddingTop: 0 }}>
        <h4>Safeguards ({assigned.length})</h4>
        {assigned.length === 0 && <div className="assigned-none">No safeguards assigned.</div>}
        {assigned.map((s) => (
          <div className="assigned-row" key={s.id}>
            <span className="etype safeguard">✓</span>
            <span>{s.label}</span>
            <span className={`pill ${s.kind}`}>{kindLabel(s.kind)}</span>
            <span className={`pill ${s.measures}`}>{s.measures}</span>
            <span className={`reuse${s.used_by > 1 ? " shared" : ""}`}>reused ×{s.used_by}</span>
            <span className="spacer-x" />
            <button
              className="icon-btn danger"
              title="Unassign"
              onClick={() =>
                run("/api/mitigation/remove", { activity_id: activityId, risk_id: riskId, safeguard_id: s.id })
              }
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
            Assign existing
          </button>
          <button className={effectiveMode === "new" ? "active" : ""} onClick={() => setMode("new")}>
            New safeguard
          </button>
        </div>

        {effectiveMode === "existing" && (
          <div className="row">
            <select value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">— choose a safeguard —</option>
              {available.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label} · {kindLabel(s.kind)} · {s.measures} (reused ×{s.used_by})
                </option>
              ))}
            </select>
            <button className="btn primary small" onClick={assignExisting}>
              Assign
            </button>
          </div>
        )}

        {effectiveMode === "new" && (
          <>
            <div className="row">
              <input
                type="text"
                placeholder="Safeguard name"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
            </div>
            <div className="row">
              <label>Kind</label>
              <select value={kind} onChange={(e) => setKind(e.target.value as SafeguardKind)}>
                <option value="structural">structural</option>
                <option value="human_dependent">human-dependent</option>
              </select>
              <label>Measures</label>
              <select value={measures} onChange={(e) => setMeasures(e.target.value as Measurement)}>
                <option value="health">health</option>
                <option value="efficacy">efficacy</option>
              </select>
            </div>
            <div className="row">
              <button className="btn primary small" onClick={createAndAssign}>
                Create &amp; assign
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
