import type { Building } from "./contracts";

export const showAddresses = process.env.NEXT_PUBLIC_SHOW_ADDRESSES === "1";

export function buildingLabel(building: Pick<Building, "id">) {
  const slug = building.id.match(/^building-([a-z0-9]+)$/)?.[1];
  return slug ? `Building ${slug.toUpperCase()}` : "Building";
}

export function propertyTypeLabel(value: string) {
  const withKnownWords = value.replace(/generalretail/gi, "general retail");
  const spaced = withKnownWords.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  return spaced ? `${spaced[0].toUpperCase()}${spaced.slice(1)}` : "Property";
}

export function buildingTitle(building: Pick<Building, "id" | "property_type">) {
  return `${buildingLabel(building)} · ${propertyTypeLabel(building.property_type)} · Houston`;
}

export function floodZoneLabel(building: Pick<Building, "in_mapped_flood_zone" | "flood_zone">) {
  const plain = building.in_mapped_flood_zone == null
    ? "Flood-zone status unavailable"
    : building.in_mapped_flood_zone
      ? "Inside 1% flood zone"
      : "Outside 1% flood zone";
  return { plain, code: building.flood_zone ? `Zone ${building.flood_zone}` : null };
}
