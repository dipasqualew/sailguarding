import { kindLabel } from "../lookups";
import type { ViewModel } from "../types";

/** The collapsible right rail: the risk & safeguard libraries, each with a reuse count. Reuse is
 *  the whole point — one named risk faced by many activities, one control mitigating many. */
export function Libraries({
  model,
  collapsed,
  onToggle,
}: {
  model: ViewModel;
  collapsed: boolean;
  onToggle: () => void;
}) {
  if (collapsed) {
    return (
      <aside className="panel rail collapsed">
        <button className="rail-toggle" onClick={onToggle} title="Show libraries">
          ‹ Libraries
        </button>
      </aside>
    );
  }

  return (
    <aside className="panel rail">
      <div className="panel-head">
        <h2>Libraries</h2>
        <button className="icon-btn" onClick={onToggle} title="Collapse">
          ›
        </button>
      </div>

      <div className="lib-block">
        <div className="panel-head">
          <h2>Risks</h2>
        </div>
        <div className="lib-list">
          {model.risks.length === 0 && (
            <div className="lib-empty">No risks yet — add one from an activity.</div>
          )}
          {model.risks.map((r) => (
            <div className="lib-item" key={r.id}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="lib-name">{r.label}</div>
                {r.description && <div className="lib-desc">{r.description}</div>}
              </div>
              <span className={`reuse${r.used_by > 1 ? " shared" : ""}`}>used ×{r.used_by}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="lib-block">
        <div className="panel-head">
          <h2>Safeguards</h2>
        </div>
        <div className="lib-list">
          {model.safeguards.length === 0 && (
            <div className="lib-empty">No safeguards yet — assign one to a risk.</div>
          )}
          {model.safeguards.map((s) => (
            <div className="lib-item" key={s.id}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="lib-name">{s.label}</div>
                <div className="lib-tags">
                  <span className={`pill ${s.kind}`}>{kindLabel(s.kind)}</span>
                  <span className={`pill ${s.measures}`}>{s.measures}</span>
                </div>
              </div>
              <span className={`reuse${s.used_by > 1 ? " shared" : ""}`}>reused ×{s.used_by}</span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
