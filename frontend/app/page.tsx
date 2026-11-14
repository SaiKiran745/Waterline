import { TriageDashboard } from "@/components/TriageDashboard";
import { getBuildings, getBuildingBundle, getDataSource } from "@/lib/data";

export default async function HomePage() {
  const buildings = await getBuildings();
  const rows = await Promise.all(
    buildings.map(async (building) => {
      const bundle = await getBuildingBundle(building.id);
      return { building, assets: bundle?.assets ?? [], assumptions: bundle?.scenario.assumptions ?? [] };
    }),
  );
  return <TriageDashboard rows={rows} dataSource={getDataSource()} />;
}
