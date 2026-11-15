"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { Brand } from "./Brand";
import { buildingLabel, floodZoneLabel, formatAddress, propertyTypeLabel, showAddresses } from "@/lib/presentation";
import type { Building, TriageRow } from "@/lib/contracts";

const BuildingMap = dynamic(() => import("./BuildingMap").then((module) => module.BuildingMap), { ssr: false, loading: () => <div className="map-loading">Plotting properties…</div> });
type Row = { building: Building; triage: TriageRow };

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumSignificantDigits: 3 }).format(value);
}

export function TriageDashboard({ rows, depth, dataSource }: { rows: Row[]; depth: 1 | 2 | 4 | 6; dataSource: string }) {
  const [selectedId, setSelectedId] = useState(rows[0]?.building.id ?? "");
  const depthKey = String(depth) as "1" | "2" | "4" | "6";
  const outsideCount = rows.filter((item) => item.building.in_mapped_flood_zone === false).length;
  const highestLoss = rows.reduce<Row | null>((highest, item) => !highest || item.triage.loss_by_depth_ft[depthKey].total[1] > highest.triage.loss_by_depth_ft[depthKey].total[1] ? item : highest, null);
  const highestIsOutside = highestLoss?.building.in_mapped_flood_zone === false;

  return (
    <main className="landing-stage">
      <section className="landing-map"><BuildingMap rows={rows} depth={depth} selectedId={selectedId} onSelect={setSelectedId} /></section>
      <header className="landing-topline"><Brand /><span><i className={`live-dot ${dataSource}`} />Houston portfolio</span></header>

      <section className="landing-story">
        <span className="eyebrow">Portfolio flood triage · {depth.toFixed(2)} ft above slab</span>
        <h1><b>{outsideCount} of {rows.length}</b> buildings sit outside the 1% flood zone.<br />The highest-loss building {highestIsOutside ? "is one of them." : "is inside it."}</h1>
        <p>Flood maps stop at the front door. Waterline ranks what the water reaches inside.</p>
        <div className="landing-depth" aria-label="Portfolio water depth">{([1, 2, 4, 6] as const).map((option) => <Link key={option} className={option === depth ? "active" : ""} href={`/?depth_ft=${option}`}>{option} ft</Link>)}</div>
        <div className="landing-key"><span><i className="outside" />Outside 1% zone</span><span><i className="inside" />Inside 1% zone</span><span><i className="size" />Size shows loss</span></div>
      </section>

      {rows.length === 0 ? <div className="state-card"><h2>No buildings in this data source.</h2><p>Connect the API or add a valid contract fixture.</p></div> : (
        <aside className="landing-rail">
          <header><div><span className="eyebrow">Risk order</span><h2>Interior loss</h2></div><b>{rows.length} buildings</b></header>
          <div className="landing-ranks">
            {rows.map((item) => {
              const active = item.building.id === selectedId;
              const loss = item.triage.loss_by_depth_ft[depthKey];
              const flood = floodZoneLabel(item.building);
              return <Link href={`/building/${item.building.id}`} className={`landing-rank ${active ? "active" : ""}`} key={item.building.id} onMouseEnter={() => setSelectedId(item.building.id)} onFocus={() => setSelectedId(item.building.id)}>
                <span className="landing-rank-number">{String(item.triage.rank).padStart(2, "0")}</span>
                <span className="landing-rank-copy"><b>{buildingLabel(item.building)}</b><small>{propertyTypeLabel(item.building.property_type)} · Houston{showAddresses ? ` · ${formatAddress(item.building.address)}` : ""}</small><em>{item.triage.status} · {item.triage.positions_read} of {item.triage.scan_positions} positions read</em></span>
                <span className="landing-rank-risk"><b>{money(loss.total[0])} to {money(loss.total[1])}</b><small className={item.building.in_mapped_flood_zone ? "inside" : "outside"}>{flood.plain}</small></span>
              </Link>;
            })}
          </div>
        </aside>
      )}
    </main>
  );
}
