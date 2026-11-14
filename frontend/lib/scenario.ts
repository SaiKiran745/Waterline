import type { Asset, Assumption, ScenarioResult } from "./contracts";

export function computeScenario(
  buildingId: string,
  assets: Asset[],
  depthFt: number,
  assumptions: Assumption[],
): ScenarioResult {
  const assetsHit: ScenarioResult["assets_hit"] = [];
  for (const asset of assets) {
    if (depthFt >= asset.height_ft_high) assetsHit.push({ asset_id: asset.id, status: "likely" });
    else if (depthFt >= asset.height_ft_low) assetsHit.push({ asset_id: asset.id, status: "possible" });
  }

  const likelyIds = new Set(assetsHit.filter((hit) => hit.status === "likely").map((hit) => hit.asset_id));
  const possibleIds = new Set(assetsHit.map((hit) => hit.asset_id));

  return {
    building_id: buildingId,
    depth_ft: depthFt,
    depth_reference: "interior water depth above ground-floor slab",
    loss_usd_low: assets.reduce((sum, asset) => sum + (likelyIds.has(asset.id) ? asset.value_usd_low : 0), 0),
    loss_usd_high: assets.reduce((sum, asset) => sum + (possibleIds.has(asset.id) ? asset.value_usd_high : 0), 0),
    assets_hit: assetsHit,
    structure_loss_usd_low: 0,
    structure_loss_usd_high: 0,
    assumptions,
  };
}

export function hitMap(scenario: ScenarioResult) {
  return new Map(scenario.assets_hit.map((hit) => [hit.asset_id, hit.status]));
}
