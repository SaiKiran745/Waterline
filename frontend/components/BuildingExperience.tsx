"use client";

import { useMemo, useState } from "react";
import { Brand } from "./Brand";
import { AerialPanel } from "./AerialPanel";
import { Viewer3D } from "./Viewer3D";
import { MatterportViewer } from "./MatterportViewer";
import { RoomGrid } from "./RoomGrid";
import { WaterSlider } from "./WaterSlider";
import { LossCounter } from "./LossCounter";
import { DetailTabs } from "./DetailTabs";
import { AssumptionsDrawer } from "./AssumptionsDrawer";
import { computeScenario } from "@/lib/scenario";
import type { BuildingBundle } from "@/lib/contracts";

export function BuildingExperience({ bundle, dataSource }: { bundle: BuildingBundle; dataSource: string }) {
  const [depth, setDepth] = useState(2);
  const [view, setView] = useState<"model" | "rooms">("model");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(bundle.assets[0]?.id ?? null);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const scenario = useMemo(
    () => computeScenario(bundle.building.id, bundle.assets, depth, bundle.scenario.assumptions),
    [bundle.assets, bundle.building.id, bundle.scenario.assumptions, depth],
  );
  const scannedPercent = bundle.building.scan_area_sqft && bundle.building.size_sqft
    ? Math.min(100, Math.round((bundle.building.scan_area_sqft / bundle.building.size_sqft) * 100))
    : null;
  const selectedAsset = bundle.assets.find((asset) => asset.id === selectedAssetId) ?? null;

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
              <button className={view === "rooms" ? "active" : ""} onClick={() => setView("rooms")}>ROOM SAFETY VIEW</button>
            </div>
            <span className="scenario-label">SCENARIO · NOT A PREDICTION</span>
          </div>
          <div className={`viewer-stage ${view === "model" ? "dual-view" : ""}`}>
            {view === "model" ? (
              <>
                <div className="viewer-pane water-model-pane">
                  <div className="pane-label">WATER MODEL</div>
                  <Viewer3D assets={bundle.assets} scenario={scenario} depthFt={depth} meshUrl={bundle.meshUrl} />
                  <div className="viewer-overlay top-left">
                    <span>INTERIOR WATER</span><strong>{depth.toFixed(2)}<small> FT</small></strong>
                  </div>
                  <div className="viewer-overlay bottom-left">
                    <span className="legend-dot clear" /> CLEAR <span className="legend-dot possible" /> POSSIBLE <span className="legend-dot likely" /> LIKELY
                  </div>
                </div>
                <div className="viewer-pane matterport-pane">
                  <div className="pane-label">MATTERPORT WALKTHROUGH</div>
                  <MatterportViewer modelId={bundle.building.matterport_model_id} locationId={selectedAsset?.location_id ?? null} enabled={dataSource === "api"} />
                </div>
              </>
            ) : (
              <RoomGrid assets={bundle.assets} scenario={scenario} depthFt={depth} />
            )}
          </div>
          <div className="scenario-console">
            <LossCounter scenario={scenario} scannedPercent={scannedPercent} />
            <WaterSlider depth={depth} onChange={setDepth} />
            <button className="assumptions-button" onClick={() => setAssumptionsOpen(true)}>
              <span>ASSUMPTIONS</span><b>{scenario.assumptions.length}</b>
            </button>
          </div>
        </section>
        <DetailTabs bundle={bundle} scenario={scenario} dataSource={dataSource} selectedAssetId={selectedAssetId} onSelectAsset={setSelectedAssetId} />
      </section>
      <AssumptionsDrawer open={assumptionsOpen} onClose={() => setAssumptionsOpen(false)} assumptions={scenario.assumptions} />
    </main>
  );
}
