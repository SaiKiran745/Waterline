import { PanelState } from "./PanelState";
import type { Mitigation } from "@/lib/contracts";

const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

export function MitigationTable({ mitigations, currentDepth }: { mitigations: Mitigation[]; currentDepth: number }) {
  if (mitigations.length === 0) return <PanelState kind="empty" title="No mitigations ranked" detail="The planner has not evaluated fixes for this scenario." />;
  const availableDepths = [...new Set(mitigations.map((item) => item.depth_ft))];
  const evaluatedDepth = availableDepths.reduce((nearest, candidate) => Math.abs(candidate - currentDepth) < Math.abs(nearest - currentDepth) ? candidate : nearest);
  const visibleMitigations = mitigations.filter((item) => item.depth_ft === evaluatedDepth);
  return (
    <div className="mitigation-tab">
      <div className="tab-heading"><span className="eyebrow">03 / MITIGATION PLANNER</span><h2>Best next moves</h2><p>Ranked by avoided loss per dollar</p></div>
      {evaluatedDepth !== currentDepth ? <div className="depth-note">Showing the nearest evaluated fixes at {evaluatedDepth.toFixed(2)} ft; current slider is {currentDepth.toFixed(2)} ft.</div> : null}
      <div className="mitigation-list">
        {[...visibleMitigations].sort((a, b) => a.rank - b.rank).map((item) => (
          <article className="mitigation-row" key={item.id}>
            <div className="mitigation-rank"><span>#{item.rank}</span><i /></div>
            <div className="mitigation-body"><span>{item.kind.replaceAll("_", " ")}</span><b>{item.action}</b><p>{item.payback_note}</p></div>
            <dl><div><dt>COST</dt><dd>{compact.format(item.cost_usd_low)}–{compact.format(item.cost_usd_high)}</dd></div><div><dt>AVOIDED</dt><dd>{compact.format(item.avoided_loss_usd_low)}–{compact.format(item.avoided_loss_usd_high)}</dd></div></dl>
          </article>
        ))}
      </div>
    </div>
  );
}
