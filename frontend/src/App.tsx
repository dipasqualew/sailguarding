import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, loadModel, post } from "./api";
import { ActivityModal } from "./components/ActivityModal";
import { ImportModal } from "./components/ImportModal";
import { Libraries } from "./components/Libraries";
import { ModelBar } from "./components/ModelBar";
import { RiskModal } from "./components/RiskModal";
import { SafeguardModal } from "./components/SafeguardModal";
import { TreeCanvas } from "./components/TreeCanvas";
import type { MutationResult, ViewModel } from "./types";

/** Which inspector is open, if any. Each carries the ids it needs to resolve against the model. */
export type ModalTarget =
  | { kind: "activity"; activityId: string }
  | { kind: "risk"; activityId: string; riskId: string }
  | { kind: "safeguard"; activityId: string; riskId: string; safeguardId: string }
  | { kind: "import" };

/** True while the model still contains the entities a modal target points at. A mutation (delete,
 *  model switch, import) can strand an open modal; when that happens we close it. */
function targetValid(model: ViewModel, t: ModalTarget): boolean {
  if (t.kind === "import") return model.models.length > 1;
  const activity = model.activities.some((a) => a.id === t.activityId);
  if (t.kind === "activity") return activity;
  const risk = model.activity_risks.some((e) => e[0] === t.activityId && e[1] === t.riskId);
  if (t.kind === "risk") return activity && risk;
  return (
    activity &&
    risk &&
    model.mitigations.some((e) => e[0] === t.activityId && e[1] === t.riskId && e[2] === t.safeguardId)
  );
}

export function App() {
  const [model, setModel] = useState<ViewModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState("");
  const [modal, setModal] = useState<ModalTarget | null>(null);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>();

  const notify = useCallback((msg: string) => {
    setToastMsg(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastMsg(""), 2600);
  }, []);

  useEffect(() => {
    loadModel().then(setModel, (e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  // Every mutation POSTs, swaps in the returned model, and re-renders — the server stays the source
  // of truth. An {error} surfaces as a toast and leaves the model untouched.
  const run = useCallback(
    async (path: string, body: Record<string, unknown> = {}): Promise<MutationResult | null> => {
      try {
        const res = await post(path, body);
        setModel(res.model);
        return res;
      } catch (e) {
        notify(e instanceof ApiError ? e.message : String(e));
        return null;
      }
    },
    [notify],
  );

  // Close an inspector once its target no longer exists (deleted, switched away, imported).
  useEffect(() => {
    if (model && modal && !targetValid(model, modal)) setModal(null);
  }, [model, modal]);

  const toggleTheme = () => {
    const root = document.documentElement;
    const cur = root.getAttribute("data-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const next = cur === "dark" ? "light" : cur === "light" ? "dark" : prefersDark ? "light" : "dark";
    root.setAttribute("data-theme", next);
  };

  if (error) {
    return (
      <div className="shell">
        <div className="load-error">Could not load the model: {error}</div>
      </div>
    );
  }
  if (!model) {
    return (
      <div className="shell">
        <div className="loading">Loading activity model…</div>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="app-header">
        <div>
          <h1>
            sailguarding <span className="tag">activity models</span>
          </h1>
          <p>
            Model the work you hand to agents as a tree of activities, the risks each faces, and the
            safeguards that mitigate them. Switch between models, scope each to where it applies, and
            import activities, risks, or safeguards from one into another.
          </p>
        </div>
        <div className="header-actions">
          <button className="theme-toggle" onClick={toggleTheme}>
            Theme
          </button>
        </div>
      </header>

      <ModelBar model={model} run={run} notify={notify} onImport={() => setModal({ kind: "import" })} />

      <div className={`workbench${railCollapsed ? " rail-collapsed" : ""}`}>
        <TreeCanvas
          key={model.active_id ?? "none"}
          model={model}
          run={run}
          open={setModal}
          onImport={() => setModal({ kind: "import" })}
        />
        <Libraries model={model} collapsed={railCollapsed} onToggle={() => setRailCollapsed((c) => !c)} />
      </div>

      <footer>
        Every edit runs a real <code>ActivityModel</code> transform on the server and re-renders from
        the result. React SPA served by <code>sg serve</code>.
      </footer>

      {modal?.kind === "activity" && (
        <ActivityModal
          model={model}
          activityId={modal.activityId}
          run={run}
          notify={notify}
          openActivity={(id) => setModal({ kind: "activity", activityId: id })}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === "risk" && (
        <RiskModal
          model={model}
          activityId={modal.activityId}
          riskId={modal.riskId}
          run={run}
          notify={notify}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === "safeguard" && (
        <SafeguardModal
          model={model}
          activityId={modal.activityId}
          riskId={modal.riskId}
          safeguardId={modal.safeguardId}
          run={run}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === "import" && (
        <ImportModal model={model} run={run} notify={notify} onClose={() => setModal(null)} />
      )}

      <div className={`toast${toastMsg ? " show" : ""}`}>{toastMsg}</div>
    </div>
  );
}
