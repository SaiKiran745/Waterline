import { PanelState } from "./PanelState";
import { hitMap } from "@/lib/scenario";
import type { Asset, ScenarioResult } from "@/lib/contracts";

function money(low: number, high: number) {
  const format = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 0 });
  return `${format.format(low)}–${format.format(high)}`;
}

export function AssetList({ assets, scenario }: { assets: Asset[]; scenario: ScenarioResult }) {
  if (assets.length === 0) return <PanelState kind="empty" title="No assets inventoried" detail="Run the interior survey to populate this panel." />;
  const hits = hitMap(scenario);
  const sorted = [...assets].sort((a, b) => {
    const order = { likely: 0, possible: 1, clear: 2 };
    return order[hits.get(a.id) ?? "clear"] - order[hits.get(b.id) ?? "clear"];
  });
  return (
    <div className="asset-tab">
      <div className="tab-heading"><span className="eyebrow">02 / INTERIOR SURVEY</span><h2>Asset inventory</h2><p>Exposure at {scenario.depth_ft.toFixed(2)} ft</p></div>
      <div className="asset-summary">
        <span><b>{scenario.assets_hit.filter((hit) => hit.status === "likely").length}</b> LIKELY</span>
        <span><b>{scenario.assets_hit.filter((hit) => hit.status === "possible").length}</b> POSSIBLE</span>
        <span><b>{assets.length - scenario.assets_hit.length}</b> CLEAR</span>
      </div>
      <div className="asset-list">
        {sorted.map((asset) => {
          const status = hits.get(asset.id) ?? "clear";
          return (
            <article className={`asset-row ${status}`} key={asset.id}>
              <div className="asset-status"><i /><span>{status}</span></div>
              <div className="asset-main"><span className="asset-room">{asset.room} · {asset.category}</span><b>{asset.label}</b><small>{asset.height_ft_low}–{asset.height_ft_high} ft vulnerable height · {Math.round(asset.confidence * 100)}% confidence</small></div>
              <span className="asset-value">{money(asset.value_usd_low, asset.value_usd_high)}</span>
            </article>
          );
        })}
      </div>
    </div>
  );
}
