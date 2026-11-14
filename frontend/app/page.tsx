import { TriageDashboard } from "@/components/TriageDashboard";
import { getBuildings, getDataSource, getTriage } from "@/lib/data";

export default async function HomePage({ searchParams }: { searchParams: Promise<{ depth_ft?: string }> }) {
  const requested = Number((await searchParams).depth_ft ?? 2);
  const depth = ([1, 2, 4, 6] as const).find((value) => value === requested) ?? 2;
  const [buildings, triage] = await Promise.all([getBuildings(), getTriage(depth)]);
  const buildingById = new Map(buildings.map((building) => [building.id, building]));
  const rows = triage
    .map((ranking) => ({ building: buildingById.get(ranking.building_id), triage: ranking }))
    .filter((row): row is { building: NonNullable<typeof row.building>; triage: typeof row.triage } => Boolean(row.building))
    .sort((a, b) => a.triage.rank - b.triage.rank);
  return <TriageDashboard key={depth} rows={rows} depth={depth} dataSource={getDataSource()} />;
}
