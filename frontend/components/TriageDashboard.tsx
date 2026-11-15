"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { Brand } from "./Brand";
import { buildingLabel, floodZoneLabel, formatAddress, propertyTypeLabel, showAddresses } from "@/lib/presentation";
import type { Building, TriageElevationRow, TriageRow } from "@/lib/contracts";

const BuildingMap = dynamic(() => import("./BuildingMap").then((module) => module.BuildingMap), { ssr: false, loading: () => <div className="map-loading">Plotting properties…</div> });
export type DashboardRow = { building: Building; triage: TriageRow | TriageElevationRow };

function money(value: number) { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumSignificantDigits: 3 }).format(value); }
function isElevation(row: DashboardRow["triage"]): row is TriageElevationRow { return "elevation" in row; }
function depthLoss(row: DashboardRow, depth: 1 | 2 | 4 | 6) { return isElevation(row.triage) ? row.triage.loss : row.triage.loss_by_depth_ft[String(depth) as "1" | "2" | "4" | "6"]; }

export function TriageDashboard({ rows, mode, depth, offset, dataSource }: { rows: DashboardRow[]; mode: "fema" | "depth"; depth: 1 | 2 | 4 | 6; offset: 0 | 1 | 2 | 3; dataSource: string }) {
  const [selectedId, setSelectedId] = useState(rows[0]?.building.id ?? "");
  const outsideCount = rows.filter((item) => item.building.in_mapped_flood_zone === false).length;
  const highestIsOutside = rows[0]?.building.in_mapped_flood_zone === false;
  const stormLabel = offset === 0 ? "FEMA’s 1% flood level" : `FEMA’s 1% flood level + ${offset} ft`;
  const wetCount = rows.filter((item) => isElevation(item.triage) && item.triage.elevation === "ok" && (item.triage.interior_depth_ft ?? 0) > 0).length;
  return (
    <main className="landing-stage">
      <section className="landing-map"><BuildingMap rows={rows} mode={mode} depth={depth} selectedId={selectedId} onSelect={setSelectedId} /></section>
      <header className="landing-topline"><Brand /><span><i className={`live-dot ${dataSource}`} />Houston portfolio</span></header>
      <section className="landing-story">
        {mode === "fema"
          ? <h1>At {stormLabel}, water gets inside <b>{wetCount} of {rows.length}</b> buildings.</h1>
          : <h1><b>{outsideCount} of {rows.length}</b> buildings sit outside the 1% flood zone.<br />The highest-loss building {highestIsOutside ? "is one of them." : "is inside it."}</h1>}
        <p>{mode === "fema" ? "One outside water level, set against each building’s estimated floor." : `The same ${depth} ft of water inside every building.`}</p>
        <div className="ranking-mode" role="group" aria-label="Portfolio comparison mode"><Link className={mode === "fema" ? "active" : ""} href="/?mode=fema&offset_ft=0">Same storm</Link><Link className={mode === "depth" ? "active" : ""} href={`/?mode=depth&depth_ft=${depth}`}>Same depth</Link></div>
        {mode === "fema" ? <div className="landing-depth" aria-label="Offset above FEMA level">{([0, 1, 2, 3] as const).map((value) => <Link key={value} className={value === offset ? "active" : ""} href={`/?mode=fema&offset_ft=${value}`}>{value === 0 ? "FEMA 1%" : `+${value} ft`}</Link>)}</div> : <div className="landing-depth" aria-label="Portfolio water depth">{([1, 2, 4, 6] as const).map((value) => <Link key={value} className={value === depth ? "active" : ""} href={`/?mode=depth&depth_ft=${value}`}>{value} ft</Link>)}</div>}
        <div className="landing-key"><span><i className="outside" />Outside 1% zone</span><span><i className="inside" />Inside 1% zone</span><span><i className="size" />Size shows median loss</span></div>
      </section>
      {rows.length === 0 ? <div className="state-card"><h2>No buildings in this data source.</h2><p>Connect the API or add a valid contract fixture.</p></div> : <aside className={`landing-rail mode-${mode}`}>
        <header><div><h2>{mode === "fema" ? "Same storm" : "Same depth"}</h2></div><b>{rows.length} buildings</b></header>
        <div className="landing-ranks">{rows.map((item) => {
          const active = item.building.id === selectedId; const flood = floodZoneLabel(item.building); const loss = depthLoss(item, depth); const elevation = isElevation(item.triage) ? item.triage : null; const hasWater = elevation?.interior_depth_ft != null && elevation.interior_depth_ft > 0;
          return <Link href={`/building/${item.building.id}`} className={`landing-rank ${active ? "active" : ""}`} key={item.building.id} onMouseEnter={() => setSelectedId(item.building.id)} onFocus={() => setSelectedId(item.building.id)}>
            <span className="landing-rank-number">{String(item.triage.rank).padStart(2, "0")}</span>
            <span className="landing-rank-copy"><b>{buildingLabel(item.building)}</b><small>{propertyTypeLabel(item.building.property_type)} · Houston{showAddresses ? ` · ${formatAddress(item.building.address)}` : ""}</small><em>{item.triage.status} · {item.triage.positions_read} of {item.triage.scan_positions} positions read</em>{elevation ? <><span className="rank-sentence">{elevation.sentence || elevation.missing_reason}</span>{elevation.fema_at_building === false && (elevation.fema_distance_m ?? 0) > 500 ? <i className="weak-reference">Weak reference: the nearest FEMA level is {((elevation.fema_distance_m ?? 0) / 1000).toFixed(1)} km away</i> : null}</> : null}</span>
            <span className="landing-rank-risk">{elevation ? <small className="rank-depth">{elevation.elevation === "missing" ? "Depth unavailable" : hasWater ? `${elevation.interior_depth_ft?.toFixed(1)} ft inside (${elevation.interior_depth_ft_low?.toFixed(1)}–${elevation.interior_depth_ft_high?.toFixed(1)} ft)` : <><b>Water stays below the floor</b>{elevation.water_above_floor_ft != null ? ` · ${Math.abs(elevation.water_above_floor_ft).toFixed(1)} ft below` : ""}</>}</small> : null}<b>{loss ? `About ${money(loss.total_median)}` : "Loss unavailable"}</b>{loss ? <em>80% range {money(loss.total[0])} to {money(loss.total[1])}</em> : null}<small className={item.building.in_mapped_flood_zone ? "inside" : "outside"}>{flood.plain}</small></span>
          </Link>;
        })}</div>
      </aside>}
    </main>
  );
}
