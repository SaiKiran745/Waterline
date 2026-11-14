"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { Brand } from "./Brand";
import type { Building, TriageRow } from "@/lib/contracts";

const BuildingMap = dynamic(() => import("./BuildingMap").then((module) => module.BuildingMap), {
  ssr: false,
  loading: () => <div className="map-loading">Plotting properties…</div>,
});

type Row = { building: Building; triage: TriageRow };

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function TriageDashboard({ rows, depth, dataSource }: { rows: Row[]; depth: 1 | 2 | 4 | 6; dataSource: string }) {
  const [selectedId, setSelectedId] = useState(rows[0]?.building.id ?? "");

  return (
    <main className="triage-page">
      <header className="topbar">
        <Brand />
        <div className="topbar-meta">
          <span className={`live-dot ${dataSource}`} />
          {dataSource === "fixture" ? "FIXTURE REPLAY" : "LIVE API"}
          <span className="divider" />
          HOUSTON, TX
        </div>
      </header>

      <section className="triage-heading">
        <div>
          <p className="eyebrow">PORTFOLIO TRIAGE / USER-CHOSEN SCENARIO</p>
          <h1>Where does the water<br /><em>cost the most?</em></h1>
        </div>
        <div className="depth-control compact-control">
          <div><span>TRIAGE DEPTH</span><strong>{depth.toFixed(2)} ft</strong></div>
          <div className="triage-depth-options" aria-label="Portfolio water depth">
            {([1, 2, 4, 6] as const).map((option) => <Link key={option} className={option === depth ? "active" : ""} href={`/?depth_ft=${option}`}>{option} FT</Link>)}
          </div>
          <small>Server-ranked · above ground-floor slab</small>
        </div>
      </section>

      {rows.length === 0 ? (
        <div className="state-card"><h2>No buildings in this data source.</h2><p>Connect the API or add a valid contract fixture.</p></div>
      ) : (
        <section className="triage-layout">
          <div className="map-shell">
            <BuildingMap buildings={rows.map((item) => item.building)} selectedId={selectedId} onSelect={setSelectedId} />
            <div className="map-legend"><span><i className="map-dot selected" /> Selected</span><span><i className="map-dot" /> Assessed</span></div>
            <div className="map-caption">HOUSTON · LOCAL COORDINATE VIEW</div>
          </div>
          <aside className="ranking-panel">
            <div className="panel-heading-row">
              <div><span className="eyebrow">RISK ORDER</span><h2>Ranked loss</h2></div>
              <span className="count-chip">{rows.length} {rows.length === 1 ? "PROPERTY" : "PROPERTIES"}</span>
            </div>
            <div className="ranking-list">
              {rows.map((item) => {
                const active = item.building.id === selectedId;
                const loss = item.triage.loss_by_depth_ft[String(depth) as "1" | "2" | "4" | "6"];
                const structureOnly = item.triage.status === "structure only";
                return (
                  <button className={`rank-card ${active ? "active" : ""} ${structureOnly ? "structure-only" : "surveyed"}`} key={item.building.id} onClick={() => setSelectedId(item.building.id)}>
                    <span className="rank-number">{String(item.triage.rank).padStart(2, "0")}</span>
                    <span className="rank-body">
                      <b>{item.building.name ?? item.building.address}</b>
                      <small>{item.building.address}</small>
                      <span className={`survey-status ${structureOnly ? "structure" : "surveyed"}`}>{item.triage.status}</span>
                      <span className="loss-range">{money(loss.total[0])} – {money(loss.total[1])}</span>
                      <span className="loss-basis">{structureOnly ? "STRUCTURE CURVE ONLY · NOT COMPARABLE · " : `${item.triage.contents_assets} CONTENTS ASSETS · `}{item.triage.positions_read} OF {item.triage.scan_positions} POSITIONS READ</span>
                    </span>
                    <span className={`zone-pill ${item.building.in_mapped_flood_zone ? "inside" : "outside"}`}>
                      FEMA {item.building.flood_zone ?? "—"}
                    </span>
                  </button>
                );
              })}
            </div>
            {selectedId ? <Link href={`/building/${selectedId}`} className="open-building">OPEN BUILDING DOSSIER <span>↗</span></Link> : null}
          </aside>
        </section>
      )}
      <footer className="portfolio-footer"><span>Waterline takes the water inside.</span><span>Loss range includes inventoried assets · assumptions disclosed in dossier</span></footer>
    </main>
  );
}
