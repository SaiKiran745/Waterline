import type { AssetDamage, ScenarioResult, ScenarioTable, ScenarioTableRow } from "./contracts";

export function scenarioIndex(table: ScenarioTable, depthFt: number) {
  const direct = table.steps_ft.findIndex((step) => Math.abs(step - depthFt) < 0.001);
  if (direct >= 0) return direct;
  return Math.max(0, Math.min(table.rows.length - 1, Math.round(depthFt / table.step_ft)));
}

export function scenarioRow(table: ScenarioTable, depthFt: number): ScenarioTableRow {
  return table.rows[scenarioIndex(table, depthFt)];
}

export function scenarioFromTable(table: ScenarioTable, depthFt: number): ScenarioResult {
  const row = scenarioRow(table, depthFt);
  return {
    building_id: table.building_id,
    depth_ft: row.depth_ft,
    depth_reference: "interior water depth above ground-floor slab",
    loss_usd_low: row.loss_usd_low,
    loss_usd_high: row.loss_usd_high,
    assets_hit: row.assets_hit,
    structure_loss_usd_low: row.structure_loss_usd_low,
    structure_loss_usd_high: row.structure_loss_usd_high,
    assumptions: table.assumptions,
  };
}

export function assetDamageMap(table: ScenarioTable, depthFt: number) {
  const index = scenarioIndex(table, depthFt);
  const statuses = new Map(table.rows[index].assets_hit.map((hit) => [hit.asset_id, hit.status]));
  return new Map<string, AssetDamage>(table.assets.map((asset) => [asset.asset_id, {
    status: statuses.get(asset.asset_id) ?? "clear",
    fractionLow: asset.fraction_low[index] ?? 0,
    fractionHigh: asset.fraction_high[index] ?? 0,
    movable: asset.movable,
  }]));
}

export function hitMap(scenario: ScenarioResult) {
  return new Map(scenario.assets_hit.map((hit) => [hit.asset_id, hit.status]));
}

export function damageColour(fraction: number) {
  if (fraction <= 0) return "#70d4c8";
  const amount = Math.max(0, Math.min(1, fraction));
  const amber = [241, 180, 95];
  const red = [255, 98, 93];
  const channel = (index: number) => Math.round(amber[index] + (red[index] - amber[index]) * amount);
  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`;
}
