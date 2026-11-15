import type { Asset, Grounding, ScenarioTable, ScenarioTableRow } from "@/lib/contracts";

const money = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumSignificantDigits: 3 }).format(value);
const width = 520; const height = 180; const pad = 18;

function chartPath(rows: ScenarioTableRow[], field: "total_usd_low" | "total_usd_median" | "total_usd_high", max: number) {
  return rows.map((row, index) => `${index ? "L" : "M"}${pad + row.depth_ft / 8 * (width - pad * 2)},${height - pad - row[field] / max * (height - pad * 2)}`).join(" ");
}

export function NumberBuildPanel({ table, row, assets, grounding, onBack }: { table: ScenarioTable; row: ScenarioTableRow; assets: Asset[]; grounding: Grounding | null; onBack: () => void }) {
  const max = Math.max(1, ...table.rows.map((item) => item.total_usd_high), ...table.standard_method.compare.map((item) => item.standard_median_usd));
  const upper = table.rows.map((item) => `${pad + item.depth_ft / 8 * (width - pad * 2)},${height - pad - item.total_usd_high / max * (height - pad * 2)}`);
  const lower = [...table.rows].reverse().map((item) => `${pad + item.depth_ft / 8 * (width - pad * 2)},${height - pad - item.total_usd_low / max * (height - pad * 2)}`);
  const standard = table.standard_method.compare.map((item, index) => `${index ? "L" : "M"}${pad + item.depth_ft / 8 * (width - pad * 2)},${height - pad - item.standard_median_usd / max * (height - pad * 2)}`).join(" ");
  const assetById = new Map(assets.map((asset) => [asset.id, asset]));
  const thresholdRows = [{ label: "First contents reached", range: table.thresholds.first_loss_ft }, { label: "Half of contents", range: table.thresholds.half_items_ft }, { label: "80% of contents", range: table.thresholds.most_items_ft }, ...table.thresholds.critical_systems.map((item) => ({ label: item.name, range: item.first_reached_ft }))];
  return <div className="number-build-panel">
    <button className="rail-back" onClick={onBack}>← Back to Agent</button>
    <div className="tab-heading"><span className="eyebrow">Transparent estimate</span><h2>How this number is built</h2><p>Median simulated loss with the middle 80% of outcomes.</p></div>
    <section className="number-chart"><header><b>Loss against depth</b><span>Current · {row.depth_ft.toFixed(2)} ft</span></header><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Loss against depth with 80 percent band and standard method line"><path className="chart-band" d={`M${upper.join(" L")} L${lower.join(" L")} Z`} /><path className="chart-median" d={chartPath(table.rows, "total_usd_median", max)} /><path className="chart-standard" d={standard} /><line className="chart-current" x1={pad + row.depth_ft / 8 * (width - pad * 2)} x2={pad + row.depth_ft / 8 * (width - pad * 2)} y1={pad} y2={height - pad} /><text x={pad} y={height - 2}>0 ft</text><text x={width - 42} y={height - 2}>8 ft</text></svg><div className="chart-legend"><span><i className="median" />Waterline median</span><span><i className="band" />80% band</span><span><i className="standard" />Standard method</span></div></section>
    <section className="method-card"><span>At {row.depth_ft.toFixed(2)} ft</span><strong>Waterline contents · about {money(row.loss_usd_median)}</strong><b>Standard method · {row.standard_contents_usd_median == null ? "not available" : `about ${money(row.standard_contents_usd_median)}`}</b><p>{table.standard_method.statement}</p><small>{table.standard_method.citation}</small></section>
    <section className="number-section"><h3>Five biggest contributors</h3>{row.top_contributors.length ? <div className="contributor-list">{row.top_contributors.map((item) => <div key={item.asset_id}><span><b>{assetById.get(item.asset_id)?.label ?? item.asset_id}</b><small>{money(item.expected_loss_usd)} expected</small></span><i><em style={{ width: `${Math.max(2, item.share * 100)}%` }} /></i><strong>{Math.round(item.share * 100)}%</strong></div>)}</div> : <p>No surveyed contents contributors at this depth.</p>}</section>
    <section className="number-section"><h3>Measured thresholds</h3><p>{table.thresholds.heights_from_mesh} of {table.thresholds.contents_items} heights measured from the mesh · {table.thresholds.heights_estimated} estimated.</p><dl className="threshold-list">{thresholdRows.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.range[0].toFixed(2)}–{item.range[1].toFixed(2)} ft</dd></div>)}</dl></section>
    {grounding ? <section className="number-section"><h3>Elevation grounding</h3><p>{grounding.method}</p></section> : null}
    <section className="number-section"><h3>Assumptions</h3><div className="compact-assumptions">{[...table.assumptions, ...(grounding?.assumptions ?? [])].map((item) => <article key={item.id}><span><code>{item.id}</code>{item.placeholder ? <em>assumed range, editable</em> : null}</span><p>{item.text}</p></article>)}</div></section>
  </div>;
}
