"use client";

import { useState } from "react";
import { PanelState } from "./PanelState";
import type { Building, EntryPoint } from "@/lib/contracts";

const markerPositions = [
  { left: "62%", top: "67%" },
  { left: "74%", top: "49%" },
  { left: "28%", top: "36%" },
];

export function AerialPanel({ building, entryPoints }: { building: Building; entryPoints: EntryPoint[] }) {
  const [activeId, setActiveId] = useState(entryPoints[0]?.id ?? "");
  const active = entryPoints.find((entry) => entry.id === activeId);
  return (
    <aside className="aerial-panel panel-frame">
      <div className="panel-title">
        <div><span className="eyebrow">01 / SITE SCOUT</span><h2>Entry points</h2></div>
        <span className="confidence-chip">{entryPoints.length} FOUND</span>
      </div>
      {entryPoints.length === 0 ? <PanelState kind="empty" title="No entry points" detail="The site survey has not produced markers yet." /> : (
        <>
          <div className="aerial-visual">
            <div className="aerial-grid" />
            <div className="building-footprint"><i /><i /><i /><span>FIXTURE AERIAL<br />IMAGE UNAVAILABLE</span></div>
            <div className="north">N ↑</div>
            {entryPoints.map((entry, index) => (
              <button
                key={entry.id}
                className={`entry-marker ${activeId === entry.id ? "active" : ""}`}
                style={markerPositions[index % markerPositions.length]}
                onMouseEnter={() => setActiveId(entry.id)}
                onFocus={() => setActiveId(entry.id)}
                onClick={() => setActiveId(entry.id)}
                aria-label={`${entry.kind} entry point`}
              >{index + 1}<span className="entry-tooltip">{entry.evidence}</span></button>
            ))}
          </div>
          {active ? (
            <div className="entry-evidence">
              <div><span className="entry-index">{String(entryPoints.indexOf(active) + 1).padStart(2, "0")}</span><span><b>{active.kind.replace("_", " ")}</b><small>{active.image_kind} · {Math.round(active.confidence * 100)}% confidence</small></span></div>
              <p>{active.evidence}</p>
              <dl><div><dt>THRESHOLD</dt><dd>{active.threshold_elevation_ft == null ? "Not measured" : `${active.threshold_elevation_ft} ft`}</dd></div><div><dt>GROUND</dt><dd>{building.ground_elevation_ft?.toFixed(1) ?? "—"} ft</dd></div></dl>
            </div>
          ) : null}
          <div className="entry-list">
            {entryPoints.map((entry, index) => <button className={entry.id === activeId ? "active" : ""} key={entry.id} onClick={() => setActiveId(entry.id)}><span>{index + 1}</span>{entry.kind.replace("_", " ")}<i>{Math.round(entry.confidence * 100)}%</i></button>)}
          </div>
        </>
      )}
      <div className="panel-source">VEXCEL · {building.aerial_collection ?? "COLLECTION UNKNOWN"} · {building.aerial_capture_date ?? "DATE UNKNOWN"}</div>
    </aside>
  );
}
