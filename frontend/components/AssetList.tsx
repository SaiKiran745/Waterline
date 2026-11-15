"use client";

import { PanelState } from "./PanelState";
import { damageColour } from "@/lib/scenario";
import { useState, type CSSProperties } from "react";
import type { Asset, AssetDamage, ScenarioResult } from "@/lib/contracts";

function money(low: number, high: number) {
  const format = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 0 });
  return `${format.format(low)}–${format.format(high)}`;
}

function measuredFromMesh(asset: Asset) {
  return [asset.evidence, ...asset.observations.map((item) => item.evidence)].some((text) => text.toLowerCase().includes("measured from mesh"));
}

export function AssetList({ assets, scenario, damageByAsset, selectedAssetId, memoryAppliedAssetIds, onSelectAsset, onCorrect, correctionState, correctionsEnabled }: { assets: Asset[]; scenario: ScenarioResult; damageByAsset: Map<string, AssetDamage>; selectedAssetId: string | null; memoryAppliedAssetIds: Set<string>; onSelectAsset: (assetId: string) => void; onCorrect: (assetId: string, method: "PATCH" | "DELETE", changes: Record<string, unknown>) => Promise<void>; correctionState: { kind: "idle" | "saving" | "success" | "error"; message: string }; correctionsEnabled: boolean }) {
  if (assets.length === 0) return <PanelState kind="empty" title="Survey pending" detail="The building is live, but its interior asset survey has not landed yet." />;
  const movableAssets = assets.filter((asset) => damageByAsset.get(asset.id)?.movable);
  const contentsAssets = assets.filter((asset) => !damageByAsset.get(asset.id)?.movable);
  const sorted = [...contentsAssets].sort((a, b) => {
    const aRisk = a.value_usd_high * (damageByAsset.get(a.id)?.fractionHigh ?? 0);
    const bRisk = b.value_usd_high * (damageByAsset.get(b.id)?.fractionHigh ?? 0);
    return bRisk - aRisk || b.value_usd_high - a.value_usd_high;
  });
  const likely = contentsAssets.filter((asset) => damageByAsset.get(asset.id)?.status === "likely").length;
  const possible = contentsAssets.filter((asset) => damageByAsset.get(asset.id)?.status === "possible").length;
  return (
    <div className="asset-tab">
      <div className="tab-heading"><span className="eyebrow">Interior survey</span><h2>Asset inventory</h2><p>Exposure at {scenario.depth_ft.toFixed(2)} ft</p></div>
      <div className="asset-summary">
        <span><b>{likely}</b> Likely</span>
        <span><b>{possible}</b> Possible</span>
        <span><b>{contentsAssets.length - likely - possible}</b> Clear</span>
      </div>
      <div className="asset-list">
        {sorted.map((asset) => <div className="asset-row-wrap" key={asset.id}><AssetRow asset={asset} damage={damageByAsset.get(asset.id)} selected={asset.id === selectedAssetId} memoryApplied={memoryAppliedAssetIds.has(asset.id)} onSelect={onSelectAsset} />{asset.id === selectedAssetId && correctionsEnabled ? <CorrectionPanel asset={asset} state={correctionState} onCorrect={onCorrect} /> : null}</div>)}
        {movableAssets.length > 0 ? <details className="movable-assets"><summary><span className="vehicle-marker">◇</span><span><b>Movable assets at risk</b><small>{movableAssets.length} vehicles · excluded from loss totals</small></span></summary>{movableAssets.map((asset) => <div className="asset-row-wrap" key={asset.id}><AssetRow asset={asset} damage={damageByAsset.get(asset.id)} selected={asset.id === selectedAssetId} memoryApplied={memoryAppliedAssetIds.has(asset.id)} movable onSelect={onSelectAsset} />{asset.id === selectedAssetId && correctionsEnabled ? <CorrectionPanel asset={asset} state={correctionState} onCorrect={onCorrect} /> : null}</div>)}</details> : null}
      </div>
    </div>
  );
}

function CorrectionPanel({ asset, state, onCorrect }: { asset: Asset; state: { kind: "idle" | "saving" | "success" | "error"; message: string }; onCorrect: (assetId: string, method: "PATCH" | "DELETE", changes: Record<string, unknown>) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [label, setLabel] = useState(asset.label);
  const [heightLow, setHeightLow] = useState(String(asset.height_ft_low));
  const [heightHigh, setHeightHigh] = useState(String(asset.height_ft_high));
  const [valueBasis, setValueBasis] = useState(asset.value_basis);
  const [note, setNote] = useState("");
  const saving = state.kind === "saving";
  const save = () => onCorrect(asset.id, "PATCH", { label, height_ft_low: Number(heightLow), height_ft_high: Number(heightHigh), value_basis: valueBasis, note });
  const remove = () => {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    void onCorrect(asset.id, "DELETE", { note });
  };
  return (
    <div className="correction-panel">
      <button className="correction-toggle" onClick={() => setOpen((value) => !value)}><span>Human correction</span><b>{open ? "Close" : "Edit selected asset"}</b></button>
      {open ? <div className="correction-form">
        <label><span>Label</span><input value={label} onChange={(event) => setLabel(event.target.value)} /></label>
        <div className="correction-pair"><label><span>Height low · ft</span><input type="number" min="0" max="30" step="0.01" value={heightLow} onChange={(event) => setHeightLow(event.target.value)} /></label><label><span>Height high · ft</span><input type="number" min="0" max="30" step="0.01" value={heightHigh} onChange={(event) => setHeightHigh(event.target.value)} /></label></div>
        <label><span>Value class</span><input value={valueBasis} onChange={(event) => setValueBasis(event.target.value)} /></label>
        <label><span>Review note</span><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="What changed and why" /></label>
        <div className="correction-actions"><button disabled={saving} onClick={() => void save()}>Save and recalculate</button><button className={confirmDelete ? "confirm" : "delete"} disabled={saving} onClick={remove}>{confirmDelete ? "Confirm remove" : "Remove false asset"}</button></div>
      </div> : null}
      {state.message ? <p className={`correction-message ${state.kind}`}>{state.message}</p> : null}
    </div>
  );
}

function AssetRow({ asset, damage, selected, memoryApplied, movable = false, onSelect }: { asset: Asset; damage?: AssetDamage; selected: boolean; memoryApplied: boolean; movable?: boolean; onSelect: (assetId: string) => void }) {
  const status = damage?.status ?? "clear";
  const fraction = damage?.fractionHigh ?? 0;
  const observations = asset.observations;
  const before = observations[0];
  const after = observations[observations.length - 1];
  const style = { "--damage-color": damageColour(fraction) } as CSSProperties;
  return (
    <button style={style} className={`asset-row ${status} ${movable ? "movable" : ""} ${selected ? "selected" : ""} ${asset.source !== "vision" || memoryApplied ? "memory-applied" : ""}`} onClick={() => onSelect(asset.id)}>
      <div className="asset-status">{movable ? <i className="vehicle-shape">◆</i> : <i />}<span>{movable ? "Move" : `${Math.round(fraction * 100)}%`}</span></div>
      <div className="asset-main">
        <span className="asset-room">{asset.room} · {asset.category}</span>
        <b>{asset.label}</b>
        <small>{asset.height_ft_low}–{asset.height_ft_high} ft vulnerable height · {Math.round(asset.confidence * 100)}% confidence</small>
        <span className="asset-damage-bar" aria-label={`${Math.round(fraction * 100)}% damage`}><i style={{ width: `${Math.round(fraction * 100)}%` }} /></span>
        {measuredFromMesh(asset) ? <span className="mesh-measured-badge">Measured from mesh</span> : null}
        {asset.source !== "vision" || memoryApplied ? <span className="memory-applied-badge">Agent memory · correction {memoryApplied || asset.source === "human-propagated" ? "applied" : "recorded"}</span> : null}
        {selected && observations.length > 1 ? (
          <span className="relook-comparison">
            <span><em>Re-look before</em>{before.height_ft_low}–{before.height_ft_high} ft · {Math.round(before.confidence * 100)}%</span>
            <span><em>After</em>{after.height_ft_low}–{after.height_ft_high} ft · {Math.round(after.confidence * 100)}%</span>
          </span>
        ) : null}
      </div>
      <span className="asset-value">{movable ? "Excluded" : money(asset.value_usd_low, asset.value_usd_high)}</span>
    </button>
  );
}
