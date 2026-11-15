"use client";
import { useMemo } from "react";
import type { Grounding, Range, ScenarioThresholds } from "@/lib/contracts";

const MAX_DEPTH = 8;
type GaugeMark = { id: string; label: string; range: Range; sentence: string; kind: "reference" | "threshold"; central?: number };

export function StaffGauge({ depth, grounding, thresholds, onChange, onCommit }: { depth: number; grounding: Grounding | null; thresholds: ScenarioThresholds; onChange: (depth: number) => void; onCommit: (depth: number) => void | Promise<void> }) {
  const ticks = useMemo(() => Array.from({ length: 17 }, (_, index) => index / 2), []); const percent = depth / MAX_DEPTH * 100;
  const marks = useMemo<GaugeMark[]>(() => {
    const references = (grounding?.reference_levels ?? []).map((level) => ({ id: level.id, label: level.label.replace("annual-chance ", ""), range: [level.depth_above_floor_ft_low, level.depth_above_floor_ft_high] as Range, sentence: level.sentence, kind: "reference" as const, central: level.depth_above_floor_ft }));
    // A threshold is null when the building has no surveyed items of that kind (A, B, C, G and H have no IT equipment): no mark.
    const threshold = (id: string, label: string, range: Range | null, sentence: (range: Range) => string): GaugeMark[] => range ? [{ id, label, range, sentence: sentence(range), kind: "threshold" }] : [];
    const gaugeThresholds: GaugeMark[] = [
      ...threshold("first-loss", "First contents reached", thresholds.first_loss_ft, (range) => `The first surveyed contents item is reached between ${range[0]} and ${range[1]} ft.`),
      ...threshold("half-items", "Half of contents", thresholds.half_items_ft, (range) => `Half of surveyed contents are reached between ${range[0]} and ${range[1]} ft.`),
      ...threshold("most-items", "80% of contents", thresholds.most_items_ft, (range) => `80% of surveyed contents are reached between ${range[0]} and ${range[1]} ft.`),
      ...thresholds.critical_systems.flatMap((system) => threshold(`critical-${system.system}`, system.name, system.first_reached_ft, (range) => `${system.name} is first reached between ${range[0]} and ${range[1]} ft.`)),
    ];
    return [...references, ...gaugeThresholds];
  }, [grounding, thresholds]);
  // A level whose central estimate is below the floor (E's FEMA level: 1.3 ft below, range -3.6 to +1.0) is listed under
  // the gauge with its sentence, not drawn at the zero line where the thresholds crowd.
  const isBelow = (mark: GaugeMark) => (mark.central ?? Math.max(...mark.range)) < 0;
  const above = marks.filter((mark) => !isBelow(mark)); const below = marks.filter(isBelow);
  const step = grounding?.steps.find((item) => Math.abs(item.depth_ft - depth) < .01);
  const commit = (value: string) => void onCommit(Number(value));
  const reserve = below.length ? below.length * 24 + 34 : 0;   // room under the gauge for marks below the floor, clear of the depth tag at 0 ft
  return <div className="staff-gauge" aria-label="Water depth control">
    <div className="staff-body" style={{ bottom: reserve }}>
    <div className="staff-depth-tag" style={{ bottom: `calc(${percent}% - 24px)` }}><b>{depth.toFixed(2)}</b><span>ft above floor</span>{step ? <small>Outside {step.water_surface_ft.toFixed(1)} ft NAVD 88<br />({step.water_surface_ft_low.toFixed(1)}–{step.water_surface_ft_high.toFixed(1)})</small> : null}</div>
    <div className="staff-column">
      <div className="staff-wet" style={{ height: `${percent}%` }} />
      <div className="staff-ticks" aria-hidden="true">{ticks.map((tick) => <span key={tick} className={Number.isInteger(tick) ? "major" : "minor"} style={{ bottom: `${tick / MAX_DEPTH * 100}%` }}>{Number.isInteger(tick) && tick > 0 && tick < MAX_DEPTH ? <b>{tick}</b> : null}</span>)}</div>
      <div className="staff-marks">{above.map((mark) => { const position = Math.max(0, Math.min(MAX_DEPTH, (mark.range[0] + mark.range[1]) / 2)); return <span key={mark.id} className={`staff-mark ${mark.kind}`} style={{ bottom: `${position / MAX_DEPTH * 100}%` }} title={`${mark.label}: ${mark.sentence}`}><i /><b>{mark.label}</b></span>; })}</div>
      <input aria-label="Interior water depth in feet" type="range" min="0" max={MAX_DEPTH} step="0.25" value={depth} onChange={(event) => onChange(Number(event.target.value))} onPointerUp={(event) => commit(event.currentTarget.value)} onKeyUp={(event) => commit(event.currentTarget.value)} />
    </div>
    <span className="staff-unit">Water above slab</span>
    </div>
    {below.length ? <div className="staff-below-zero">{below.map((mark) => <span key={mark.id} title={mark.sentence}><b>{mark.label}</b><small>{mark.sentence}</small></span>)}</div> : null}
  </div>;
}
