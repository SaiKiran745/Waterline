"use client";

import { useMemo, useState } from "react";
import { Brand } from "./Brand";
import { AerialPanel } from "./AerialPanel";
import { Viewer3D } from "./Viewer3D";
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
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const scenario = useMemo(
    () => computeScenario(bundle.building.id, bundle.assets, depth, bundle.scenario.assumptions),
    [bundle.assets, bundle.building.id, bundle.scenario.assumptions, depth],
  );
  const scannedPercent = bundle.building.scan_area_sqft && bundle.building.size_sqft
    ? Math.min(100, Math.round((bundle.building.scan_area_sqft / bundle.building.size_sqft) * 100))
    : null;

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
        <AerialPanel building={bundle.building} entryPoints={bundle.entryPoints} />
        <section className="viewer-column">
          <div className="viewer-toolbar">
            <div className="view-toggle" role="group" aria-label="Interior view">
              <button className={view === "model" ? "active" : ""} onClick={() => setView("model")}>3D MODEL</button>
              <button className={view === "rooms" ? "active" : ""} onClick={() => setView("rooms")}>ROOM SAFETY VIEW</button>
            </div>
            <span className="scenario-label">SCENARIO · NOT A PREDICTION</span>
          </div>
          <div className="viewer-stage">
            {view === "model" ? (
              <Viewer3D assets={bundle.assets} scenario={scenario} depthFt={depth} meshUrl={bundle.meshUrl} />
            ) : (
              <RoomGrid assets={bundle.assets} scenario={scenario} depthFt={depth} />
            )}
            <div className="viewer-overlay top-left">
              <span>INTERIOR WATER</span><strong>{depth.toFixed(2)}<small> FT</small></strong>
            </div>
            <div className="viewer-overlay bottom-left">
              <span className="legend-dot clear" /> CLEAR <span className="legend-dot possible" /> POSSIBLE <span className="legend-dot likely" /> LIKELY
            </div>
          </div>
          <div className="scenario-console">
            <LossCounter scenario={scenario} scannedPercent={scannedPercent} />
            <WaterSlider depth={depth} onChange={setDepth} />
            <button className="assumptions-button" onClick={() => setAssumptionsOpen(true)}>
              <span>ASSUMPTIONS</span><b>{scenario.assumptions.length}</b>
            </button>
          </div>
        </section>
        <DetailTabs bundle={bundle} scenario={scenario} dataSource={dataSource} />
      </section>
      <AssumptionsDrawer open={assumptionsOpen} onClose={() => setAssumptionsOpen(false)} assumptions={scenario.assumptions} />
    </main>
  );
}
