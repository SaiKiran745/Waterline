"use client";

import { useEffect, useRef, useState } from "react";
import type { ScenarioResult } from "@/lib/contracts";

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
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

export function LossCounter({ scenario, scannedPercent }: { scenario: ScenarioResult; scannedPercent: number | null }) {
  const low = useAnimatedNumber(scenario.loss_usd_low);
  const high = useAnimatedNumber(scenario.loss_usd_high);
  return (
    <div className="loss-counter" aria-live="polite">
      <span>ESTIMATED INTERIOR LOSS</span>
      <strong>{dollars(low)} <i>—</i> {dollars(high)}</strong>
      <small>{scenario.assets_hit.length} assets exposed · scanned area: {scannedPercent == null ? "unknown" : `${scannedPercent}% of floor`}</small>
    </div>
  );
}
