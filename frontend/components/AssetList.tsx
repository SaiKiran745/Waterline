import { PanelState } from "./PanelState";
import { damageColour } from "@/lib/scenario";
import type { CSSProperties } from "react";
import type { Asset, AssetDamage, ScenarioResult } from "@/lib/contracts";

function money(low: number, high: number) {
  const format = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 0 });
  return `${format.format(low)}–${format.format(high)}`;
}

function measuredFromMesh(asset: Asset) {
  return [asset.evidence, ...asset.observations.map((item) => item.evidence)].some((text) => text.toLowerCase().includes("measured from mesh"));
}

export function AssetList({ assets, scenario, damageByAsset, selectedAssetId, onSelectAsset }: { assets: Asset[]; scenario: ScenarioResult; damageByAsset: Map<string, AssetDamage>; selectedAssetId: string | null; onSelectAsset: (assetId: string) => void }) {
  if (assets.length === 0) return <PanelState kind="empty" title="Survey pending" detail="The building is live, but its interior asset survey has not landed yet." />;
  const movableAssets = assets.filter((asset) => damageByAsset.get(asset.id)?.movable);
  const contentsAssets = assets.filter((asset) => !damageByAsset.get(asset.id)?.movable);
  const sorted = [...contentsAssets].sort((a, b) => {
    const order = { likely: 0, possible: 1, clear: 2 };
    return order[damageByAsset.get(a.id)?.status ?? "clear"] - order[damageByAsset.get(b.id)?.status ?? "clear"];
  });
  const likely = contentsAssets.filter((asset) => damageByAsset.get(asset.id)?.status === "likely").length;
  const possible = contentsAssets.filter((asset) => damageByAsset.get(asset.id)?.status === "possible").length;
  return (
    <div className="asset-tab">
      <div className="tab-heading"><span className="eyebrow">02 / INTERIOR SURVEY</span><h2>Asset inventory</h2><p>Exposure at {scenario.depth_ft.toFixed(2)} ft</p></div>
      <div className="asset-summary">
        <span><b>{likely}</b> LIKELY</span>
        <span><b>{possible}</b> POSSIBLE</span>
        <span><b>{contentsAssets.length - likely - possible}</b> CLEAR</span>
      </div>
      <div className="asset-list">
        {movableAssets.length > 0 ? <div className="movable-heading"><span className="vehicle-marker">◆</span><div><b>Movable assets at risk</b><small>Road vehicles are excluded from loss totals.</small></div></div> : null}
        {movableAssets.map((asset) => <AssetRow key={asset.id} asset={asset} damage={damageByAsset.get(asset.id)} selected={asset.id === selectedAssetId} movable onSelect={onSelectAsset} />)}
        {movableAssets.length > 0 ? <div className="contents-heading">CONTENTS INCLUDED IN LOSS</div> : null}
        {sorted.map((asset) => <AssetRow key={asset.id} asset={asset} damage={damageByAsset.get(asset.id)} selected={asset.id === selectedAssetId} onSelect={onSelectAsset} />)}
      </div>
    </div>
  );
}

function AssetRow({ asset, damage, selected, movable = false, onSelect }: { asset: Asset; damage?: AssetDamage; selected: boolean; movable?: boolean; onSelect: (assetId: string) => void }) {
  const status = damage?.status ?? "clear";
  const fraction = damage?.fractionHigh ?? 0;
  const observations = asset.observations;
  const before = observations[0];
  const after = observations[observations.length - 1];
  const style = { "--damage-color": damageColour(fraction) } as CSSProperties;
  return (
    <button style={style} className={`asset-row ${status} ${movable ? "movable" : ""} ${selected ? "selected" : ""}`} onClick={() => onSelect(asset.id)}>
      <div className="asset-status">{movable ? <i className="vehicle-shape">◆</i> : <i />}<span>{movable ? "MOVE" : `${Math.round(fraction * 100)}%`}</span></div>
      <div className="asset-main">
        <span className="asset-room">{asset.room} · {asset.category}</span>
        <b>{asset.label}</b>
        <small>{asset.height_ft_low}–{asset.height_ft_high} ft vulnerable height · {Math.round(asset.confidence * 100)}% confidence</small>
        {measuredFromMesh(asset) ? <span className="mesh-measured-badge">MEASURED FROM MESH</span> : null}
        {selected && observations.length > 1 ? (
          <span className="relook-comparison">
            <span><em>RE-LOOK BEFORE</em>{before.height_ft_low}–{before.height_ft_high} ft · {Math.round(before.confidence * 100)}%</span>
            <span><em>AFTER</em>{after.height_ft_low}–{after.height_ft_high} ft · {Math.round(after.confidence * 100)}%</span>
          </span>
        ) : null}
      </div>
      <span className="asset-value">{movable ? "EXCLUDED" : money(asset.value_usd_low, asset.value_usd_high)}</span>
    </button>
  );
}
