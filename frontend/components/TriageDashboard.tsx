"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Brand } from "./Brand";
import { computeScenario } from "@/lib/scenario";
import type { Asset, Assumption, Building } from "@/lib/contracts";

const BuildingMap = dynamic(() => import("./BuildingMap").then((module) => module.BuildingMap), {
  ssr: false,
  loading: () => <div className="map-loading">Plotting properties…</div>,
});

type Row = { building: Building; assets: Asset[]; assumptions: Assumption[] };

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function TriageDashboard({ rows, dataSource }: { rows: Row[]; dataSource: string }) {
  const [depth, setDepth] = useState(2);
  const [selectedId, setSelectedId] = useState(rows[0]?.building.id ?? "");
  const ranked = useMemo(
    () => rows
      .map((row) => ({ ...row, scenario: computeScenario(row.building.id, row.assets, depth, row.assumptions) }))
      .sort((a, b) => b.scenario.loss_usd_high - a.scenario.loss_usd_high),
    [rows, depth],
  );

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
          <div><span>INTERIOR DEPTH</span><strong>{depth.toFixed(2)} ft</strong></div>
          <input aria-label="Portfolio water depth" type="range" min="0" max="8" step="0.25" value={depth} onChange={(event) => setDepth(Number(event.target.value))} />
          <small>Above ground-floor slab · scenario, not forecast</small>
        </div>
      </section>

      {ranked.length === 0 ? (
        <div className="state-card"><h2>No buildings in this data source.</h2><p>Connect the API or add a valid contract fixture.</p></div>
      ) : (
        <section className="triage-layout">
          <div className="map-shell">
            <BuildingMap buildings={ranked.map((item) => item.building)} selectedId={selectedId} onSelect={setSelectedId} />
            <div className="map-legend"><span><i className="map-dot selected" /> Selected</span><span><i className="map-dot" /> Assessed</span></div>
            <div className="map-caption">HOUSTON · LOCAL COORDINATE VIEW</div>
          </div>
          <aside className="ranking-panel">
            <div className="panel-heading-row">
              <div><span className="eyebrow">RISK ORDER</span><h2>Ranked loss</h2></div>
              <span className="count-chip">{ranked.length} {ranked.length === 1 ? "PROPERTY" : "PROPERTIES"}</span>
            </div>
            <div className="ranking-list">
              {ranked.map((item, index) => {
                const active = item.building.id === selectedId;
                return (
                  <button className={`rank-card ${active ? "active" : ""}`} key={item.building.id} onClick={() => setSelectedId(item.building.id)}>
                    <span className="rank-number">{String(index + 1).padStart(2, "0")}</span>
                    <span className="rank-body">
                      <b>{item.building.name ?? item.building.address}</b>
                      <small>{item.building.address}</small>
                      <span className="loss-range">{money(item.scenario.loss_usd_low)} – {money(item.scenario.loss_usd_high)}</span>
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
