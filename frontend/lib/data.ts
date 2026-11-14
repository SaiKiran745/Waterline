import buildingFixture from "../../contracts/fixtures/building.json";
import entryPointsFixture from "../../contracts/fixtures/entry_points.json";
import assetsFixture from "../../contracts/fixtures/assets.json";
import scenarioFixture from "../../contracts/fixtures/scenario_2ft.json";
import mitigationsFixture from "../../contracts/fixtures/mitigations.json";
import eventsFixture from "../../contracts/fixtures/agent_events.json";
import type {
  AgentEvent,
  Asset,
  Building,
  BuildingBundle,
  EntryPoint,
  Mitigation,
  ScenarioResult,
} from "./contracts";

const API_BASE = "http://localhost:8000";
const source = process.env.WATERLINE_DATA_SOURCE === "api" ? "api" : "fixture";

async function api<T>(pathname: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${pathname}`, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error(`Waterline API ${response.status}: ${pathname}`);
  return response.json() as Promise<T>;
}

export function getDataSource() {
  return source;
}

export async function getBuildings(): Promise<Building[]> {
  if (source === "api") return api<Building[]>("/buildings");
  return [buildingFixture as Building];
}

export async function getBuildingBundle(id: string): Promise<BuildingBundle | null> {
  if (source === "api") {
    try {
      const [detail, scenario, mitigations] = await Promise.all([
        api<{ building: Building; entry_points: EntryPoint[]; assets: Asset[] }>(`/buildings/${id}`),
        api<ScenarioResult>(`/buildings/${id}/scenario?depth_ft=2`),
        api<Mitigation[]>(`/buildings/${id}/mitigations?depth_ft=2`),
      ]);
      return {
        building: detail.building,
        entryPoints: detail.entry_points,
        assets: detail.assets,
        scenario,
        mitigations,
        events: [],
        meshUrl: `${API_BASE}/media/${id}/mesh/mesh_50k.obj`,
      };
    } catch (error) {
      if (error instanceof Error && error.message.includes("404")) return null;
      throw error;
    }
  }

  const building = buildingFixture as Building;
  const entryPoints = entryPointsFixture as EntryPoint[];
  const assets = assetsFixture as Asset[];
  const scenario = scenarioFixture as ScenarioResult;
  const mitigations = mitigationsFixture as Mitigation[];
  const events = eventsFixture as AgentEvent[];
  if (building.id !== id) return null;
  return { building, entryPoints, assets, scenario, mitigations, events, meshUrl: null };
}

export async function sendPlaybook(buildingId: string, recipient = ""): Promise<{ ok: boolean; message: string }> {
  if (source === "api") {
    await api(`/buildings/${buildingId}/send`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ approved: true, recipient }),
    });
    return { ok: true, message: "Approved playbook sent by Waterline API." };
  }
  return { ok: true, message: "Fixture approval recorded. No external message was sent." };
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

export async function approveAndSend(buildingId: string, recipient: string) {
  const response = await fetch(`/api/buildings/${buildingId}/send`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ approved: true, recipient }),
  });
  const result = await response.json() as { ok: boolean; message: string };
  if (!response.ok) throw new Error(result.message || "The playbook could not be sent.");
  return result;
}
