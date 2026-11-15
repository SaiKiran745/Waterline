import { TriageDashboard } from "@/components/TriageDashboard";
import { getBuildings, getDataSource, getElevationTriage, getTriage } from "@/lib/data";
import type { TriageElevationRow, TriageRow } from "@/lib/contracts";

export default async function HomePage({ searchParams }: { searchParams: Promise<{ mode?: string; depth_ft?: string; offset_ft?: string }> }) {
  const query = await searchParams;
  const mode = query.mode === "depth" ? "depth" : "fema";
  const requested = Number(query.depth_ft ?? 2);
  const depth = ([1, 2, 4, 6] as const).find((value) => value === requested) ?? 2;
  const requestedOffset = Number(query.offset_ft ?? 0);
  const offset = ([0, 1, 2, 3] as const).find((value) => value === requestedOffset) ?? 0;
  const [buildings, triage] = await Promise.all([
    getBuildings(),
    mode === "fema" ? getElevationTriage(offset) : getTriage(depth),
  ]);
  const buildingById = new Map(buildings.map((building) => [building.id, building]));
  const rows = triage
    .map((ranking) => ({ building: buildingById.get(ranking.building_id), triage: ranking }))
    .filter((row): row is { building: NonNullable<typeof row.building>; triage: TriageRow | TriageElevationRow } => Boolean(row.building))
    .sort((a, b) => a.triage.rank - b.triage.rank);
  return <TriageDashboard key={`${mode}-${mode === "fema" ? offset : depth}`} rows={rows} mode={mode} depth={depth} offset={offset} dataSource={getDataSource()} />;
}
