"use client";

import { useState } from "react";
import { AssetList } from "./AssetList";
import { MitigationTable } from "./MitigationTable";
import { AgentTrace } from "./AgentTrace";
import { ApprovePanel } from "./ApprovePanel";
import { AerialPanel } from "./AerialPanel";
import type { AgentSessionController } from "@/hooks/useAgentSession";
import type { AssetDamage, BuildingBundle, ScenarioResult } from "@/lib/contracts";

const tabs = [
  { id: "agent", label: "Agent" }, { id: "assets", label: "Assets" }, { id: "fixes", label: "Fixes" }, { id: "site", label: "Site" }, { id: "send", label: "Send" },
] as const;
type TabId = (typeof tabs)[number]["id"];

export function DetailTabs({ bundle, scenario, damageByAsset, dataSource, selectedAssetId, memoryAppliedAssetIds, onSelectAsset, onCorrect, correctionState, session }: { bundle: BuildingBundle; scenario: ScenarioResult; damageByAsset: Map<string, AssetDamage>; dataSource: string; selectedAssetId: string | null; memoryAppliedAssetIds: Set<string>; onSelectAsset: (assetId: string) => void; onCorrect: (assetId: string, method: "PATCH" | "DELETE", changes: Record<string, unknown>) => Promise<void>; correctionState: { kind: "idle" | "saving" | "success" | "error"; message: string }; session: AgentSessionController; traceRequest: number }) {
  const [tab, setTab] = useState<TabId>("agent");
  return (
    <aside className="glass-rail">
      <div className="rail-tabs" role="tablist" aria-label="Building details">
        {tabs.map((item) => <button key={item.id} role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}>{item.label}{item.id === "agent" && session.status?.running ? <i className="trace-live" /> : null}</button>)}
      </div>
      <div className="rail-content" role="tabpanel">
        {tab === "agent" ? <AgentTrace buildingId={bundle.building.id} fixtureEvents={bundle.events} dataSource={dataSource} session={session} /> : null}
        {tab === "assets" ? <AssetList assets={bundle.assets} scenario={scenario} damageByAsset={damageByAsset} selectedAssetId={selectedAssetId} memoryAppliedAssetIds={memoryAppliedAssetIds} onSelectAsset={onSelectAsset} onCorrect={onCorrect} correctionState={correctionState} correctionsEnabled={dataSource === "api"} /> : null}
        {tab === "fixes" ? <MitigationTable buildingId={bundle.building.id} mitigations={bundle.mitigations} currentDepth={scenario.depth_ft} dataSource={dataSource} /> : null}
        {tab === "site" ? <AerialPanel building={bundle.building} entryPoints={bundle.entryPoints} media={bundle.media} events={bundle.events} dataSource={dataSource} /> : null}
        {tab === "send" ? <ApprovePanel building={bundle.building} mitigations={bundle.mitigations} currentDepth={scenario.depth_ft} dataSource={dataSource} session={session} /> : null}
      </div>
    </aside>
  );
}
