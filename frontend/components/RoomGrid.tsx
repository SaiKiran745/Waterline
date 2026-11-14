import { PanelState } from "./PanelState";
import { hitMap } from "@/lib/scenario";
import type { Asset, ScenarioResult } from "@/lib/contracts";

export function RoomGrid({ assets, scenario, depthFt }: { assets: Asset[]; scenario: ScenarioResult; depthFt: number }) {
  const rooms = Array.from(new Set(assets.map((asset) => asset.room)));
  const hits = hitMap(scenario);
  if (rooms.length === 0) return <PanelState kind="empty" title="No rooms in survey" detail="The safety view appears when assets have room labels." />;
  return (
    <div className="room-grid">
      {rooms.map((room) => {
        const roomAssets = assets.filter((asset) => asset.room === room);
        const roomHits = roomAssets.filter((asset) => hits.has(asset.id));
        return (
          <article className="room-card" key={room}>
            <div className="room-water" style={{ height: `${Math.min(100, depthFt / 8 * 100)}%` }} />
            <div className="room-card-content">
              <div><span>ROOM</span><strong>{room}</strong></div>
              <p>{roomHits.length} of {roomAssets.length} assets exposed</p>
              <ul>{roomAssets.map((asset) => <li key={asset.id} className={hits.get(asset.id) ?? "clear"}><i />{asset.label}<span>{hits.get(asset.id) ?? "clear"}</span></li>)}</ul>
            </div>
            <span className="room-depth">{depthFt.toFixed(2)} FT</span>
          </article>
        );
      })}
    </div>
  );
}
