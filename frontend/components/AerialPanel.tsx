"use client";

import { useState } from "react";
import Image from "next/image";
import { PanelState } from "./PanelState";
import type { AgentEvent, Building, EntryPoint, MediaManifest } from "@/lib/contracts";
import { buildingLabel } from "@/lib/presentation";

const fixtureMarkerPositions = [
  { left: "62%", top: "67%" },
  { left: "74%", top: "49%" },
  { left: "28%", top: "36%" },
];

function entryMatchesImage(entry: EntryPoint, imageKind: string) {
  if (imageKind === "ortho") return entry.image_kind === "ortho";
  return entry.image_kind === `oblique-${imageKind}` || entry.image_kind === imageKind;
}

function aerialLabel(kind: string) {
  if (kind === "ortho") return "Overhead";
  const label = kind.replace(/^oblique-/, "").replaceAll("-", " ");
  return `${label[0]?.toUpperCase() ?? ""}${label.slice(1)}`;
}

export function AerialPanel({ building, entryPoints, media, events, dataSource }: { building: Building; entryPoints: EntryPoint[]; media: MediaManifest | null; events: AgentEvent[]; dataSource: string }) {
  const aerials = Object.entries(media?.aerial ?? {}).sort(([a], [b]) => Number(b === "ortho") - Number(a === "ortho"));
  const firstEvidenceImage = entryPoints[0] ? aerials.find(([kind]) => entryMatchesImage(entryPoints[0], kind))?.[0] : undefined;
  const [selectedKind, setSelectedKind] = useState(firstEvidenceImage ?? aerials[0]?.[0] ?? "");
  const [activeId, setActiveId] = useState(entryPoints[0]?.id ?? "");
  const [imageState, setImageState] = useState<"loading" | "ready" | "error">("loading");
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const selectedImage = aerials.find(([kind]) => kind === selectedKind)?.[1] ?? null;
  const active = entryPoints.find((entry) => entry.id === activeId);
  const visibleMarkers = entryPoints.filter((entry) => entryMatchesImage(entry, selectedKind));
  const layerDiscrepancy = media?.notes?.find((note) => /layer discrepancy/i.test(note))
    ?? events.find((event) => /layer discrepancy/i.test(event.text))?.text
    ?? entryPoints.find((entry) => /layer discrepancy/i.test(entry.evidence))?.evidence
    ?? null;

  const chooseImage = (kind: string) => {
    setSelectedKind(kind);
    setImageState("loading");
    setImageSize(null);
    const firstMarker = entryPoints.find((entry) => entryMatchesImage(entry, kind));
    if (firstMarker) setActiveId(firstMarker.id);
  };

  return (
    <aside className="aerial-panel panel-frame">
      <div className="panel-title">
        <div><span className="eyebrow">Site scout</span><h2>Aerial evidence</h2></div>
        <span className="confidence-chip">{entryPoints.length} found</span>
      </div>

      {aerials.length > 0 ? (
        <>
          <div className="aerial-angle-tabs" role="tablist" aria-label="Aerial image angle">
            {aerials.map(([kind]) => <button key={kind} className={kind === selectedKind ? "active" : ""} onClick={() => chooseImage(kind)} aria-label={`${aerialLabel(kind)} aerial angle`}>{aerialLabel(kind)}</button>)}
          </div>
          {layerDiscrepancy ? <aside className="layer-discrepancy"><b>Layer discrepancy</b><span>{layerDiscrepancy}</span></aside> : null}
          <div className="aerial-visual real-aerial">
            {selectedImage ? (
              <div className="aerial-image-canvas" style={imageSize ? { aspectRatio: `${imageSize.width} / ${imageSize.height}` } : undefined}>
                {/* Manifest URLs are localhost-only cached sponsor media served by the backend. */}
                <Image
                  src={selectedImage.url}
                  alt={`${selectedKind} aerial view of ${buildingLabel(building)}`}
                  fill
                  unoptimized
                  loading="eager"
                  sizes="(max-width: 760px) 100vw, 24vw"
                  onLoad={(event) => {
                    setImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight });
                    setImageState("ready");
                  }}
                  onError={() => setImageState("error")}
                />
                {imageState === "ready" ? visibleMarkers.filter((entry) => entry.image_xy).map((entry) => {
                  const index = entryPoints.indexOf(entry);
                  const [x, y] = entry.image_xy!;
                  return (
                    <button
                      key={entry.id}
                      className={`entry-marker ${activeId === entry.id ? "active" : ""}`}
                      style={{ left: `${x / imageSize!.width * 100}%`, top: `${y / imageSize!.height * 100}%` }}
                      onMouseEnter={() => setActiveId(entry.id)} onFocus={() => setActiveId(entry.id)} onClick={() => setActiveId(entry.id)}
                      aria-label={`${entry.kind} entry point`}
                    >{index + 1}<span className="entry-tooltip">{entry.evidence}</span></button>
                  );
                }) : null}
              </div>
            ) : null}
            {imageState === "loading" ? <div className="aerial-load-state">◌ Loading cached {selectedKind} image</div> : null}
            {imageState === "error" ? <div className="aerial-load-state error">! {selectedKind} image unavailable</div> : null}
            <div className="north">N ↑</div>
          </div>
        </>
      ) : dataSource === "api" ? (
        <PanelState kind="empty" title="Aerial imagery pending" detail="The media manifest has no overhead or angled images for this building." />
      ) : (
        <FixtureAerial entryPoints={entryPoints} activeId={activeId} onActivate={setActiveId} />
      )}

      {entryPoints.length === 0 ? (
        <PanelState kind="empty" title="Site survey pending" detail="Imagery is ready; entry-point evidence will appear after the site scout runs." />
      ) : active ? (
        <>
          <div className="entry-evidence">
            <div><span className="entry-index">{String(entryPoints.indexOf(active) + 1).padStart(2, "0")}</span><span><b>{active.kind.replace("_", " ")}</b><small>{active.image_kind} · {Math.round(active.confidence * 100)}% confidence</small></span></div>
            <p>{active.evidence}</p>
            <dl><div><dt>Threshold</dt><dd>{active.threshold_elevation_ft == null ? "Not measured" : `${active.threshold_elevation_ft} ft`}</dd></div><div><dt>Ground</dt><dd>{building.ground_elevation_ft?.toFixed(1) ?? "—"} ft</dd></div></dl>
          </div>
          <div className="entry-list">
            {entryPoints.map((entry, index) => <button className={entry.id === activeId ? "active" : ""} key={entry.id} onClick={() => { setActiveId(entry.id); const match = aerials.find(([kind]) => entryMatchesImage(entry, kind)); if (match) chooseImage(match[0]); }}><span>{index + 1}</span>{entry.kind.replace("_", " ")}<i>{Math.round(entry.confidence * 100)}%</i></button>)}
          </div>
        </>
      ) : null}
      <div className="panel-source">Vexcel · {selectedImage?.collection ?? building.aerial_collection ?? "collection unknown"} · {selectedImage?.capture_date ?? building.aerial_capture_date ?? "date unknown"}</div>
    </aside>
  );
}

function FixtureAerial({ entryPoints, activeId, onActivate }: { entryPoints: EntryPoint[]; activeId: string; onActivate: (id: string) => void }) {
  return (
    <div className="aerial-visual">
      <div className="aerial-grid" />
      <div className="building-footprint"><i /><i /><i /><span>Fixture aerial<br />image unavailable</span></div>
      <div className="north">N ↑</div>
      {entryPoints.map((entry, index) => <button key={entry.id} className={`entry-marker ${activeId === entry.id ? "active" : ""}`} style={fixtureMarkerPositions[index % fixtureMarkerPositions.length]} onMouseEnter={() => onActivate(entry.id)} onFocus={() => onActivate(entry.id)} onClick={() => onActivate(entry.id)} aria-label={`${entry.kind} entry point`}>{index + 1}<span className="entry-tooltip">{entry.evidence}</span></button>)}
    </div>
  );
}
