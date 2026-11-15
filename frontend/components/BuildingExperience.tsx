"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Brand } from "./Brand";
import { Viewer3D } from "./Viewer3D";
import { PhotoRealViewer } from "./PhotoRealViewer";
import { StaffGauge } from "./StaffGauge";
import { LossCounter } from "./LossCounter";
import { DetailTabs } from "./DetailTabs";
import { AssumptionsDrawer } from "./AssumptionsDrawer";
import { assetDamageMap, scenarioFromTable, scenarioRow } from "@/lib/scenario";
import { correctAsset } from "@/lib/data";
import { buildingTitle, floodZoneLabel, formatAddress, showAddresses } from "@/lib/presentation";
import { useAgentSession } from "@/hooks/useAgentSession";
import type { BuildingBundle } from "@/lib/contracts";

type FloodView = "dollhouse" | "inside" | "model";
const STARTING_DEPTH = 2;

export function BuildingExperience({ bundle, dataSource }: { bundle: BuildingBundle; dataSource: string }) {
  const photoAvailable = dataSource === "api" && Boolean(bundle.building.matterport_model_id);
  const [depth, setDepth] = useState(0);
  const [view, setView] = useState<FloodView>(photoAvailable ? "dollhouse" : "model");
  const [assets, setAssets] = useState(bundle.assets);
  const [scenarioTable, setScenarioTable] = useState(bundle.scenarioTable);
  const [mitigations, setMitigations] = useState(bundle.mitigations);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(bundle.assets[0]?.id ?? null);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [fallbackNotice, setFallbackNotice] = useState("");
  const [fallbackDetail, setFallbackDetail] = useState("");
  const [insideRequest, setInsideRequest] = useState(0);
  const [traceRequest, setTraceRequest] = useState(0);
  const [correctionState, setCorrectionState] = useState<{ kind: "idle" | "saving" | "success" | "error"; message: string }>({ kind: "idle", message: "" });
  const scenario = useMemo(() => scenarioFromTable(scenarioTable, depth), [scenarioTable, depth]);
  const row = useMemo(() => scenarioRow(scenarioTable, depth), [scenarioTable, depth]);
  const damageByAsset = useMemo(() => assetDamageMap(scenarioTable, depth), [scenarioTable, depth]);
  const scannedPercent = bundle.building.scan_coverage == null ? null : Math.round(bundle.building.scan_coverage * 100);
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId) ?? null;
  const session = useAgentSession(bundle.building.id, dataSource === "api");
  const lastAgentDepth = useRef(STARTING_DEPTH);
  const memoryCorrections = session.status?.memory.active_human_corrections ?? assets.filter((asset) => asset.source === "human").length;
  const memoryAppliedAssetIds = useMemo(() => new Set(session.status?.memory.applied_this_session_asset_ids ?? []), [session.status?.memory.applied_this_session_asset_ids]);
  const currentBundle = useMemo(() => ({ ...bundle, assets, scenarioTable, mitigations }), [assets, bundle, mitigations, scenarioTable]);
  const floodZone = floodZoneLabel(bundle.building);
  const agentStage = session.action === "run" ? "planning" : session.action === "depth" ? "re-planning" : session.status?.waiting_for_approval ? "waiting for approval" : session.status?.running ? ((session.status?.events ?? 0) < 3 ? "planning" : "surveying") : session.status?.run_id ? "done" : "idle";

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const timer = window.setTimeout(() => setDepth(STARTING_DEPTH), 0);
      return () => window.clearTimeout(timer);
    }
    const started = performance.now();
    let frame = 0;
    const rise = (now: number) => {
      const progress = Math.min(1, (now - started) / 1500);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDepth(Math.round(STARTING_DEPTH * eased * 4) / 4);
      if (progress < 1) frame = window.requestAnimationFrame(rise);
    };
    frame = window.requestAnimationFrame(rise);
    return () => window.cancelAnimationFrame(frame);
  }, []);

  const handlePhotoFailure = useCallback((message: string) => {
    setFallbackNotice("Photo-real view unavailable. Offline model restored.");
    setFallbackDetail(message);
    setView("model");
  }, []);

  const retryPhotoReal = useCallback(() => {
    setFallbackNotice("");
    setFallbackDetail("");
    setView("dollhouse");
  }, []);

  const handleAssetSelect = useCallback((assetId: string) => {
    setSelectedAssetId(assetId);
    if (photoAvailable) { setView("inside"); setInsideRequest((value) => value + 1); }
  }, [photoAvailable]);

  const handleRun = async () => {
    setTraceRequest((value) => value + 1);
    try { await session.start(depth); } catch { /* The trace preserves the exact endpoint response. */ }
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
    try { await session.changeDepth(nextDepth); lastAgentDepth.current = nextDepth; } catch { /* The agent rail renders the exact response. */ }
  };

  const selectView = (next: FloodView) => {
    if (next !== "model" && !photoAvailable) return;
    setFallbackNotice(""); setFallbackDetail(""); setView(next);
    if (next === "inside") setInsideRequest((value) => value + 1);
  };

  return (
    <main className="flood-stage">
      <section className="flood-canvas" aria-label="Flood scenario view">
        {view === "model" ? <Viewer3D assets={assets} damageByAsset={damageByAsset} depthFt={depth} meshUrl={bundle.meshUrl} selectedAssetId={selectedAssetId} /> : <PhotoRealViewer modelId={bundle.building.matterport_model_id} assets={assets} damageByAsset={damageByAsset} depthFt={depth} locationId={selectedAsset?.location_id ?? null} locations={bundle.media?.locations ?? []} insideRequest={insideRequest} requestedMode={view} onFailure={handlePhotoFailure} />}
      </section>

      <header className="stage-topline">
        <Brand compact />
        <div className="stage-building"><h1>{buildingTitle(bundle.building)}</h1>{showAddresses ? <p>{formatAddress(bundle.building.address)}</p> : null}</div>
        <div className="stage-facts">
          <span><b>{floodZone.plain}</b>{floodZone.code ? <small>{floodZone.code}</small> : null}</span>
          <span><b>{bundle.triage ? `${bundle.triage.positions_read} of ${bundle.triage.scan_positions} positions read` : "Position count unavailable"}</b><small>Agent memory: {memoryCorrections} corrections</small></span>
        </div>
        <div className="stage-run"><button className="run-agent-button" disabled={session.busy || dataSource !== "api"} onClick={() => void handleRun()}>{session.action === "run" ? "Starting…" : "Run agent"}</button><span className={`agent-stage stage-${agentStage.replaceAll(" ", "-")}`}><i />{agentStage}</span></div>
        <details className="stage-menu"><summary aria-label="Demo menu">•••</summary><button onClick={() => window.location.reload()}>Reset demo</button></details>
      </header>

      <div className="stage-gauge"><StaffGauge depth={depth} onChange={setDepth} onCommit={commitDepth} /></div>
      <div className="stage-loss"><LossCounter row={row} scannedPercent={scannedPercent} /><button className="assumptions-button" onClick={() => setAssumptionsOpen(true)}>Assumptions <b>({scenario.assumptions.length})</b></button></div>
      <div className="stage-controls">
        <div className="stage-key" aria-label="Asset damage key"><span><i className="key-ring clear" />Clear</span><span><i className="key-ring partial" />Partial</span><span><i className="key-ring lost" />Severe</span><span><i className="key-vehicle" />Vehicle</span></div>
        <div className="stage-view-switch" role="group" aria-label="Flood view"><button className={view === "dollhouse" ? "active" : ""} disabled={!photoAvailable} onClick={() => selectView("dollhouse")}>Dollhouse</button><button className={view === "inside" ? "active" : ""} disabled={!photoAvailable || !selectedAsset} onClick={() => selectView("inside")}>View selected inside</button><button className={view === "model" ? "active" : ""} onClick={() => selectView("model")}>3D model</button></div>
        {fallbackNotice ? <div className="stage-fallback" title={fallbackDetail}><span>{fallbackNotice}</span><button onClick={retryPhotoReal}>Retry photo-real</button></div> : null}
      </div>

      <DetailTabs key={`details-${traceRequest}`} bundle={currentBundle} scenario={scenario} damageByAsset={damageByAsset} dataSource={dataSource} selectedAssetId={selectedAssetId} memoryAppliedAssetIds={memoryAppliedAssetIds} onSelectAsset={handleAssetSelect} onCorrect={handleCorrection} correctionState={correctionState} session={session} traceRequest={traceRequest} />
      <AssumptionsDrawer open={assumptionsOpen} onClose={() => setAssumptionsOpen(false)} assumptions={scenarioTable.assumptions} />
    </main>
  );
}
