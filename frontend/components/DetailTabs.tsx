"use client";

import { useState } from "react";
import { AssetList } from "./AssetList";
import { MitigationTable } from "./MitigationTable";
import { AgentTrace } from "./AgentTrace";
import { ApprovePanel } from "./ApprovePanel";
import type { AssetDamage, BuildingBundle, ScenarioResult } from "@/lib/contracts";

const tabs = [
  { id: "assets", label: "ASSETS" },
  { id: "mitigation", label: "FIXES" },
  { id: "trace", label: "TRACE" },
  { id: "approve", label: "APPROVE" },
] as const;

type TabId = (typeof tabs)[number]["id"];

export function DetailTabs({ bundle, scenario, damageByAsset, dataSource, selectedAssetId, onSelectAsset }: { bundle: BuildingBundle; scenario: ScenarioResult; damageByAsset: Map<string, AssetDamage>; dataSource: string; selectedAssetId: string | null; onSelectAsset: (assetId: string) => void }) {
  const [tab, setTab] = useState<TabId>("assets");
  return (
    <aside className="details-panel panel-frame">
      <div className="tab-list" role="tablist" aria-label="Building details">
        {tabs.map((item) => (
          <button key={item.id} role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}>
            {item.label}{item.id === "trace" ? <i className="trace-live" /> : null}
          </button>
        ))}
      </div>
      <div className="tab-content" role="tabpanel">
        {tab === "assets" ? <AssetList assets={bundle.assets} scenario={scenario} damageByAsset={damageByAsset} selectedAssetId={selectedAssetId} onSelectAsset={onSelectAsset} /> : null}
        {tab === "mitigation" ? <MitigationTable buildingId={bundle.building.id} mitigations={bundle.mitigations} currentDepth={scenario.depth_ft} dataSource={dataSource} /> : null}
        {tab === "trace" ? <AgentTrace buildingId={bundle.building.id} fixtureEvents={bundle.events} dataSource={dataSource} /> : null}
        {tab === "approve" ? <ApprovePanel building={bundle.building} mitigations={bundle.mitigations} dataSource={dataSource} /> : null}
      </div>
    </aside>
  );
}
