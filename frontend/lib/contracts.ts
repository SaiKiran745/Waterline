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
  loss_usd_median: number;
  loss_usd_high: number;
  assets_hit: Array<{ asset_id: string; status: HitStatus }>;
  structure_loss_usd_low: number;
  structure_loss_usd_median: number;
  structure_loss_usd_high: number;
  total_usd_low: number;
  total_usd_median: number;
  total_usd_high: number;
  items_in_water: ItemsInWater;
  top_contributors: TopContributor[];
  standard_contents_usd_median: number | null;
  assumptions: Assumption[];
};

export type ScenarioTableRow = {
  depth_ft: number;
  loss_usd_low: number;
  loss_usd_median: number;
  loss_usd_high: number;
  structure_loss_usd_low: number;
  structure_loss_usd_median: number;
  structure_loss_usd_high: number;
  total_usd_low: number;
  total_usd_median: number;
  total_usd_high: number;
  assets_hit: Array<{ asset_id: string; status: HitStatus }>;
  items_in_water: ItemsInWater;
  top_contributors: TopContributor[];
  standard_contents_usd_median: number | null;
};

export type ItemsInWater = { of: number; count_low: number; count_high: number; share_low: number; share_high: number };
export type TopContributor = { asset_id: string; expected_loss_usd: number; share: number };

export type ScenarioTableAsset = {
  asset_id: string;
  value_basis: string;
  value_usd_low: number;
  value_usd_high: number;
  critical_ft: number;
  movable: boolean;
  expected_loss_usd: number[];
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
  thresholds: ScenarioThresholds;
  standard_method: StandardMethod;
};

export type Range = [number, number];
export type ScenarioThresholds = {
  contents_items: number;
  heights_from_mesh: number;
  heights_estimated: number;
  // null when the building has no surveyed items of that kind (contracts/scenario_table.schema.json), e.g. no IT equipment.
  first_loss_ft: Range | null;
  half_items_ft: Range | null;
  most_items_ft: Range | null;
  critical_systems: Array<{ system: string; name: string; items: number; first_reached_ft: Range | null }>;
};

export type StandardMethod = {
  method: string;
  functions: Array<{ kind: string; function_id: number; description: string; source: string; pct_at_1_2_4_6_ft: number[] }>;
  citation: string;
  source_url: string;
  value_basis: string;
  compare: Array<{ depth_ft: number; ours_median_usd: number; standard_median_usd: number; ratio: number; verdict: string }>;
  statement: string;
  why_shapes_differ: string;
  share_of_value_below_1ft: number;
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
  contents_median: number;
  structure_median: number;
  total_median: number;
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

export type TriageElevationRow = {
  building_id: string;
  rank: number;
  status: "surveyed" | "structure only";
  positions_read: number;
  scan_positions: number;
  contents_assets: number;
  note: string;
  elevation: "ok" | "missing";
  missing_reason: string | null;
  offset_ft: 0 | 1 | 2 | 3;
  water_level_ft: number | null;
  water_level_ft_low: number | null;
  water_level_ft_high: number | null;
  fema_level_ft: number | null;
  fema_distance_m: number | null;
  fema_at_building: boolean | null;
  floor_ft: number | null;
  floor_ft_low: number | null;
  floor_ft_high: number | null;
  floor_above_fema_ft: number | null;
  water_above_floor_ft: number | null;
  interior_depth_ft: number | null;
  interior_depth_ft_low: number | null;
  interior_depth_ft_high: number | null;
  depth_capped: boolean;
  loss: TriageLoss | null;
  total_median_at_depth_range: Range | null;
  sentence: string;
  depth_sentence: string;
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
  avoided_loss_usd_median: number;
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

export type AgentTurn = {
  turn: string;
  seconds: number;
  model_calls: number;
  cost_usd: number;
  interrupted: boolean;
};

export type AgentCorrection = {
  id: string;
  asset_id: string;
  action: "patch" | "delete";
  changes: Record<string, unknown>;
  note: string;
  at: string;
};

export type AgentMemory = {
  active_human_corrections: number;
  human_corrections: AgentCorrection[];
  applied_this_session: number;
  applied_this_session_asset_ids: string[];
};

export type AgentDelivery = {
  status: "sent" | "draft_only" | "refused" | "failed";
  recipient: string;
  at: string;
  detail: string;
};

export type AgentStatus = {
  building_id: string;
  session?: null;
  run_id?: string;
  running?: boolean;
  waiting_for_approval?: boolean;
  turns?: AgentTurn[];
  events?: number;
  error?: string | null;
  events_url?: string;
  status?: string;
  memory: AgentMemory;
  last_delivery: AgentDelivery | null;
};

export type ReplayRun = {
  status: "replay";
  building_id: string;
  run_id: string;
  recorded_at: string;
  events: number;
  seconds: number;
  cost_usd: number;
  model_calls: number;
  turns: AgentTurn[];
  replay: true;
  label: string;
  events_url: string;
};

export type DossierFile = {
  path: string;
  bytes: number;
  modified: string;
  content: string;
};

export type Dossier = {
  building_id: string;
  files: DossierFile[];
};

export type AgentActionResult = (AgentStatus | ReplayRun) & {
  result?: Record<string, unknown> | null;
  recipient?: string;
  message?: string;
  reason?: string;
};

export type MatterportLocation = {
  id: string;
  position: { x: number; y: number; z: number };
  floor?: string | null;
  room?: string | null;
  label?: string | null;
  neighbors?: string[];
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
  locations?: MatterportLocation[];
  notes?: string[];
};

export type GroundingEntryPoint = { entry_point_id: string; kind: string; side: string; ground_ft: number; rank: number; above_lowest_door_ft: number };
export type GroundingReferenceLevel = {
  id: string;
  label: string;
  elevation_ft: number;
  elevation_ft_low: number;
  elevation_ft_high: number;
  depth_above_floor_ft: number;
  depth_above_floor_ft_low: number;
  depth_above_floor_ft_high: number;
  source: string;
  sentence: string;
};
export type Grounding = {
  building_id: string;
  computed_at: string;
  method: string;
  datum: { name: string; units: string; match: boolean; note: string };
  ground: { source: string; accuracy_rmse_ft: number; points: number; lowest_adjacent_ft: number; highest_adjacent_ft: number; low_side: string; high_side: string; around_min_ft: number; around_max_ft: number; sentence: string };
  entry_points: GroundingEntryPoint[];
  first_door: { entry_point_id: string | null; lead_ft: number | null; sentence: string };
  floor: { elevation_ft: number; elevation_ft_low: number; elevation_ft_high: number; ground_ft: Range; allowance_id: string; allowance_ft: Range; basis: string; chosen_because: string };
  fema_1pct: { found: boolean; elevation_ft?: number; elevation_ft_low?: number; elevation_ft_high?: number; nearest_distance_m?: number; relative_to_floor_ft?: number; relative_to_floor_ft_low?: number; relative_to_floor_ft_high?: number; sentence?: string; source?: string };
  reference_levels: GroundingReferenceLevel[];
  steps: Array<{ depth_ft: number; water_surface_ft: number; water_surface_ft_low: number; water_surface_ft_high: number }>;
  assumptions: Assumption[];
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
  triage: TriageRow | null;
  grounding: Grounding | null;
};
