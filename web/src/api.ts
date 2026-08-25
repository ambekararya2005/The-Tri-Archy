/**
 * The one place the console talks to the API.
 *
 * `VITE_API_BASE` is baked at build time. Empty in dev, where vite.config.ts
 * proxies `/api` to 127.0.0.1:8000 and CORS never comes up; set to the deployed
 * API's origin for the Vercel build. Nothing else in the app knows a hostname.
 */

const RAW_BASE = import.meta.env.VITE_API_BASE ?? "";
export const API_BASE = RAW_BASE ? RAW_BASE.replace(/\/$/, "") : "/api";

export type Decision = "approve" | "challenge" | "review" | "decline";

export interface LayerScore {
  score: number | null;
  percentile: number | null;
}

export interface Contribution {
  feature: string;
  value: unknown;
  contribution: number;
}

export interface ScoredEvent {
  event_id: string;
  ts: string;
  amount: number;
  currency: string;
  mcc: string | null;
  channel: string;
  entry_mode: string | null;
  customer_id: string | null;
  merchant_id: string | null;
  merchant_country: string | null;
  card_bin: string | null;
  device_id: string | null;
  txn_type: string | null;
  ag_agent_id: string | null;
  ag_agent_platform: string | null;
  ag_mandate_type: string | null;
  ag_human_present: boolean | null;
  ag_delegation_depth: number | null;
  layers: Record<string, LayerScore>;
  l0: { fired: boolean; reason: string | null };
  risk: number | null;
  decision: Decision;
  contributions: Contribution[];
}

export interface Truth {
  is_fraud: boolean;
  attack_id: string | null;
  attack_campaign: string | null;
}

/** One SSE `auth` frame: what the firewall knew, then what was actually true. */
export interface AuthFrame {
  seq: number;
  event: ScoredEvent;
  truth: Truth;
}

export interface StreamMeta {
  run_id: string;
  n_events: number;
  rate: number;
  operating_fpr: number | null;
  sampling_note: string;
  provenance_note: string;
  thresholds: Record<string, number>;
}

export interface StreamDone {
  n_events: number;
  decisions: Record<string, number>;
  caught: number;
  missed: number;
  false_positives: number;
}

export interface AtlasCard {
  id: string;
  name: string;
  family: string;
  status: string;
  rails: string[];
  detected_by: string[];
  has_injector: boolean;
  discovered_by: string;
}

export interface AtlasResponse {
  cards: AtlasCard[];
  families: { family: string; total: number; implemented: number }[];
  total: number;
  implemented: number;
  discovered: AtlasCard[];
}

export interface ResultsResponse {
  generated: string;
  tables: { title: string; header: string[]; rows: string[][] }[];
  layer_performance: Record<string, string>[];
  per_family: Record<string, string>[];
  per_attack: Record<string, string>[];
  decisions: Record<string, string>[];
  zero_day: { detector: string; recall: number }[];
  evasion_curve: number[];
  headline: Record<string, unknown>;
}

export interface ArenaResponse {
  operating_fpr: number;
  cards: string[];
  seconds: number;
  n_background: number;
  evasion_curve: number[];
  generations: {
    generation: number;
    n_variants: number;
    n_events: number;
    mean_evasion: number;
    max_evasion: number;
    per_card: Record<string, number>;
  }[];
  survivors: Record<string, unknown>[];
  zero_day: Record<string, number | string> | null;
}

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    // The API answers 503 with a message naming the make target that produces
    // the missing artefact. Surfacing that verbatim turns "the panel is blank"
    // into "run make firewall", which is the difference between a bug report
    // and a fix.
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* a non-JSON error body is not worth a second failure */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const fetchAtlas = () => getJSON<AtlasResponse>("/atlas");
export const fetchResults = () => getJSON<ResultsResponse>("/results");
export const fetchArena = () => getJSON<ArenaResponse>("/arena");

export interface SimulateOptions {
  n_events?: number;
  rate?: number;
  family?: string | null;
  offset?: number;
}

export async function startRun(options: SimulateOptions = {}): Promise<{
  run_id: string;
  n_events: number;
  rate: number;
  stream_url: string;
  note: string;
}> {
  const response = await fetch(`${API_BASE}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      n_events: options.n_events ?? 200,
      rate: options.rate ?? 6,
      family: options.family ?? null,
      offset: options.offset ?? 0,
    }),
  });
  if (!response.ok) throw new Error(`simulate failed: ${response.status}`);
  return response.json();
}

/**
 * Open the SSE stream for a run.
 *
 * Returns the `EventSource` so the caller owns the lifetime — React's effect
 * cleanup closes it. Leaving that to this module would mean a component
 * unmounting mid-stream leaks a connection, and a judge clicking between tabs
 * during a demo does exactly that.
 */
export function openStream(
  runId: string,
  handlers: {
    onMeta?: (meta: StreamMeta) => void;
    onAuth?: (frame: AuthFrame) => void;
    onDone?: (done: StreamDone) => void;
    onError?: (error: Event) => void;
  },
): EventSource {
  const source = new EventSource(`${API_BASE}/stream/${runId}`);
  if (handlers.onMeta) {
    source.addEventListener("meta", (e) => handlers.onMeta!(JSON.parse((e as MessageEvent).data)));
  }
  if (handlers.onAuth) {
    source.addEventListener("auth", (e) => handlers.onAuth!(JSON.parse((e as MessageEvent).data)));
  }
  source.addEventListener("done", (e) => {
    handlers.onDone?.(JSON.parse((e as MessageEvent).data));
    // The server has said its last word. Without this close the browser sees a
    // finished stream as a dropped one and reconnects, replaying the whole feed
    // from the top — which during a demo looks like the console glitching.
    source.close();
  });
  source.onerror = (e) => handlers.onError?.(e);
  return source;
}
