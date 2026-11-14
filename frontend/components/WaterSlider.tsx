export function WaterSlider({ depth, onChange }: { depth: number; onChange: (depth: number) => void }) {
  const percentage = (depth / 8) * 100;
  return (
    <div className="water-slider">
      <div className="slider-label"><span>WATER DEPTH</span><strong>{depth.toFixed(2)} ft</strong></div>
      <div className="slider-track-wrap">
        <input
          aria-label="Interior water depth above ground-floor slab"
          type="range" min="0" max="8" step="0.25" value={depth}
          style={{ "--slider-fill": `${percentage}%` } as React.CSSProperties}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        <div className="slider-scale"><span>0</span><span>2</span><span>4</span><span>6</span><span>8 FT</span></div>
      </div>
    </div>
  );
}
