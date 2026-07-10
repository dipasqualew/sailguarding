import type { MutationResult, ViewModel } from "./types";

// The API base is same-origin by default: under `sg serve` the SPA and the JSON API share a host,
// and under `npm run dev` Vite proxies `/api` to the Python server. Set `VITE_API_BASE` at build
// time to point the hosted SPA at a separate backend.
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

/** Raised when the server answers with a non-2xx and an `{error}` body (or an opaque failure). */
export class ApiError extends Error {}

/** Load the current view model. */
export async function loadModel(): Promise<ViewModel> {
  const res = await fetch(`${BASE}/api/model`);
  if (!res.ok) throw new ApiError(`could not load model (${res.status})`);
  return (await res.json()) as ViewModel;
}

/**
 * POST one mutation and return the refreshed model. Every route on the server answers with
 * `{model, created_id}`; a 4xx answers with `{error}`, which we raise as an {@link ApiError} the
 * caller turns into a toast — mirroring the original page's `api()` contract.
 */
export async function post(path: string, body: Record<string, unknown> = {}): Promise<MutationResult> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network error — is the server still running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error || `request failed (${res.status})`);
  return data as MutationResult;
}
