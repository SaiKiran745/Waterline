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

export function LossCounter({ row, scannedPercent }: { row: ScenarioTableRow; scannedPercent: number | null }) {
  const totalLow = useAnimatedNumber(row.total_usd_low);
  const totalHigh = useAnimatedNumber(row.total_usd_high);
  const contentsLow = useAnimatedNumber(row.loss_usd_low);
  const contentsHigh = useAnimatedNumber(row.loss_usd_high);
  const structureLow = useAnimatedNumber(row.structure_loss_usd_low);
  const structureHigh = useAnimatedNumber(row.structure_loss_usd_high);
  return (
    <div className="loss-counter" aria-live="polite">
      <span>Estimated total loss</span>
      <strong>{dollars(totalLow)} <i>–</i> {dollars(totalHigh)}</strong>
      <div className="loss-split">
        <span><em>Contents</em><b>{dollars(contentsLow)} – {dollars(contentsHigh)}</b></span>
        <span><em>Structure</em><b>{dollars(structureLow)} – {dollars(structureHigh)}</b></span>
      </div>
      <small>scanned area only ({scannedPercent == null ? "coverage unknown" : `${scannedPercent}% of floor`}) · assumed value ranges</small>
    </div>
  );
}
