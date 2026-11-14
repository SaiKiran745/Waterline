"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Building } from "@/lib/contracts";

export function BuildingMap({ buildings, selectedId, onSelect }: { buildings: Building[]; selectedId: string; onSelect: (id: string) => void }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!hostRef.current || mapRef.current) return;
    const map = L.map(hostRef.current, { zoomControl: false, attributionControl: false, minZoom: 9, maxZoom: 18 });
    L.control.zoom({ position: "bottomright" }).addTo(map);
    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer || buildings.length === 0) return;
    layer.clearLayers();
    const bounds = L.latLngBounds([]);
    buildings.forEach((building, index) => {
      const active = building.id === selectedId;
      const icon = L.divIcon({
        className: "waterline-map-icon",
        html: `<span class="map-pin ${active ? "active" : ""}"><b>${index + 1}</b><i></i></span>`,
        iconSize: [48, 56], iconAnchor: [24, 48],
      });
      const marker = L.marker([building.lat, building.lng], { icon, title: building.name ?? building.address });
      marker.on("click", () => onSelect(building.id));
      marker.addTo(layer);
      bounds.extend([building.lat, building.lng]);
    });
    if (buildings.length === 1) map.setView(bounds.getCenter(), 13);
    else map.fitBounds(bounds.pad(0.25));
  }, [buildings, selectedId, onSelect]);

  return <div ref={hostRef} className="leaflet-host" aria-label="Map of assessed Houston buildings" />;
}
