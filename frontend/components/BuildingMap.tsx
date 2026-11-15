"use client";
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { TriageElevationRow, TriageRow } from "@/lib/contracts";
import type { DashboardRow } from "./TriageDashboard";
import { buildingLabel } from "@/lib/presentation";

function isElevation(row: TriageRow | TriageElevationRow): row is TriageElevationRow { return "elevation" in row; }

export function BuildingMap({ rows, mode, depth, selectedId, onSelect }: { rows: DashboardRow[]; mode: "fema" | "depth"; depth: 1 | 2 | 4 | 6; selectedId: string; onSelect: (id: string) => void }) {
  const hostRef = useRef<HTMLDivElement>(null); const mapRef = useRef<L.Map | null>(null); const layerRef = useRef<L.LayerGroup | null>(null);
  const [basemapState, setBasemapState] = useState<"loading" | "online" | "offline">("loading");
  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;
    const map = L.map(hostRef.current, { zoomControl: false, attributionControl: true, minZoom: 9, maxZoom: 18 }); L.control.zoom({ position: "bottomright" }).addTo(map); map.attributionControl.setPrefix(false);
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, className: "dark-map-tiles", attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }); let errors = 0;
    tiles.on("load", () => { errors = 0; setBasemapState("online"); tiles.setOpacity(1); }); tiles.on("tileerror", () => { errors += 1; if (errors >= 3) { setBasemapState("offline"); tiles.setOpacity(0); } }); tiles.addTo(map); mapRef.current = map; layerRef.current = L.layerGroup().addTo(map);
    return () => { map.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => {
    const map = mapRef.current; const layer = layerRef.current; if (!map || !layer || rows.length === 0) return; layer.clearLayers();
    const bounds = L.latLngBounds(rows.map(({ building }) => [building.lat, building.lng] as [number, number])); if (rows.length === 1) map.setView(bounds.getCenter(), 13, { animate: false }); else map.fitBounds(bounds.pad(.18), { padding: [52, 52], animate: false });
    const key = String(depth) as "1" | "2" | "4" | "6"; const losses = rows.map(({ triage }) => isElevation(triage) ? (triage.loss?.total_median ?? 0) : triage.loss_by_depth_ft[key].total_median); const min = Math.min(...losses); const max = Math.max(...losses); const placed: Array<{ point: L.Point; size: number }> = [];
    rows.forEach((row, index) => {
      const active = row.building.id === selectedId; const inside = row.building.in_mapped_flood_zone === true; const loss = isElevation(row.triage) ? (row.triage.loss?.total_median ?? 0) : row.triage.loss_by_depth_ft[key].total_median; const scale = max === min ? .5 : (Math.log1p(loss) - Math.log1p(min)) / (Math.log1p(max) - Math.log1p(min)); const size = Math.round(34 + scale * 28);
      const origin = L.latLng(row.building.lat, row.building.lng); const originPoint = map.latLngToLayerPoint(origin); let plottedPoint = originPoint.clone(); let attempt = 0;
      while (placed.some((item) => plottedPoint.distanceTo(item.point) < (size + item.size) / 2 + 12) && attempt < 30) { attempt += 1; const angle = (attempt * 137.508 + index * 29) * Math.PI / 180; const radius = 28 + Math.ceil(attempt / 6) * 24; plottedPoint = originPoint.add(L.point(Math.cos(angle) * radius, Math.sin(angle) * radius)); }
      placed.push({ point: plottedPoint, size }); const plotted = map.layerPointToLatLng(plottedPoint); const weak = isElevation(row.triage) && row.triage.fema_at_building === false;
      const icon = L.divIcon({ className: "waterline-map-icon", html: `<span class="map-pin ${inside ? "inside" : "outside"} ${active ? "active" : ""} ${weak ? "weak" : ""}" style="--pin-size:${size}px"><b>${row.triage.rank}</b><i></i></span>`, iconSize: [size + 10, size + 16], iconAnchor: [(size + 10) / 2, size + 8] });
      if (!origin.equals(plotted)) L.polyline([origin, plotted], { color: inside ? "#3cc6ea" : "#f6c61a", weight: 1, opacity: .55, dashArray: "3 4", interactive: false }).addTo(layer);
      L.marker(plotted, { icon, title: `${buildingLabel(row.building)} · ${mode === "fema" ? "same storm" : "same depth"}`, riseOnHover: true }).on("click", () => onSelect(row.building.id)).addTo(layer);
    });
  }, [depth, mode, onSelect, rows, selectedId]);
  return <><div ref={hostRef} className={`leaflet-host basemap-${basemapState}`} aria-label="Map of assessed Houston buildings" /><span className={`basemap-state ${basemapState}`}>{basemapState === "online" ? "Street map" : basemapState === "offline" ? "Offline grid" : "Loading map"}</span></>;
}
