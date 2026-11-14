import { PanelState } from "./PanelState";
import { damageColour } from "@/lib/scenario";
import type { CSSProperties } from "react";
import type { Asset, AssetDamage } from "@/lib/contracts";

export function RoomGrid({ assets, damageByAsset, depthFt }: { assets: Asset[]; damageByAsset: Map<string, AssetDamage>; depthFt: number }) {
  const rooms = Array.from(new Set(assets.map((asset) => asset.room)));
  if (rooms.length === 0) return <PanelState kind="empty" title="No rooms in survey" detail="The safety view appears when assets have room labels." />;
  return (
    <div className="room-grid">
      {rooms.map((room) => {
        const roomAssets = assets.filter((asset) => asset.room === room);
        const roomHits = roomAssets.filter((asset) => damageByAsset.get(asset.id)?.status !== "clear");
        return (
          <article className="room-card" key={room}>
            <div className="room-water" style={{ height: `${Math.min(100, depthFt / 8 * 100)}%` }} />
            <div className="room-card-content">
              <div><span>ROOM</span><strong>{room}</strong></div>
              <p>{roomHits.length} of {roomAssets.length} assets exposed</p>
              <ul>{roomAssets.map((asset) => {
                const damage = damageByAsset.get(asset.id);
                const style = { "--damage-color": damageColour(damage?.fractionHigh ?? 0) } as CSSProperties;
                return <li key={asset.id} style={style} className={`${damage?.status ?? "clear"} ${damage?.movable ? "movable" : ""}`}><i>{damage?.movable ? "◆" : ""}</i>{asset.label}<span>{damage?.movable ? "move" : `${Math.round((damage?.fractionHigh ?? 0) * 100)}%`}</span></li>;
              })}</ul>
            </div>
            <span className="room-depth">{depthFt.toFixed(2)} FT</span>
          </article>
        );
      })}
    </div>
  );
}
