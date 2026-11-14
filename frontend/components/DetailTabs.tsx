"use client";

import { useState } from "react";
import { AssetList } from "./AssetList";
import { MitigationTable } from "./MitigationTable";
import { AgentTrace } from "./AgentTrace";
import { ApprovePanel } from "./ApprovePanel";
import { FilesPanel } from "./FilesPanel";
import type { AgentSessionController } from "@/hooks/useAgentSession";
import type { AssetDamage, BuildingBundle, ScenarioResult } from "@/lib/contracts";

const tabs = [
  { id: "assets", label: "ASSETS" },
  { id: "mitigation", label: "FIXES" },
  { id: "trace", label: "TRACE" },
  { id: "files", label: "FILES" },
  { id: "approve", label: "APPROVE" },
] as const;

type TabId = (typeof tabs)[number]["id"];

export function DetailTabs({ bundle, scenario, damageByAsset, dataSource, selectedAssetId, memoryAppliedAssetIds, onSelectAsset, onCorrect, correctionState, session, traceRequest }: { bundle: BuildingBundle; scenario: ScenarioResult; damageByAsset: Map<string, AssetDamage>; dataSource: string; selectedAssetId: string | null; memoryAppliedAssetIds: Set<string>; onSelectAsset: (assetId: string) => void; onCorrect: (assetId: string, method: "PATCH" | "DELETE", changes: Record<string, unknown>) => Promise<void>; correctionState: { kind: "idle" | "saving" | "success" | "error"; message: string }; session: AgentSessionController; traceRequest: number }) {
  const [tab, setTab] = useState<TabId>(traceRequest > 0 ? "trace" : "assets");
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
        {tab === "assets" ? <AssetList assets={bundle.assets} scenario={scenario} damageByAsset={damageByAsset} selectedAssetId={selectedAssetId} memoryAppliedAssetIds={memoryAppliedAssetIds} onSelectAsset={onSelectAsset} onCorrect={onCorrect} correctionState={correctionState} correctionsEnabled={dataSource === "api"} /> : null}
        {tab === "mitigation" ? <MitigationTable buildingId={bundle.building.id} mitigations={bundle.mitigations} currentDepth={scenario.depth_ft} dataSource={dataSource} /> : null}
        {tab === "trace" ? <AgentTrace buildingId={bundle.building.id} fixtureEvents={bundle.events} dataSource={dataSource} session={session} /> : null}
        {tab === "files" ? <FilesPanel buildingId={bundle.building.id} live={Boolean(session.status?.running)} refreshVersion={session.streamVersion} dataSource={dataSource} /> : null}
        {tab === "approve" ? <ApprovePanel building={bundle.building} mitigations={bundle.mitigations} currentDepth={scenario.depth_ft} dataSource={dataSource} session={session} /> : null}
      </div>
    </aside>
  );
}
