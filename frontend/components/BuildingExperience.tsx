"use client";

import { useCallback, useMemo, useState } from "react";
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
import type { BuildingBundle } from "@/lib/contracts";

export function BuildingExperience({ bundle, dataSource }: { bundle: BuildingBundle; dataSource: string }) {
  const [depth, setDepth] = useState(2);
  const [view, setView] = useState<"model" | "photo" | "rooms">("model");
  const [assets, setAssets] = useState(bundle.assets);
  const [scenarioTable, setScenarioTable] = useState(bundle.scenarioTable);
  const [mitigations, setMitigations] = useState(bundle.mitigations);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(bundle.assets[0]?.id ?? null);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [fallbackNotice, setFallbackNotice] = useState("");
  const [correctionState, setCorrectionState] = useState<{ kind: "idle" | "saving" | "success" | "error"; message: string }>({ kind: "idle", message: "" });
  const scenario = useMemo(() => scenarioFromTable(scenarioTable, depth), [scenarioTable, depth]);
  const row = useMemo(() => scenarioRow(scenarioTable, depth), [scenarioTable, depth]);
  const damageByAsset = useMemo(() => assetDamageMap(scenarioTable, depth), [scenarioTable, depth]);
  const scannedPercent = bundle.building.scan_coverage == null ? null : Math.round(bundle.building.scan_coverage * 100);
  const selectedAsset = assets.find((asset) => asset.id === selectedAssetId) ?? null;
  const currentBundle = useMemo(() => ({ ...bundle, assets, scenarioTable, mitigations }), [assets, bundle, mitigations, scenarioTable]);

  const handlePhotoFailure = useCallback((message: string) => {
    setFallbackNotice(`Photo-real view unavailable: ${message} Offline 3D model restored.`);
    setView("model");
  }, []);

  const handleCorrection = async (assetId: string, method: "PATCH" | "DELETE", changes: Record<string, unknown>) => {
    setCorrectionState({ kind: "saving", message: method === "DELETE" ? "Removing asset and refreshing scenarios…" : "Saving correction and refreshing scenarios…" });
    try {
      const refreshed = await correctAsset(bundle.building.id, assetId, method, changes, depth);
      setAssets(refreshed.assets);
      setScenarioTable(refreshed.scenarioTable);
      setMitigations(refreshed.mitigations);
      if (method === "DELETE") setSelectedAssetId(refreshed.assets[0]?.id ?? null);
      setCorrectionState({ kind: "success", message: `Scenario table and mitigations refreshed · portfolio rank ${refreshed.rank == null ? "pending" : `#${refreshed.rank}`}${refreshed.similarCount ? ` · ${refreshed.similarCount} similar assets flagged` : ""}.` });
    } catch (error) {
      setCorrectionState({ kind: "error", message: error instanceof Error ? error.message : "Correction failed." });
    }
  };

  return (
    <main className="building-page">
      <header className="building-header">
        <Brand compact />
        <div className="building-title">
          <span className="eyebrow">BUILDING DOSSIER / {bundle.building.property_type.toUpperCase()}</span>
          <h1>{bundle.building.name ?? bundle.building.address}</h1>
          <p>{bundle.building.address}</p>
        </div>
        <div className="building-meta">
          <span><small>FEMA ZONE</small><b>{bundle.building.flood_zone ?? "—"}</b></span>
          <span><small>GROUND EL.</small><b>{bundle.building.ground_elevation_ft?.toFixed(1) ?? "—"} ft</b></span>
          <span className={`source-badge ${dataSource}`}>{dataSource === "fixture" ? "FIXTURE" : "LIVE"}</span>
        </div>
      </header>

      <section className="building-workspace">
        <AerialPanel building={bundle.building} entryPoints={bundle.entryPoints} media={bundle.media} dataSource={dataSource} />
        <section className="viewer-column">
          <div className="viewer-toolbar">
            <div className="view-toggle" role="group" aria-label="Interior view">
              <button className={view === "model" ? "active" : ""} onClick={() => setView("model")}>3D MODEL</button>
              <button className={view === "photo" ? "active" : ""} disabled={dataSource !== "api" || !bundle.building.matterport_model_id} onClick={() => { setFallbackNotice(""); setView("photo"); }}>PHOTO-REAL</button>
              <button className={view === "rooms" ? "active" : ""} onClick={() => setView("rooms")}>ROOM SAFETY VIEW</button>
            </div>
            <span className="scenario-label">{fallbackNotice || "SCENARIO · NOT A PREDICTION"}</span>
          </div>
          <div className={`viewer-stage ${view === "model" ? "dual-view" : ""}`}>
            {view === "model" ? (
              <>
                <div className="viewer-pane water-model-pane">
                  <div className="pane-label">WATER MODEL</div>
                  <Viewer3D assets={assets} damageByAsset={damageByAsset} depthFt={depth} meshUrl={bundle.meshUrl} />
                  <div className="viewer-overlay top-left">
                    <span>INTERIOR WATER</span><strong>{depth.toFixed(2)}<small> FT</small></strong>
                  </div>
                  <div className="viewer-overlay bottom-left">
                    <span className="legend-dot clear" /> CLEAR <span className="legend-dot possible" /> PARTIAL <span className="legend-dot likely" /> SEVERE <span className="legend-diamond" /> VEHICLE
                  </div>
                </div>
                <div className="viewer-pane matterport-pane">
                  <div className="pane-label">MATTERPORT WALKTHROUGH</div>
                  <MatterportViewer modelId={bundle.building.matterport_model_id} locationId={selectedAsset?.location_id ?? null} enabled={dataSource === "api"} />
                </div>
              </>
            ) : view === "photo" ? <PhotoRealViewer modelId={bundle.building.matterport_model_id} assets={assets} damageByAsset={damageByAsset} depthFt={depth} locationId={selectedAsset?.location_id ?? null} locations={bundle.media?.locations ?? []} onFailure={handlePhotoFailure} /> : <RoomGrid assets={assets} damageByAsset={damageByAsset} depthFt={depth} />}
          </div>
          <div className="scenario-console">
            <LossCounter row={row} scannedPercent={scannedPercent} />
            <WaterSlider depth={depth} onChange={setDepth} />
            <button className="assumptions-button" onClick={() => setAssumptionsOpen(true)}>
              <span>ASSUMPTIONS</span><b>{scenario.assumptions.length}</b>
            </button>
          </div>
        </section>
        <DetailTabs bundle={currentBundle} scenario={scenario} damageByAsset={damageByAsset} dataSource={dataSource} selectedAssetId={selectedAssetId} onSelectAsset={setSelectedAssetId} onCorrect={handleCorrection} correctionState={correctionState} />
      </section>
      <AssumptionsDrawer open={assumptionsOpen} onClose={() => setAssumptionsOpen(false)} assumptions={scenarioTable.assumptions} />
    </main>
  );
}
