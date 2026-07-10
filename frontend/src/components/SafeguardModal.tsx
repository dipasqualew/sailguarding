import { kindLabel, riskById, safeguardById } from "../lookups";
import type { MutationResult, ViewModel } from "../types";
import { Modal } from "./Modal";

type Run = (path: string, body?: Record<string, unknown>) => Promise<MutationResult | null>;

/** The safeguard inspector, scoped to where it mitigates a risk: its properties, plus unassign. */
export function SafeguardModal({
  model,
  activityId,
  riskId,
  safeguardId,
  run,
  onClose,
}: {
  model: ViewModel;
  activityId: string;
  riskId: string;
  safeguardId: string;
  run: Run;
  onClose: () => void;
}) {
  const sg = safeguardById(model, safeguardId);
  const risk = riskById(model, riskId);
  const activity = model.activities.find((a) => a.id === activityId);

  if (!sg || !risk || !activity) return null;

  const cadence =
    sg.cadence_seconds == null ? "—" : `${Math.round(sg.cadence_seconds / 3600)}h`;

  const unassign = async () => {
    const res = await run("/api/mitigation/remove", {
      activity_id: activityId,
      risk_id: riskId,
      safeguard_id: safeguardId,
    });
    if (res) onClose();
  };

  return (
    <Modal
      icon={<span className="etype safeguard">✓</span>}
      title={sg.label}
      sub={
        <>
          Mitigating <b>{risk.label}</b> on <b>{activity.label}</b>
        </>
      }
      onClose={onClose}
      footer={
        <>
          <button className="btn danger" onClick={unassign}>
            Unassign from this risk
          </button>
          <button className="btn primary" onClick={onClose}>
            Done
          </button>
        </>
      }
    >
      <div className="assigned-row">
        <span className="entity-sub">Kind</span>
        <span className="spacer-x" />
        <span className={`pill ${sg.kind}`}>{kindLabel(sg.kind)}</span>
      </div>
      <div className="assigned-row">
        <span className="entity-sub">Measures</span>
        <span className="spacer-x" />
        <span className={`pill ${sg.measures}`}>{sg.measures}</span>
      </div>
      {sg.metric && (
        <div className="assigned-row">
          <span className="entity-sub">Metric</span>
          <span className="spacer-x" />
          <span>{sg.metric}</span>
        </div>
      )}
      <div className="assigned-row">
        <span className="entity-sub">Cadence</span>
        <span className="spacer-x" />
        <span>{cadence}</span>
      </div>
      <div className="assigned-row">
        <span className="entity-sub">Reuse</span>
        <span className="spacer-x" />
        <span className={`reuse${sg.used_by > 1 ? " shared" : ""}`}>
          reused across {sg.used_by} activit{sg.used_by === 1 ? "y" : "ies"}
        </span>
      </div>
    </Modal>
  );
}
