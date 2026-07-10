// Wire types mirroring the engine's `view_model` (see src/sailguarding/web/app.py::view_model).
// Kept as a hand-written mirror rather than generated, since the API is small and stable.

export type SafeguardKind = "structural" | "human_dependent";
export type Measurement = "health" | "efficacy";

/** One activity in the active model, flattened depth-first (synthetic root excluded). */
export interface Activity {
  id: string;
  label: string;
  parent_id: string | null;
  depth: number;
  child_ids: string[];
  risk_count: number;
  mitigation_count: number;
}

/** A library risk in the active model, with its reuse count. */
export interface Risk {
  id: string;
  label: string;
  description: string;
  used_by: number;
}

/** A library safeguard in the active model, with its reuse count. */
export interface Safeguard {
  id: string;
  label: string;
  kind: SafeguardKind;
  measures: Measurement;
  metric: string;
  cadence_seconds: number | null;
  used_by: number;
}

/** The applicability scope: named dimensions each pinned to a set of values. */
export interface AppliesWhen {
  dimensions: { name: string; values: string[] }[];
  summary: string;
}

/** A model's header entry — plus id+label pick-lists the import dialog reads without a round-trip. */
export interface ModelSummary {
  id: string;
  name: string;
  applies_when: AppliesWhen;
  activity_count: number;
  risk_count: number;
  safeguard_count: number;
  activities: { id: string; label: string; depth: number }[];
  risks: { id: string; label: string }[];
  safeguards: { id: string; label: string; kind: SafeguardKind; measures: Measurement }[];
}

/** The whole payload the UI renders: the model switcher plus the active model's flattened view. */
export interface ViewModel {
  models: ModelSummary[];
  active_id: string | null;
  activities: Activity[];
  risks: Risk[];
  safeguards: Safeguard[];
  /** `[activityId, riskId]` — which risks each activity faces. */
  activity_risks: [string, string][];
  /** `[activityId, riskId, safeguardId]` — which safeguard mitigates a risk on an activity. */
  mitigations: [string, string, string][];
  applies_when: AppliesWhen;
}

/** The envelope every mutation POST returns. */
export interface MutationResult {
  model: ViewModel;
  created_id: string | null;
}
