// Pure lookups over the flat view model — the React mirror of the original page's helper closures.
import type { Activity, Risk, Safeguard, ViewModel } from "./types";

export const activityById = (m: ViewModel, id: string): Activity | undefined =>
  m.activities.find((a) => a.id === id);
export const riskById = (m: ViewModel, id: string): Risk | undefined =>
  m.risks.find((r) => r.id === id);
export const safeguardById = (m: ViewModel, id: string): Safeguard | undefined =>
  m.safeguards.find((s) => s.id === id);

export const topLevel = (m: ViewModel): Activity[] =>
  m.activities.filter((a) => a.parent_id === null);
export const childrenOf = (m: ViewModel, id: string): Activity[] =>
  m.activities.filter((a) => a.parent_id === id);

/** The library risks an activity faces, in attach order. */
export const risksForActivity = (m: ViewModel, aid: string): Risk[] =>
  m.activity_risks
    .filter((e) => e[0] === aid)
    .map((e) => riskById(m, e[1]))
    .filter((r): r is Risk => r != null);

/** The safeguards mitigating a given risk on a given activity. */
export const safeguardsForRisk = (m: ViewModel, aid: string, rid: string): Safeguard[] =>
  m.mitigations
    .filter((e) => e[0] === aid && e[1] === rid)
    .map((e) => safeguardById(m, e[2]))
    .filter((s): s is Safeguard => s != null);

export const activeModel = (m: ViewModel) => m.models.find((x) => x.id === m.active_id) ?? null;

export const kindLabel = (k: string): string => (k === "human_dependent" ? "human-dependent" : k);

/** The ancestor labels of an activity, root-first (its breadcrumb). */
export function pathLabels(m: ViewModel, activity: Activity): string[] {
  const labels: string[] = [];
  let cur: Activity | undefined = activity;
  while (cur && cur.parent_id) {
    cur = activityById(m, cur.parent_id);
    if (cur) labels.unshift(cur.label);
  }
  return labels;
}
