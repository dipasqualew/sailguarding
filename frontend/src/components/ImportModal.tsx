import { useState } from "react";

import { activeModel } from "../lookups";
import type { ModelSummary, MutationResult, ViewModel } from "../types";
import { Modal } from "./Modal";

type Run = (path: string, body?: Record<string, unknown>) => Promise<MutationResult | null>;
type Kind = "activity" | "risk" | "safeguard";

/** Copy an activity (with its subtree, risks, safeguards and edges), risk, or safeguard from
 *  another model into the active one — the source model is left untouched. */
export function ImportModal({
  model,
  run,
  notify,
  onClose,
}: {
  model: ViewModel;
  run: Run;
  notify: (msg: string) => void;
  onClose: () => void;
}) {
  const target = activeModel(model);
  const others = model.models.filter((m) => m.id !== model.active_id);
  const [sourceId, setSourceId] = useState(others[0]?.id ?? "");
  const [kind, setKind] = useState<Kind>("activity");
  const [entityId, setEntityId] = useState("");

  const source: ModelSummary | undefined = model.models.find((m) => m.id === sourceId);
  const entities =
    source == null
      ? []
      : kind === "activity"
        ? source.activities
        : kind === "risk"
          ? source.risks
          : source.safeguards;

  const doImport = async () => {
    if (!entityId) return notify("Choose an item to import.");
    const res = await run("/api/model/import", {
      target_id: model.active_id,
      source_id: sourceId,
      kind,
      entity_id: entityId,
    });
    if (res) {
      notify(`Imported into ${target?.name ?? "model"}.`);
      onClose();
    }
  };

  const pickKind = (k: Kind) => {
    setKind(k);
    setEntityId("");
  };

  return (
    <Modal
      title={`Import into “${target?.name ?? ""}”`}
      sub="Copies the item in. The source model is left untouched."
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" onClick={doImport} disabled={entities.length === 0}>
            Import
          </button>
        </>
      }
    >
      <div className="row">
        <label>From model</label>
        <select
          value={sourceId}
          onChange={(e) => {
            setSourceId(e.target.value);
            setEntityId("");
          }}
        >
          {others.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      </div>

      <div className="picker-tabs">
        {(["activity", "risk", "safeguard"] as Kind[]).map((k) => (
          <button key={k} className={kind === k ? "active" : ""} onClick={() => pickKind(k)}>
            {k[0].toUpperCase() + k.slice(1)}
          </button>
        ))}
      </div>

      <div className="row">
        <label>Item</label>
        <select value={entityId} onChange={(e) => setEntityId(e.target.value)}>
          <option value="">{entities.length ? "— choose an item —" : "— nothing to import —"}</option>
          {entities.map((e) => {
            const depth = (e as { depth?: number }).depth ?? 0;
            const pad = depth ? `${"  ".repeat(depth)}↳ ` : "";
            return (
              <option key={e.id} value={e.id}>
                {pad}
                {e.label}
              </option>
            );
          })}
        </select>
      </div>

      {kind === "activity" && (
        <div className="import-preview">
          Imports the activity <b>and</b> its sub-activities, the risks &amp; safeguards it references,
          and the edges wiring them — so it lands fully governed.
        </div>
      )}
    </Modal>
  );
}
