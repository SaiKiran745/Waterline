import { notFound } from "next/navigation";
import { BuildingExperience } from "@/components/BuildingExperience";
import { getBuildingBundle, getDataSource } from "@/lib/data";

export default async function BuildingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const bundle = await getBuildingBundle(id);
  if (!bundle) notFound();
  return <BuildingExperience bundle={bundle} dataSource={getDataSource()} />;
}
