"use client";

import { useEffect, useState } from "react";
import { PanelState } from "./PanelState";
import { getMitigationsForDepth } from "@/lib/data";
import type { Mitigation } from "@/lib/contracts";

const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

export function MitigationTable({ buildingId, mitigations, currentDepth, dataSource }: { buildingId: string; mitigations: Mitigation[]; currentDepth: number; dataSource: string }) {
  const [apiResult, setApiResult] = useState<{ depth: number; rows: Mitigation[] } | null>(null);
  const [requestState, setRequestState] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    if (dataSource !== "api") return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setRequestState("loading");
      try {
        const rows = await getMitigationsForDepth(buildingId, currentDepth, controller.signal);
        setApiResult({ depth: currentDepth, rows });
        setRequestState("idle");
      } catch {
        if (!controller.signal.aborted) setRequestState("error");
      }
    }, 120);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [buildingId, currentDepth, dataSource]);

  const exactFallback = mitigations.filter((item) => item.depth_ft === currentDepth);
  if (dataSource === "api" && requestState === "loading" && apiResult?.depth !== currentDepth && exactFallback.length === 0) return <PanelState kind="loading" title="Re-ranking fixes" detail={`Requesting the exact ${currentDepth.toFixed(2)} ft scenario.`} />;
  if (dataSource === "api" && requestState === "error" && exactFallback.length === 0) return <PanelState kind="error" title="Mitigations unavailable" detail={`The backend could not evaluate ${currentDepth.toFixed(2)} ft.`} />;

  const sourceRows = dataSource === "api" ? (apiResult?.depth === currentDepth ? apiResult.rows : exactFallback) : mitigations;
  if (sourceRows.length === 0) return <PanelState kind="empty" title="Survey pending" detail="Mitigations will appear after the interior survey and scenario model are ready." />;
  const availableDepths = [...new Set(sourceRows.map((item) => item.depth_ft))];
  const evaluatedDepth = dataSource === "api" ? currentDepth : availableDepths.reduce((nearest, candidate) => Math.abs(candidate - currentDepth) < Math.abs(nearest - currentDepth) ? candidate : nearest);
  const visibleMitigations = dataSource === "api" ? sourceRows : sourceRows.filter((item) => item.depth_ft === evaluatedDepth);
  return (
    <div className="mitigation-tab">
      <div className="tab-heading"><h2>Best next moves</h2><p>Ranked by avoided loss per dollar</p></div>
      {evaluatedDepth !== currentDepth ? <div className="depth-note">Showing the nearest evaluated fixes at {evaluatedDepth.toFixed(2)} ft; current slider is {currentDepth.toFixed(2)} ft.</div> : null}
      <div className="mitigation-list">
        {[...visibleMitigations].sort((a, b) => a.rank - b.rank).map((item) => (
          <article className="mitigation-row" key={item.id}>
            <div className="mitigation-rank"><span>#{item.rank}</span><i /></div>
            <div className="mitigation-body"><span>{item.kind.replaceAll("_", " ")}</span><b>{item.action}</b><p>{item.payback_note}</p></div>
            <dl><div><dt>Cost</dt><dd>{compact.format(item.cost_usd_low)}–{compact.format(item.cost_usd_high)}</dd></div><div><dt>Avoided</dt><dd><strong>About {compact.format(item.avoided_loss_usd_median)}</strong><small>80% range {compact.format(item.avoided_loss_usd_low)}–{compact.format(item.avoided_loss_usd_high)}</small></dd></div></dl>
          </article>
        ))}
      </div>
    </div>
  );
}
