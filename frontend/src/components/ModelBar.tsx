import { useState } from "react";

import { activeModel } from "../lookups";
import type { MutationResult, ViewModel } from "../types";

type Run = (path: string, body?: Record<string, unknown>) => Promise<MutationResult | null>;

/** The model switcher pills plus the active model's "Applies when" scope strip. */
export function ModelBar({
  model,
  run,
  notify,
  onImport,
}: {
  model: ViewModel;
  run: Run;
  notify: (msg: string) => void;
  onImport: () => void;
}) {
  const meta = activeModel(model);

  const createModel = async () => {
    const name = (prompt("Name the new activity model (e.g. Data Science):") || "").trim();
    if (name) await run("/api/model/add", { name });
  };
  const renameModel = async () => {
    if (!meta) return;
    const name = (prompt("Rename this model:", meta.name) || "").trim();
    if (name && name !== meta.name) await run("/api/model/rename", { id: meta.id, name });
  };
  const deleteModel = async () => {
    if (!meta) return;
    if (model.models.length <= 1) return notify("Keep at least one model.");
    if (confirm(`Delete the "${meta.name}" model and everything in it?`))
      await run("/api/model/delete", { id: meta.id });
  };

  return (
    <>
      <div className="models">
        {model.models.map((m) => (
          <button
            key={m.id}
            className={`model-pill${m.id === model.active_id ? " active" : ""}`}
            onClick={() => m.id !== model.active_id && run("/api/model/select", { id: m.id })}
          >
            {m.name || "(unnamed model)"}
            <span className="model-count" title="activities">
              {m.activity_count}
            </span>
          </button>
        ))}
        <button className="model-pill add" onClick={createModel}>
          ＋ New model
        </button>
        <span className="model-actions">
          <button className="btn small ghost" onClick={renameModel}>
            Rename
          </button>
          <button className="btn small ghost" onClick={deleteModel}>
            Delete
          </button>
          <button className="btn small ghost" onClick={onImport}>
            ⤵ Import…
          </button>
        </span>
      </div>

      {model.active_id && <ScopeStrip model={model} run={run} notify={notify} />}
    </>
  );
}

/** The "Applies when" strip: edit the named context dimensions the active model is scoped to. */
function ScopeStrip({ model, run, notify }: { model: ViewModel; run: Run; notify: (m: string) => void }) {
  const [draft, setDraft] = useState<Record<number, string>>({});
  const dims = model.applies_when.dimensions;

  // Every edit sends the whole dimension set — the transform replaces the scope wholesale.
  const save = (next: { name: string; values: string[] }[]) =>
    run("/api/model/scope/set", { id: model.active_id, dimensions: next });
  const clone = () => dims.map((d) => ({ name: d.name, values: [...d.values] }));

  const addValue = (i: number) => {
    const v = (draft[i] ?? "").trim();
    if (!v) return;
    const next = clone();
    if (next[i].values.includes(v)) return notify("That value is already listed.");
    next[i].values.push(v);
    setDraft((d) => ({ ...d, [i]: "" }));
    save(next);
  };
  const removeValue = (i: number, j: number) => {
    const next = clone();
    next[i].values.splice(j, 1);
    save(next);
  };
  const removeDim = (i: number) => {
    const next = clone();
    next.splice(i, 1);
    save(next);
  };
  const addDim = () => {
    const name = (prompt("Context dimension this model is scoped to (e.g. repo, team, environment):") || "").trim();
    if (!name) return;
    if (dims.some((d) => d.name === name)) return notify("That dimension is already set.");
    save([...clone(), { name, values: [] }]);
  };

  return (
    <div className="scope-strip">
      <span className="scope-lead">Applies when</span>
      {dims.length === 0 && <span className="scope-any">everywhere — no context restriction</span>}
      {dims.map((d, i) => (
        <span className="scope-dim" key={d.name}>
          <span className="scope-name">{d.name}</span>
          {d.values.length ? (
            d.values.map((v, j) => (
              <span className="scope-chip" key={v}>
                {v}
                <button className="chip-x" title="Remove value" onClick={() => removeValue(i, j)}>
                  ×
                </button>
              </span>
            ))
          ) : (
            <span className="scope-chip any">any value</span>
          )}
          <input
            className="scope-add"
            placeholder="+ value"
            autoComplete="off"
            value={draft[i] ?? ""}
            onChange={(e) => setDraft((s) => ({ ...s, [i]: e.target.value }))}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addValue(i))}
          />
          <button className="chip-x" title="Remove dimension" onClick={() => removeDim(i)}>
            ✕
          </button>
        </span>
      ))}
      <button className="btn small ghost" onClick={addDim}>
        ＋ dimension
      </button>
    </div>
  );
}
