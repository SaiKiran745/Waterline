import buildingFixture from "../../contracts/fixtures/building.json";
import entryPointsFixture from "../../contracts/fixtures/entry_points.json";
import assetsFixture from "../../contracts/fixtures/assets.json";
import scenarioTableFixture from "../../contracts/fixtures/scenario_table.json";
import triageFixture from "../../contracts/fixtures/triage.json";
import mitigationsFixture from "../../contracts/fixtures/mitigations.json";
import eventsFixture from "../../contracts/fixtures/agent_events.json";
import type {
  AgentEvent,
  Asset,
  Building,
  BuildingBundle,
  EntryPoint,
  MediaManifest,
  Mitigation,
  ScenarioTable,
  TriageRow,
} from "./contracts";

const API_BASE = "http://localhost:8000";
const source = process.env.WATERLINE_DATA_SOURCE === "fixture" ? "fixture" : "api";

async function api<T>(pathname: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${pathname}`, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error(`Waterline API ${response.status}: ${pathname}`);
  return response.json() as Promise<T>;
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
  return triageFixture as TriageRow[];
}

export async function getBuildingBundle(id: string): Promise<BuildingBundle | null> {
  if (source === "api") {
    try {
      const [detail, rawManifest, scenarioTable, mitigations] = await Promise.all([
        api<{ building: Building; entry_points: EntryPoint[]; assets: Asset[] }>(`/buildings/${encodeURIComponent(id)}`),
        optionalApi<MediaManifest>(`/media/${encodeURIComponent(id)}/manifest.json`),
        api<ScenarioTable>(`/buildings/${encodeURIComponent(id)}/scenario_table`),
        optionalApi<Mitigation[]>(`/buildings/${encodeURIComponent(id)}/mitigations?depth_ft=2`),
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
  return { building, entryPoints, assets, scenarioTable, mitigations, events, meshUrl: null, media: null };
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
) {
  if (dataSource !== "api") {
    onState("replay");
    const timers = fixtureEvents.map((event, index) => window.setTimeout(() => onEvent(event), 120 + index * 90));
    return () => timers.forEach(window.clearTimeout);
  }
  onState("connecting");
  const eventSource = new EventSource(`${API_BASE}/buildings/${buildingId}/events`);
  eventSource.onopen = () => onState("open");
  eventSource.onmessage = (message) => onEvent(JSON.parse(message.data) as AgentEvent);
  eventSource.onerror = () => onState("error");
  return () => eventSource.close();
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
  const [detail, scenarioTable, triage] = await Promise.all([
    api<{ building: Building; entry_points: EntryPoint[]; assets: Asset[] }>(`/buildings/${encodeURIComponent(buildingId)}`),
    api<ScenarioTable>(`/buildings/${encodeURIComponent(buildingId)}/scenario_table`),
    api<TriageRow[]>("/triage?depth_ft=2"),
  ]);
  return {
    assets: detail.assets,
    scenarioTable,
    mitigations: mutation.mitigations ?? [],
    rank: triage.find((row) => row.building_id === buildingId)?.rank ?? null,
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
