import buildingFixture from "../../contracts/fixtures/building.json";
import entryPointsFixture from "../../contracts/fixtures/entry_points.json";
import assetsFixture from "../../contracts/fixtures/assets.json";
import scenarioTableFixture from "../../contracts/fixtures/scenario_table.json";
import triageFixture from "../../contracts/fixtures/triage.json";
import triageElevationFixture from "../../contracts/fixtures/triage_elevation.json";
import groundingFixture from "../../contracts/fixtures/grounding.json";
import mitigationsFixture from "../../contracts/fixtures/mitigations.json";
import eventsFixture from "../../contracts/fixtures/agent_events.json";
import type {
  AgentActionResult,
  AgentEvent,
  AgentStatus,
  Asset,
  Building,
  BuildingBundle,
  Dossier,
  EntryPoint,
  Grounding,
  MediaManifest,
  Mitigation,
  ReplayRun,
  ScenarioTable,
  TriageRow,
  TriageElevationRow,
} from "./contracts";

const API_BASE = "http://localhost:8000";
const source = process.env.WATERLINE_DATA_SOURCE === "fixture" ? "fixture" : "api";

async function api<T>(pathname: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${pathname}`, { ...init, cache: "no-store" });
  if (!response.ok) throw await apiError(response, init?.method ?? "GET", pathname);
  return response.json() as Promise<T>;
}

async function apiError(response: Response, method: string, pathname: string) {
  const raw = await response.text();
  let detail = raw;
  try {
    const parsed = JSON.parse(raw) as { detail?: string; message?: string };
    detail = parsed.detail ?? parsed.message ?? raw;
  } catch {
    // Keep the verbatim response when it is not JSON.
  }
  return new Error(`${method} ${pathname} → ${response.status}${detail ? `: ${detail}` : ""}`);
}

async function optionalApi<T>(pathname: string): Promise<T | null> {
  const response = await fetch(`${API_BASE}${pathname}`, { cache: "no-store" });
  if (response.status === 404 || response.status === 503) return null;
  if (!response.ok) throw new Error(`Waterline API ${response.status}: ${pathname}`);
  return response.json() as Promise<T>;
}

function mediaUrl(pathname: string | null | undefined) {
  if (!pathname) return null;
  return pathname.startsWith("http://") || pathname.startsWith("https://") ? pathname : `${API_BASE}${pathname.startsWith("/") ? "" : "/"}${pathname}`;
}

function normalizeManifest(manifest: MediaManifest | null): MediaManifest | null {
  if (!manifest) return null;
  return {
    ...manifest,
    mesh: manifest.mesh ? { ...manifest.mesh, url: mediaUrl(manifest.mesh.url)! } : null,
    aerial: Object.fromEntries(Object.entries(manifest.aerial ?? {}).map(([kind, image]) => [kind, { ...image, url: mediaUrl(image.url)!, meta_url: mediaUrl(image.meta_url)! }])),
  };
}

export function getDataSource() {
  return source;
}

export async function getBuildings(): Promise<Building[]> {
  if (source === "api") return api<Building[]>("/buildings");
  return [buildingFixture as unknown as Building];
}

export async function getTriage(depthFt: 1 | 2 | 4 | 6): Promise<TriageRow[]> {
  if (source === "api") return api<TriageRow[]>(`/triage?depth_ft=${depthFt}`);
  return triageFixture as unknown as TriageRow[];
}

export async function getElevationTriage(offsetFt: 0 | 1 | 2 | 3): Promise<TriageElevationRow[]> {
  if (source === "api") return api<TriageElevationRow[]>(`/triage?mode=fema&offset_ft=${offsetFt}`);
  return (triageElevationFixture as unknown as TriageElevationRow[])
    .filter((row) => row.offset_ft === offsetFt);
}

export async function getBuildingBundle(id: string): Promise<BuildingBundle | null> {
  if (source === "api") {
    try {
      const [detail, rawManifest, scenarioTable, mitigations, triage, grounding] = await Promise.all([
        api<{ building: Building; entry_points: EntryPoint[]; assets: Asset[] }>(`/buildings/${encodeURIComponent(id)}`),
        optionalApi<MediaManifest>(`/media/${encodeURIComponent(id)}/manifest.json`),
        api<ScenarioTable>(`/buildings/${encodeURIComponent(id)}/scenario_table`),
        optionalApi<Mitigation[]>(`/buildings/${encodeURIComponent(id)}/mitigations?depth_ft=2`),
        api<TriageRow[]>("/triage?depth_ft=2"),
        optionalApi<Grounding>(`/buildings/${encodeURIComponent(id)}/grounding`),
      ]);
      const media = normalizeManifest(rawManifest);
      return {
        building: detail.building,
        entryPoints: detail.entry_points,
        assets: detail.assets,
        scenarioTable,
        mitigations: mitigations ?? [],
        events: [],
        meshUrl: media?.mesh?.url ?? null,
        media,
        triage: triage.find((row) => row.building_id === id) ?? null,
        grounding,
      };
    } catch (error) {
      if (error instanceof Error && error.message.includes("404")) return null;
      throw error;
    }
  }

  const building = buildingFixture as unknown as Building;
  const entryPoints = entryPointsFixture as EntryPoint[];
  const assets = assetsFixture as Asset[];
  const scenarioTable = scenarioTableFixture as ScenarioTable;
  const mitigations = mitigationsFixture as Mitigation[];
  const events = eventsFixture as AgentEvent[];
  if (building.id !== id) return null;
  return { building, entryPoints, assets, scenarioTable, mitigations, events, meshUrl: null, media: null, triage: triageFixture.find((row) => row.building_id === id) as TriageRow | undefined ?? null, grounding: groundingFixture as unknown as Grounding };
}

export async function forwardSend(buildingId: string, body: string) {
  return fetch(`${API_BASE}/buildings/${encodeURIComponent(buildingId)}/send`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    cache: "no-store",
  });
}

export function subscribeToEvents(
  buildingId: string,
  dataSource: string,
  fixtureEvents: AgentEvent[],
  onEvent: (event: AgentEvent) => void,
  onState: (state: "connecting" | "open" | "replay" | "error") => void,
  options?: {
    eventsUrl?: string;
    onReplay?: (run: ReplayRun) => void;
    onEnd?: (summary: Record<string, unknown>) => void;
    onError?: (message: string) => void;
  },
) {
  if (dataSource !== "api") {
    onState("replay");
    const timers = fixtureEvents.map((event, index) => window.setTimeout(() => onEvent(event), 120 + index * 90));
    return () => timers.forEach(window.clearTimeout);
  }
  onState("connecting");
  const eventsUrl = options?.eventsUrl ?? `/buildings/${encodeURIComponent(buildingId)}/events`;
  const eventSource = new EventSource(eventsUrl.startsWith("http") ? eventsUrl : `${API_BASE}${eventsUrl}`);
  eventSource.onopen = () => onState("open");
  const readEvent = (message: MessageEvent<string>) => onEvent(JSON.parse(message.data) as AgentEvent);
  eventSource.addEventListener("agent_event", readEvent as EventListener);
  eventSource.onmessage = readEvent;
  eventSource.addEventListener("replay", ((message: MessageEvent<string>) => {
    onState("replay");
    options?.onReplay?.(JSON.parse(message.data) as ReplayRun);
  }) as EventListener);
  eventSource.addEventListener("end", ((message: MessageEvent<string>) => {
    options?.onEnd?.(JSON.parse(message.data) as Record<string, unknown>);
    eventSource.close();
  }) as EventListener);
  eventSource.onerror = () => {
    onState("error");
    options?.onError?.(`GET ${eventsUrl} → event stream disconnected`);
  };
  return () => eventSource.close();
}

export function getAgentStatus(buildingId: string) {
  return api<AgentStatus>(`/buildings/${encodeURIComponent(buildingId)}/agent`);
}

export function getLatestRun(buildingId: string) {
  return api<ReplayRun>(`/buildings/${encodeURIComponent(buildingId)}/runs/latest`);
}

export function getDossier(buildingId: string) {
  return api<Dossier>(`/buildings/${encodeURIComponent(buildingId)}/dossier`);
}

export function runAgent(buildingId: string, depthFt: number) {
  return api<AgentActionResult>(`/buildings/${encodeURIComponent(buildingId)}/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ depth_ft: depthFt, live: true }),
  });
}

export function replayLastRun(buildingId: string) {
  return api<AgentActionResult>(`/buildings/${encodeURIComponent(buildingId)}/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ replay: true }),
  });
}

export function postAgentDepth(buildingId: string, depthFt: number) {
  return api<AgentActionResult>(`/buildings/${encodeURIComponent(buildingId)}/depth`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ depth_ft: depthFt }),
  });
}

export function requestAgentSend(buildingId: string, recipient: string) {
  return api<AgentActionResult>(`/buildings/${encodeURIComponent(buildingId)}/request_send`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ recipient }),
  });
}

export function decideAgentSend(buildingId: string, approved: boolean, recipient: string) {
  return api<AgentActionResult>(`/buildings/${encodeURIComponent(buildingId)}/send`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ approved, ...(recipient ? { recipient } : {}) }),
  });
}

export async function getMitigationsForDepth(buildingId: string, depthFt: number, signal?: AbortSignal) {
  const response = await fetch(`${API_BASE}/buildings/${encodeURIComponent(buildingId)}/mitigations?depth_ft=${encodeURIComponent(depthFt)}`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error(`Mitigations unavailable at ${depthFt.toFixed(2)} ft (${response.status}).`);
  return response.json() as Promise<Mitigation[]>;
}

export async function correctAsset(buildingId: string, assetId: string, method: "PATCH" | "DELETE", changes: Record<string, unknown>, depthFt: number) {
  const response = await fetch(`${API_BASE}/buildings/${encodeURIComponent(buildingId)}/assets/${encodeURIComponent(assetId)}?depth_ft=${encodeURIComponent(depthFt)}`, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(changes),
  });
  const mutation = await response.json() as { detail?: string; mitigations?: Mitigation[]; similar_asset_ids?: string[] };
  if (!response.ok) throw new Error(mutation.detail || `Correction failed (${response.status}).`);
  const triageDepth = [1, 2, 4, 6].reduce((nearest, candidate) => Math.abs(candidate - depthFt) < Math.abs(nearest - depthFt) ? candidate : nearest);
  const [detail, scenarioTable, triage] = await Promise.all([
    api<{ building: Building; entry_points: EntryPoint[]; assets: Asset[] }>(`/buildings/${encodeURIComponent(buildingId)}`),
    api<ScenarioTable>(`/buildings/${encodeURIComponent(buildingId)}/scenario_table`),
    api<TriageRow[]>(`/triage?depth_ft=${triageDepth}`),
  ]);
  return {
    assets: detail.assets,
    scenarioTable,
    mitigations: mutation.mitigations ?? [],
    rank: triage.find((row) => row.building_id === buildingId)?.rank ?? null,
    rankDepth: triageDepth,
    similarCount: mutation.similar_asset_ids?.length ?? 0,
  };
}

export function getArtifactUrl(buildingId: string, artifact: "report" | "playbook", depthFt = 2) {
  return `${API_BASE}/buildings/${encodeURIComponent(buildingId)}/${artifact}?depth_ft=${encodeURIComponent(depthFt)}`;
}

export async function approveAndSend(buildingId: string, recipient: string) {
  const response = await fetch(`/api/buildings/${buildingId}/send`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ approved: true, recipient }),
  });
  const result = await response.json() as { status?: string; reason?: string; message?: string; detail?: string };
  if (!response.ok) throw new Error(result.detail || result.message || "The playbook could not be sent.");
  return { ok: true, message: result.reason || result.message || `Backend send status: ${result.status ?? "accepted"}.` };
}

export async function resetDemo(): Promise<void> {
  // Backend demo reset (localhost only): restores the starting state and clears agent sessions.
  await api<unknown>("/demo/reset", { method: "POST" });
}
