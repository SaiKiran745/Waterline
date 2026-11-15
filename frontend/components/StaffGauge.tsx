"use client";
import { useMemo } from "react";
import type { Grounding, Range, ScenarioThresholds } from "@/lib/contracts";

const MAX_DEPTH = 8;
type GaugeMark = { id: string; label: string; range: Range; sentence: string; kind: "reference" | "threshold" };

export function StaffGauge({ depth, grounding, thresholds, onChange, onCommit }: { depth: number; grounding: Grounding | null; thresholds: ScenarioThresholds; onChange: (depth: number) => void; onCommit: (depth: number) => void | Promise<void> }) {
  const ticks = useMemo(() => Array.from({ length: 17 }, (_, index) => index / 2), []); const percent = depth / MAX_DEPTH * 100;
  const marks = useMemo<GaugeMark[]>(() => {
    const references = (grounding?.reference_levels ?? []).map((level) => ({ id: level.id, label: level.label.replace("annual-chance ", ""), range: [level.depth_above_floor_ft_low, level.depth_above_floor_ft_high] as Range, sentence: level.sentence, kind: "reference" as const }));
    const gaugeThresholds: GaugeMark[] = [
      { id: "first-loss", label: "First contents reached", range: thresholds.first_loss_ft, sentence: `The first surveyed contents item is reached between ${thresholds.first_loss_ft[0]} and ${thresholds.first_loss_ft[1]} ft.`, kind: "threshold" },
      { id: "half-items", label: "Half of contents", range: thresholds.half_items_ft, sentence: `Half of surveyed contents are reached between ${thresholds.half_items_ft[0]} and ${thresholds.half_items_ft[1]} ft.`, kind: "threshold" },
      { id: "most-items", label: "80% of contents", range: thresholds.most_items_ft, sentence: `80% of surveyed contents are reached between ${thresholds.most_items_ft[0]} and ${thresholds.most_items_ft[1]} ft.`, kind: "threshold" },
      ...thresholds.critical_systems.map((system) => ({ id: `critical-${system.system}`, label: system.name, range: system.first_reached_ft, sentence: `${system.name} is first reached between ${system.first_reached_ft[0]} and ${system.first_reached_ft[1]} ft.`, kind: "threshold" as const })),
    ];
    return [...references, ...gaugeThresholds];
  }, [grounding, thresholds]);
  const above = marks.filter((mark) => Math.max(...mark.range) >= 0); const below = marks.filter((mark) => Math.max(...mark.range) < 0);
  const step = grounding?.steps.find((item) => Math.abs(item.depth_ft - depth) < .01);
  const commit = (value: string) => void onCommit(Number(value));
  return <div className="staff-gauge" aria-label="Water depth control">
    <div className="staff-depth-tag" style={{ bottom: `calc(${percent}% - 24px)` }}><b>{depth.toFixed(2)}</b><span>ft above floor</span>{step ? <small>Outside {step.water_surface_ft.toFixed(1)} ft NAVD 88<br />({step.water_surface_ft_low.toFixed(1)}–{step.water_surface_ft_high.toFixed(1)})</small> : null}</div>
    <div className="staff-column">
      <div className="staff-wet" style={{ height: `${percent}%` }} />
      <div className="staff-ticks" aria-hidden="true">{ticks.map((tick) => <span key={tick} className={Number.isInteger(tick) ? "major" : "minor"} style={{ bottom: `${tick / MAX_DEPTH * 100}%` }}>{Number.isInteger(tick) && tick > 0 && tick < MAX_DEPTH ? <b>{tick}</b> : null}</span>)}</div>
      <div className="staff-marks">{above.map((mark) => { const position = Math.max(0, Math.min(MAX_DEPTH, (mark.range[0] + mark.range[1]) / 2)); return <span key={mark.id} className={`staff-mark ${mark.kind}`} style={{ bottom: `${position / MAX_DEPTH * 100}%` }} title={`${mark.label}: ${mark.sentence}`}><i /><b>{mark.label}</b></span>; })}</div>
      <input aria-label="Interior water depth in feet" type="range" min="0" max={MAX_DEPTH} step="0.25" value={depth} onChange={(event) => onChange(Number(event.target.value))} onPointerUp={(event) => commit(event.currentTarget.value)} onKeyUp={(event) => commit(event.currentTarget.value)} />
    </div>
    <span className="staff-unit">Water above slab</span>
    {below.length ? <div className="staff-below-zero">{below.map((mark) => <span key={mark.id} title={mark.sentence}><b>{mark.label}</b><small>{mark.sentence}</small></span>)}</div> : null}
    {grounding ? <p className="staff-method">{grounding.method}</p> : null}
  </div>;
}
