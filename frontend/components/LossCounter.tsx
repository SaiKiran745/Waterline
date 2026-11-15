"use client";

import { useEffect, useRef, useState } from "react";
import type { ScenarioTableRow } from "@/lib/contracts";

function useAnimatedNumber(target: number) {
  const [value, setValue] = useState(target);
  const previous = useRef(target);
  useEffect(() => {
    const startValue = previous.current;
    const started = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / 420);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(startValue + (target - startValue) * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
      else previous.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return value;
}

function dollars(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumSignificantDigits: 3 }).format(value);
}

export function LossCounter({ row, onExplain }: { row: ScenarioTableRow; onExplain: () => void }) {
  const totalMedian = useAnimatedNumber(row.total_usd_median);
  const contentsMedian = useAnimatedNumber(row.loss_usd_median);
  const structureMedian = useAnimatedNumber(row.structure_loss_usd_median);
  return (
    <div className="loss-counter" aria-live="polite">
      <span>Estimated loss at {row.depth_ft.toFixed(2)} ft</span>
      <strong>About {dollars(totalMedian)}</strong>
      <p>80% range {dollars(row.total_usd_low)} to {dollars(row.total_usd_high)}</p>
      <div className="loss-split">
        <span><em>Contents</em><b>About {dollars(contentsMedian)}</b><small>80% range {dollars(row.loss_usd_low)} to {dollars(row.loss_usd_high)}</small></span>
        <span><em>Structure</em><b>About {dollars(structureMedian)}</b><small>80% range {dollars(row.structure_loss_usd_low)} to {dollars(row.structure_loss_usd_high)}</small></span>
      </div>
      <small className="measured-line">Water reaches {row.items_in_water.count_low} to {row.items_in_water.count_high} of {row.items_in_water.of} items at {row.depth_ft.toFixed(row.depth_ft % 1 ? 2 : 0)} ft, measured from the 3D scan.</small>
      <small className="scenario-note">A scenario tied to elevation, not a forecast.</small>
      <small className="loss-caveat">Scanned area only. Values are assumed ranges.</small>
      <button className="number-explain" onClick={onExplain}>How this number is built</button>
    </div>
  );
}
