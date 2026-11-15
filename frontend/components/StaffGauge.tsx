"use client";

import { useMemo } from "react";

const MAX_DEPTH = 8;

export function StaffGauge({ depth, onChange, onCommit }: {
  depth: number;
  onChange: (depth: number) => void;
  onCommit: (depth: number) => void | Promise<void>;
}) {
  const ticks = useMemo(() => Array.from({ length: 17 }, (_, index) => index / 2), []);
  const percent = depth / MAX_DEPTH * 100;
  const commit = (value: string) => void onCommit(Number(value));

  return (
    <div className="staff-gauge" aria-label="Water depth control">
      <div className="staff-depth-tag" style={{ bottom: `calc(${percent}% - 18px)` }}><b>{depth.toFixed(2)}</b><span>ft</span></div>
      <div className="staff-column">
        <div className="staff-wet" style={{ height: `${percent}%` }} />
        <div className="staff-ticks" aria-hidden="true">
          {ticks.map((tick) => <span key={tick} className={Number.isInteger(tick) ? "major" : "minor"} style={{ bottom: `${tick / MAX_DEPTH * 100}%` }}>{Number.isInteger(tick) && tick > 0 && tick < MAX_DEPTH ? <b>{tick}</b> : null}</span>)}
        </div>
        <input aria-label="Interior water depth in feet" type="range" min="0" max={MAX_DEPTH} step="0.25" value={depth} onChange={(event) => onChange(Number(event.target.value))} onPointerUp={(event) => commit(event.currentTarget.value)} onKeyUp={(event) => commit(event.currentTarget.value)} />
      </div>
      <span className="staff-unit">Water above slab</span>
    </div>
  );
}
