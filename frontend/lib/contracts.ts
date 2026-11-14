export type Building = {
  id: string;
  name: string | null;
  address: string;
  lat: number;
  lng: number;
  property_type: string;
  property_subtype: string | null;
  size_sqft: number | null;
  size_basis: "GBA";
  year_built: number | null;
  stories: number | null;
  tenants: string[];
  value_usd: number | null;
  improvement_value_usd: number | null;
  value_as_of: string | null;
  value_source: string | null;
  loading_docks_external: number | null;
  drive_in_bays: number | null;
  matterport_model_id: string | null;
  matterport_model_ids: string[];
  scan_area_sqft: number | null;
  scan_coverage: number | null;
  in_mapped_flood_zone: boolean | null;
  flood_zone: string | null;
  flood_zone_subtype: string | null;
  flood_zone_source: string | null;
  ground_elevation_ft: number | null;
  ground_elevation_source: string | null;
  aerial_collection: string | null;
  aerial_capture_date: string | null;
};

export type EntryPoint = {
  id: string;
  building_id: string;
  kind: "door" | "dock" | "drive_in" | "ramp" | "garage" | "other";
  lat: number | null;
  lng: number | null;
  image_ref: string;
  image_kind: "ortho" | "oblique-north" | "oblique-south" | "oblique-east" | "oblique-west";
  image_xy: [number, number] | null;
  threshold_elevation_ft: number | null;
  elevation_source: string | null;
  confidence: number;
  evidence: string;
};

export type Asset = {
  id: string;
  building_id: string;
  matterport_model_id: string;
  floor_id: string | null;
  room_id: string | null;
  room: string;
  location_id: string;
  category: "electrical" | "it" | "hvac" | "inventory" | "equipment" | "furniture" | "finishes" | "other";
  label: string;
  height_ft_low: number;
  height_ft_high: number;
  confidence: number;
  value_usd_low: number;
  value_usd_high: number;
  value_basis: string;
  position: { x: number; y: number; z: number } | null;
  evidence: string;
  image_ref: string;
  observations: Array<{
    location_id: string;
    height_ft_low: number;
    height_ft_high: number;
    confidence: number;
    evidence: string;
    image_ref: string;
  }>;
  source: "vision" | "human" | "human-propagated";
};

export type Assumption = { id: string; text: string; source: string; placeholder: boolean };
export type HitStatus = "likely" | "possible";
export type ScenarioResult = {
  building_id: string;
  depth_ft: number;
  depth_reference: "interior water depth above ground-floor slab";
  loss_usd_low: number;
  loss_usd_high: number;
  assets_hit: Array<{ asset_id: string; status: HitStatus }>;
  structure_loss_usd_low: number;
  structure_loss_usd_high: number;
  assumptions: Assumption[];
};

export type ScenarioTableRow = {
  depth_ft: number;
  loss_usd_low: number;
  loss_usd_high: number;
  structure_loss_usd_low: number;
  structure_loss_usd_high: number;
  total_usd_low: number;
  total_usd_high: number;
  assets_hit: Array<{ asset_id: string; status: HitStatus }>;
};

export type ScenarioTableAsset = {
  asset_id: string;
  value_basis: string;
  value_usd_low: number;
  value_usd_high: number;
  critical_ft: number;
  movable: boolean;
  fraction_low: number[];
  fraction_high: number[];
};

export type ScenarioTable = {
  building_id: string;
  depth_reference: string;
  step_ft: number;
  steps_ft: number[];
  rows: ScenarioTableRow[];
  assets: ScenarioTableAsset[];
  assumptions: Assumption[];
};

export type AssetDamage = {
  status: HitStatus | "clear";
  fractionLow: number;
  fractionHigh: number;
  movable: boolean;
};

export type TriageLoss = {
  contents: [number, number];
  structure: [number, number];
  total: [number, number];
};

export type TriageRow = {
  building_id: string;
  rank: number;
  status: "surveyed" | "structure only";
  positions_read: number;
  scan_positions: number;
  contents_assets: number;
  note: string;
  loss_by_depth_ft: Record<"1" | "2" | "4" | "6", TriageLoss>;
};

export type Mitigation = {
  id: string;
  building_id: string;
  depth_ft: number;
  rank: number;
  kind: "raise_asset" | "relocate_asset" | "entry_barrier" | "move_inventory" | "other";
  action: string;
  targets: string[];
  cost_usd_low: number;
  cost_usd_high: number;
  avoided_loss_usd_low: number;
  avoided_loss_usd_high: number;
  payback_note: string;
  basis: string;
};

export type AgentEvent = {
  id: number;
  building_id: string;
  ts: string;
  agent: "orchestrator" | "site-scout" | "interior-surveyor" | "market-analyst" | "scenario-builder" | "mitigation-planner" | "communications";
  type: "plan" | "tool_call" | "observation" | "decision" | "replan" | "artifact" | "awaiting_approval";
  text: string;
  refs: string[];
  data: Record<string, unknown> | null;
};

export type MediaManifest = {
  building_id: string;
  mesh: { url: string; bytes: number; has_uv?: boolean; has_materials?: boolean } | null;
  aerial: Record<string, {
    url: string;
    meta_url: string;
    collection: string | null;
    capture_date: string | null;
    min_gsd_m: number | null;
    max_gsd_m: number | null;
  }>;
  panos?: Array<Record<string, unknown>>;
  floors?: Array<Record<string, unknown>>;
  rooms?: Array<Record<string, unknown>>;
  locations?: Array<Record<string, unknown>>;
  notes?: string[];
};

export type BuildingBundle = {
  building: Building;
  entryPoints: EntryPoint[];
  assets: Asset[];
  scenarioTable: ScenarioTable;
  mitigations: Mitigation[];
  events: AgentEvent[];
  meshUrl: string | null;
  media: MediaManifest | null;
};
