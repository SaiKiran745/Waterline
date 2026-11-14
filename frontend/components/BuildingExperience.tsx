"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Brand } from "./Brand";
import { AerialPanel } from "./AerialPanel";
import { Viewer3D } from "./Viewer3D";
import { MatterportViewer } from "./MatterportViewer";
import { PhotoRealViewer } from "./PhotoRealViewer";
import { RoomGrid } from "./RoomGrid";
import { WaterSlider } from "./WaterSlider";
import { LossCounter } from "./LossCounter";
import { DetailTabs } from "./DetailTabs";
import { AssumptionsDrawer } from "./AssumptionsDrawer";
import { assetDamageMap, scenarioFromTable, scenarioRow } from "@/lib/scenario";
import { correctAsset } from "@/lib/data";
import { buildingTitle, floodZoneLabel, showAddresses } from "@/lib/presentation";
import { useAgentSession } from "@/hooks/useAgentSession";
import type { BuildingBundle } from "@/lib/contracts";

export function BuildingExperience({ bundle, dataSource }: { bundle: BuildingBundle; dataSource: string }) {
  const [depth, setDepth] = useState(2);
  const [view, setView] = useState<"model" | "photo" | "rooms">(dataSource === "api" && bundle.building.matterport_model_id ? "photo" : "model");
  const [assets, setAssets] = useState(bundle.assets);
  const [scenarioTable, setScenarioTable] = useState(bundle.scenarioTable);
  const [mitigations, setMitigations] = useState(bundle.mitigations);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(bundle.assets[0]?.id ?? null);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [fallbackNotice, setFallbackNotice] = useState("");
  const [fallbackDetail, setFallbackDetail] = useState("");
  const [insideRequest, setInsideRequest] = useState(0);
  const [insideOverlayOpen, setInsideOverlayOpen] = useState(false);
  const [traceRequest, setTraceRequest] = useState(0);
  const [correctionState, setCorrectionState] = useState<{ kind: "idle" | "saving" | "success" | "error"; message: string }>({ kind: "idle", message: "" });
  const scenario = useMemo(() => scenarioFromTable(scenarioTable, depth), [scenarioTable, depth]);
  const row = useMemo(() => scenarioRow(scenarioTable, depth), [scenarioTable, depth]);
  const damageByAsset = useMemo(() => assetDamageMap(scenarioTable, depth), [scenarioTable, depth]);
  const scannedPercent = bundle.building.scan_coverage == null ? null : Math.round(bundle.building.scan_coverage * 100);
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId) ?? null;
  const session = useAgentSession(bundle.building.id, dataSource === "api");
  const lastAgentDepth = useRef(depth);
  const memoryCorrections = session.status?.memory.active_human_corrections ?? assets.filter((asset) => asset.source === "human").length;
  const memoryAppliedAssetIds = useMemo(() => new Set(session.status?.memory.applied_this_session_asset_ids ?? []), [session.status?.memory.applied_this_session_asset_ids]);
  const currentBundle = useMemo(() => ({ ...bundle, assets, scenarioTable, mitigations }), [assets, bundle, mitigations, scenarioTable]);
  const floodZone = floodZoneLabel(bundle.building);
  const agentStage = session.action === "run" ? "planning" : session.action === "depth" ? "re-planning" : session.status?.waiting_for_approval ? "waiting for approval" : session.status?.running ? ((session.status?.events ?? 0) < 3 ? "planning" : "surveying") : session.status?.run_id ? "done" : "idle";

  const handlePhotoFailure = useCallback((message: string) => {
    setFallbackNotice("Photo-real unavailable — offline 3D restored.");
    setFallbackDetail(message);
    setView("model");
  }, []);

  const retryPhotoReal = useCallback(() => {
    setFallbackNotice("");
    setFallbackDetail("");
    setView("photo");
  }, []);

  const handleAssetSelect = useCallback((assetId: string) => {
    setSelectedAssetId(assetId);
    setInsideOverlayOpen(true);
    if (view === "photo") setInsideRequest((value) => value + 1);
  }, [view]);

  const handleRun = async () => {
    setTraceRequest((value) => value + 1);
    try {
      await session.start(depth);
    } catch {
      // The exact endpoint response remains visible in the trace panel.
    }
  };

  const handleCorrection = async (assetId: string, method: "PATCH" | "DELETE", changes: Record<string, unknown>) => {
    setCorrectionState({ kind: "saving", message: method === "DELETE" ? "Removing asset and refreshing scenarios…" : "Saving correction and refreshing scenarios…" });
    try {
      const refreshed = await correctAsset(bundle.building.id, assetId, method, changes, depth);
      setAssets(refreshed.assets);
      setScenarioTable(refreshed.scenarioTable);
      setMitigations(refreshed.mitigations);
      await session.refresh();
      if (method === "DELETE") setSelectedAssetId(refreshed.assets[0]?.id ?? null);
      setCorrectionState({ kind: "success", message: `Scenario table and mitigations refreshed · portfolio rank at ${refreshed.rankDepth} ft ${refreshed.rank == null ? "pending" : `#${refreshed.rank}`}${refreshed.similarCount ? ` · ${refreshed.similarCount} similar assets flagged` : ""}.` });
    } catch (error) {
      setCorrectionState({ kind: "error", message: error instanceof Error ? error.message : "Correction failed." });
    }
  };

  const commitDepth = async (nextDepth: number) => {
    if (!session.active || session.busy || nextDepth === lastAgentDepth.current) return;
    try {
      await session.changeDepth(nextDepth);
      lastAgentDepth.current = nextDepth;
    } catch {
      // The exact endpoint response is shown in the agent trace and status rail.
    }
  };

  return (
    <main className="building-page">
      <header className="building-header">
        <Brand compact />
        <div className="building-title">
          <span className="eyebrow">FLOOD DOSSIER</span>
          <h1>{buildingTitle(bundle.building)}</h1>
          {showAddresses ? <p>{bundle.building.address}</p> : null}
        </div>
        <div className="agent-header-action">
          <button className="run-agent-button primary" disabled={session.busy || dataSource !== "api"} onClick={() => void handleRun()}>{session.action === "run" ? "STARTING AGENT…" : "RUN AGENT"}</button>
          <span className={`agent-stage stage-${agentStage.replaceAll(" ", "-")}`}><i />{agentStage}</span>
        </div>
        <div className="building-meta">
          <span className="flood-zone-meta"><small>FLOOD MAP</small><b>{floodZone.plain}</b>{floodZone.code ? <em>{floodZone.code}</em> : null}</span>
          <span className="survey-progress"><small>SURVEY</small><b>{bundle.triage ? `${bundle.triage.positions_read} of ${bundle.triage.scan_positions} positions read` : "Position count unavailable"}</b></span>
          <span className="agent-memory"><small>AGENT MEMORY</small><b>{memoryCorrections} corrections</b></span>
        </div>
      </header>

      <section className="building-workspace">
        <AerialPanel building={bundle.building} entryPoints={bundle.entryPoints} media={bundle.media} dataSource={dataSource} />
        <section className="viewer-column">
          <div className="viewer-toolbar">
            <div className="view-toggle" role="group" aria-label="Interior view">
              <button className={view === "model" ? "active" : ""} onClick={() => setView("model")}>3D MODEL</button>
              <button className={view === "photo" ? "active" : ""} disabled={dataSource !== "api" || !bundle.building.matterport_model_id} onClick={() => { setFallbackNotice(""); setFallbackDetail(""); setView("photo"); }}>PHOTO-REAL</button>
              <button className={view === "rooms" ? "active" : ""} onClick={() => setView("rooms")}>ROOM SAFETY VIEW</button>
            </div>
            <div className="scenario-status"><span className="scenario-label" title={fallbackDetail}>{fallbackNotice || "SCENARIO · NOT A PREDICTION"}</span>{fallbackNotice ? <button className="retry-photo-real" onClick={retryPhotoReal}>RETRY PHOTO-REAL</button> : null}</div>
            {selectedAsset ? <button className="view-selected-inside" onClick={() => { setInsideOverlayOpen(true); setInsideRequest((value) => value + 1); }}>VIEW SELECTED INSIDE</button> : null}
          </div>
          <div className="viewer-stage">
            {view === "model" ? (
              <div className="viewer-pane water-model-pane">
                <Viewer3D assets={assets} damageByAsset={damageByAsset} depthFt={depth} meshUrl={bundle.meshUrl} />
                <div className="viewer-overlay top-left">
                  <span>INTERIOR WATER</span><strong>{depth.toFixed(2)}<small> FT</small></strong>
                </div>
                <div className="viewer-overlay bottom-left">
                  <span className="legend-dot clear" /> CLEAR <span className="legend-dot possible" /> PARTIAL <span className="legend-dot likely" /> SEVERE <span className="legend-diamond" /> VEHICLE
                </div>
              </div>
            ) : view === "photo" ? <PhotoRealViewer modelId={bundle.building.matterport_model_id} assets={assets} damageByAsset={damageByAsset} depthFt={depth} locationId={selectedAsset?.location_id ?? null} locations={bundle.media?.locations ?? []} insideRequest={insideRequest} onFailure={handlePhotoFailure} /> : <RoomGrid assets={assets} damageByAsset={damageByAsset} depthFt={depth} />}
            {insideOverlayOpen ? <section className="inside-view-overlay" aria-label="Selected asset walkthrough">
              <header><div><span>SELECTED ASSET · INSIDE VIEW</span><b>{selectedAsset?.label ?? "Walkthrough"}</b></div><button onClick={() => setInsideOverlayOpen(false)} aria-label="Close inside view">CLOSE ×</button></header>
              <div className="inside-view-body"><MatterportViewer modelId={bundle.building.matterport_model_id} locationId={selectedAsset?.location_id ?? null} enabled={dataSource === "api"} /></div>
            </section> : null}
          </div>
          <div className="scenario-console">
            <div className="loss-console-group"><LossCounter row={row} scannedPercent={scannedPercent} /><button className="assumptions-button" onClick={() => setAssumptionsOpen(true)}><span>ASSUMPTIONS</span><b>({scenario.assumptions.length})</b></button></div>
            <WaterSlider depth={depth} onChange={setDepth} onCommit={commitDepth} />
          </div>
        </section>
        <DetailTabs key={`details-${traceRequest}`} bundle={currentBundle} scenario={scenario} damageByAsset={damageByAsset} dataSource={dataSource} selectedAssetId={selectedAssetId} memoryAppliedAssetIds={memoryAppliedAssetIds} onSelectAsset={handleAssetSelect} onCorrect={handleCorrection} correctionState={correctionState} session={session} traceRequest={traceRequest} />
      </section>
      <AssumptionsDrawer open={assumptionsOpen} onClose={() => setAssumptionsOpen(false)} assumptions={scenarioTable.assumptions} />
    </main>
  );
}
