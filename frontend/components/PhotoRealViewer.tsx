"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type * as Three from "three";
import { damageColour } from "@/lib/scenario";
import type { Asset, AssetDamage, MatterportLocation } from "@/lib/contracts";

type Vector3 = { x: number; y: number; z: number };
type SweepData = {
  id: string;
  sid: string;
  uuid: string;
  position: Vector3;
  puckPosition: Vector3;
  floorInfo: { id?: string; sequence?: number };
};
type SceneComponent = {
  outputs: { objectRoot?: Three.Object3D | null; collider?: Three.Object3D | null };
  events: Record<string, boolean>;
  emits: Record<string, boolean>;
  onInit(this: SceneComponent): void;
  onEvent(): void;
  onInputsUpdated(): void;
  onTick(): void;
  onDestroy(this: SceneComponent): void;
};
type SceneRuntimeComponent = { outputs: { objectRoot?: Three.Object3D | null } };
type SceneNode = { addComponent(name: string, inputs?: Record<string, unknown>): SceneRuntimeComponent; start(): void };
type SceneObject = { addNode(name?: string): SceneNode; start(): void; stop(): void };
type Disposable = { dispose(): void };
type BundleSdk = {
  App: { Phase: { PLAYING: unknown }; state: { waitUntil(predicate: (state: { phase: unknown }) => boolean): Promise<unknown> } };
  Camera: { TransitionType: { FADEOUT: unknown; FLY: unknown } };
  Sweep: {
    data: { subscribe(observer: { onCollectionUpdated(collection: Record<string, SweepData>): void }): { cancel?: () => void } };
    current: { subscribe(callback: (sweep: SweepData) => void): { cancel?: () => void } };
    moveTo(id: string, options: { transition: unknown }): Promise<string>;
  };
  Mode: {
    Mode: { INSIDE: unknown; DOLLHOUSE: unknown };
    moveTo(mode: unknown, options?: { transition?: unknown }): Promise<unknown>;
  };
  Scene: {
    THREE: typeof import("three");
    register(name: string, factory: () => SceneComponent): Promise<Disposable | null>;
    createObjects(count: number): Promise<SceneObject[]>;
  };
  disconnect(): void;
};
type BundleWindow = Window & { MP_SDK?: { connect(target: Window): Promise<BundleSdk> } };
type ViewMode = "inside" | "dollhouse";

const FEET_TO_METRES = 0.3048;

function withTimeout<T>(promise: Promise<T>, milliseconds: number, message: string) {
  return Promise.race<T>([
    promise,
    new Promise<T>((_, reject) => window.setTimeout(() => reject(new Error(message)), milliseconds)),
  ]);
}

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function meshToViewer(point: Vector3): Vector3 {
  return { x: point.x, y: point.z, z: -point.y };
}

function coordinateRms(locations: MatterportLocation[], sweeps: SweepData[]) {
  const byId = new Map<string, SweepData>();
  sweeps.forEach((sweep) => [sweep.id, sweep.sid, sweep.uuid].filter(Boolean).forEach((id) => byId.set(id, sweep)));
  const errors = locations.flatMap((location) => {
    const sweep = byId.get(location.id);
    if (!sweep?.puckPosition) return [];
    const expected = meshToViewer(location.position);
    return [(expected.x - sweep.puckPosition.x) ** 2 + (expected.y - sweep.puckPosition.y) ** 2 + (expected.z - sweep.puckPosition.z) ** 2];
  });
  return { matches: errors.length, rms: errors.length ? Math.sqrt(errors.reduce((sum, value) => sum + value, 0) / errors.length) : null };
}

export function PhotoRealViewer({ modelId, assets, damageByAsset, depthFt, locationId, locations, insideRequest, onFailure }: {
  modelId: string | null;
  assets: Asset[];
  damageByAsset: Map<string, AssetDamage>;
  depthFt: number;
  locationId: string | null;
  locations: MatterportLocation[];
  insideRequest: number;
  onFailure: (message: string) => void;
}) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const sdkRef = useRef<BundleSdk | null>(null);
  const sceneObjectRef = useRef<SceneObject | null>(null);
  const registrationRef = useRef<Disposable | null>(null);
  const waterRef = useRef<Three.Mesh | null>(null);
  const markerMaterialsRef = useRef(new Map<string, Three.MeshBasicMaterial>());
  const automaticFloorRef = useRef(0);
  const loadStartedAtRef = useRef(0);
  const [iframeReady, setIframeReady] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [loadingStage, setLoadingStage] = useState("Starting Matterport viewer");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [mode, setMode] = useState<ViewMode>("dollhouse");
  const [floorLevel, setFloorLevel] = useState(0);
  const [floorDraft, setFloorDraft] = useState("0.000");
  const [calibrating, setCalibrating] = useState(false);
  const [floorSource, setFloorSource] = useState("Matterport floor pucks");
  const [currentPuckLevel, setCurrentPuckLevel] = useState<number | null>(null);
  const [coordinateCheck, setCoordinateCheck] = useState("Checking shared scan positions");
  const [activeLocationId, setActiveLocationId] = useState<string | null>(null);
  const sdkKey = process.env.NEXT_PUBLIC_MATTERPORT_SDK_KEY ?? "";
  const bundleUrl = useMemo(() => modelId && sdkKey ? `/matterport-bundle/showcase.html?m=${encodeURIComponent(modelId)}&play=1&qs=1&applicationKey=${encodeURIComponent(sdkKey)}` : "", [modelId, sdkKey]);

  useEffect(() => {
    if (iframeReady || !modelId || !sdkKey) return;
    loadStartedAtRef.current = performance.now();
    const timer = window.setTimeout(() => {
      const message = "Matterport Bundle iframe did not load after 30 seconds.";
      setStatus("error");
      setError(message);
      onFailure(message);
    }, 30_000);
    return () => window.clearTimeout(timer);
  }, [iframeReady, modelId, onFailure, sdkKey]);

  useEffect(() => {
    if (!iframeReady || !iframeRef.current || !modelId || !sdkKey) return;
    let cancelled = false;
    let sweepSubscription: { cancel?: () => void } | null = null;
    let currentSubscription: { cancel?: () => void } | null = null;
    const markerMaterials = markerMaterialsRef.current;
    const connect = async () => {
      loadStartedAtRef.current = performance.now();
      setStatus("loading");
      setError("");
      setElapsedSeconds(0);
      setLoadingStage("Connecting to Matterport SDK");
      try {
        const bundleWindow = iframeRef.current!.contentWindow as BundleWindow | null;
        if (!bundleWindow?.MP_SDK) throw new Error("Matterport Bundle files are missing. Run npm run bundle:download.");
        const sdk = await withTimeout(bundleWindow.MP_SDK.connect(bundleWindow), 30_000, "Matterport Bundle SDK connection timed out after 30 seconds.");
        setLoadingStage("Loading photo-real model");
        await withTimeout(sdk.App.state.waitUntil((app) => app.phase === sdk.App.Phase.PLAYING), 60_000, "Matterport viewer did not reach the playing state after 60 seconds.");
        if (cancelled) { sdk.disconnect(); return; }
        sdkRef.current = sdk;
        currentSubscription = sdk.Sweep.current.subscribe((sweep) => { if (sweep?.id) setCurrentPuckLevel(sweep.puckPosition.y); });
        setLoadingStage("Reading scan positions");
        const sweeps = await withTimeout(new Promise<SweepData[]>((resolve) => {
          sweepSubscription = sdk.Sweep.data.subscribe({ onCollectionUpdated: (collection) => resolve(Object.values(collection)) });
        }), 30_000, "Matterport scan positions did not arrive after 30 seconds.");
        if (cancelled) return;

        const floorSequences = sweeps.map((sweep) => sweep.floorInfo?.sequence).filter((value): value is number => typeof value === "number");
        if (floorSequences.length === 0) throw new Error("Matterport returned no aligned floor sweeps.");
        const groundSequence = Math.min(...floorSequences);
        const floorPucks = sweeps.filter((sweep) => sweep.floorInfo?.sequence === groundSequence).map((sweep) => sweep.puckPosition?.y).filter((value): value is number => Number.isFinite(value));
        if (floorPucks.length === 0) throw new Error("Matterport returned no floor-puck elevations.");
        const automaticFloor = median(floorPucks);
        automaticFloorRef.current = automaticFloor;
        const saved = window.localStorage.getItem(`waterline-floor-${modelId}`);
        const initialFloor = saved == null ? automaticFloor : Number(saved);
        setFloorLevel(initialFloor);
        setFloorDraft(initialFloor.toFixed(3));
        setFloorSource(saved == null ? `Matterport pucks · floor ${groundSequence + 1}` : "Saved manual calibration");

        const check = coordinateRms(locations, sweeps);
        setCoordinateCheck(check.rms == null ? "No shared scan points" : `${check.matches} shared points · RMS ${check.rms.toFixed(3)} m`);
        if (check.rms != null && check.rms > 0.2) throw new Error(`Mesh/viewer coordinate check failed (${check.rms.toFixed(3)} m RMS).`);

        setLoadingStage("Aligning water and asset markers");
        const THREE = sdk.Scene.THREE;
        markerMaterials.clear();
        let water: Three.Mesh | null = null;
        const componentName = `waterline.photoReal.${Date.now()}`;
        registrationRef.current = await sdk.Scene.register(componentName, () => ({
          outputs: {},
          events: {},
          emits: {},
          onInit() {
            const root = new THREE.Group();
            const xValues = sweeps.map((sweep) => sweep.puckPosition.x);
            const zValues = sweeps.map((sweep) => sweep.puckPosition.z);
            const width = Math.max(12, Math.max(...xValues) - Math.min(...xValues) + 8);
            const length = Math.max(12, Math.max(...zValues) - Math.min(...zValues) + 8);
            water = new THREE.Mesh(
              new THREE.PlaneGeometry(width, length),
              new THREE.MeshBasicMaterial({ color: 0x2ab9dd, transparent: true, opacity: 0.42, side: THREE.DoubleSide, depthWrite: false }),
            );
            water.rotation.x = -Math.PI / 2;
            water.position.set((Math.max(...xValues) + Math.min(...xValues)) / 2, initialFloor + depthFt * FEET_TO_METRES, (Math.max(...zValues) + Math.min(...zValues)) / 2);
            water.visible = depthFt > 0.001;
            water.renderOrder = 2;
            root.add(water);
            assets.filter((asset) => asset.position).forEach((asset) => {
              const damage = damageByAsset.get(asset.id);
              const material = new THREE.MeshBasicMaterial({ color: damageColour(damage?.fractionHigh ?? 0), depthTest: true });
              const geometry = damage?.movable ? new THREE.OctahedronGeometry(0.5, 0) : new THREE.SphereGeometry(0.38, 16, 12);
              const marker = new THREE.Mesh(geometry, material);
              const point = meshToViewer(asset.position!);
              marker.position.set(point.x, point.y, point.z);
              marker.renderOrder = 3;
              root.add(marker);
              markerMaterials.set(asset.id, material);
            });
            waterRef.current = water;
            this.outputs.objectRoot = root;
          },
          onEvent() {},
          onInputsUpdated() {},
          onTick() {},
          onDestroy() {
            this.outputs.objectRoot = null;
            this.outputs.collider = null;
          },
        }));
        const [sceneObject] = await sdk.Scene.createObjects(1);
        const node = sceneObject.addNode("waterline-photo-real-overlay");
        const component = node.addComponent(componentName);
        node.start();
        const objectRoot = await withTimeout(new Promise<Three.Object3D>((resolve) => {
          const inspect = () => component.outputs.objectRoot ? resolve(component.outputs.objectRoot) : window.requestAnimationFrame(inspect);
          inspect();
        }), 5_000, "Matterport Scene overlay did not initialize.");
        sceneObjectRef.current = sceneObject;
        setCoordinateCheck((label) => `${label} · ${objectRoot.children.length - 1} markers`);
        setLoadingStage("Opening dollhouse view");
        await sdk.Mode.moveTo(sdk.Mode.Mode.DOLLHOUSE, { transition: sdk.Camera.TransitionType.FLY });
        setMode("dollhouse");
        setStatus("ready");
      } catch (caught) {
        if (cancelled) return;
        const message = caught instanceof Error ? caught.message : String(caught);
        setStatus("error");
        setError(message);
        window.setTimeout(() => onFailure(message), 1200);
      }
    };
    void connect();
    return () => {
      cancelled = true;
      sweepSubscription?.cancel?.();
      currentSubscription?.cancel?.();
      sceneObjectRef.current?.stop();
      registrationRef.current?.dispose();
      sdkRef.current?.disconnect();
      sceneObjectRef.current = null;
      registrationRef.current = null;
      sdkRef.current = null;
      waterRef.current = null;
      markerMaterials.clear();
    };
    // The overlay is rebuilt when the model or corrected asset inventory changes, not at each slider step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assets, iframeReady, locations, modelId, sdkKey]);

  useEffect(() => {
    if (status !== "loading") return;
    const timer = window.setInterval(() => setElapsedSeconds(Math.max(0, Math.floor((performance.now() - loadStartedAtRef.current) / 1000))), 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  useEffect(() => {
    if (waterRef.current) {
      waterRef.current.position.y = floorLevel + depthFt * FEET_TO_METRES;
      waterRef.current.visible = depthFt > 0.001;
    }
  }, [depthFt, floorLevel]);

  useEffect(() => {
    markerMaterialsRef.current.forEach((material, assetId) => material.color.set(damageColour(damageByAsset.get(assetId)?.fractionHigh ?? 0)));
  }, [damageByAsset]);

  useEffect(() => {
    if (insideRequest === 0 || status !== "ready" || !locationId || !sdkRef.current) return;
    sdkRef.current.Sweep.moveTo(locationId, { transition: sdkRef.current.Camera.TransitionType.FADEOUT }).then(() => { setMode("inside"); setActiveLocationId(locationId); }).catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, [insideRequest, locationId, status]);

  const switchMode = async (next: ViewMode) => {
    const sdk = sdkRef.current;
    if (!sdk) return;
    try {
      if (next === "inside" && locationId) { await sdk.Sweep.moveTo(locationId, { transition: sdk.Camera.TransitionType.FADEOUT }); setActiveLocationId(locationId); }
      else await sdk.Mode.moveTo(next === "inside" ? sdk.Mode.Mode.INSIDE : sdk.Mode.Mode.DOLLHOUSE, { transition: sdk.Camera.TransitionType.FLY });
      setMode(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const applyFloor = () => {
    const value = Number(floorDraft);
    if (!Number.isFinite(value)) return;
    setFloorLevel(value);
    setFloorSource("Saved manual calibration");
    if (modelId) window.localStorage.setItem(`waterline-floor-${modelId}`, String(value));
    setCalibrating(false);
  };

  const resetFloor = () => {
    const value = automaticFloorRef.current;
    setFloorLevel(value);
    setFloorDraft(value.toFixed(3));
    setFloorSource("Matterport floor pucks");
    if (modelId) window.localStorage.removeItem(`waterline-floor-${modelId}`);
    setCalibrating(false);
  };

  if (!modelId || !sdkKey) return <div className="photo-real-unavailable"><b>Photo-real view unavailable</b><span>{!modelId ? "No Matterport model is attached." : "NEXT_PUBLIC_MATTERPORT_SDK_KEY is missing."}</span></div>;

  return (
    <div className="photo-real-viewer">
      <iframe ref={iframeRef} src={bundleUrl} title="Photo-real Matterport water view" allow="fullscreen; xr-spatial-tracking" onLoad={() => { setLoadingStage("Connecting to Matterport SDK"); setIframeReady(true); }} />
      <div className="photo-real-toolbar">
        <div className="photo-mode-toggle"><button className={mode === "inside" ? "active" : ""} onClick={() => void switchMode("inside")}>INSIDE</button><button className={mode === "dollhouse" ? "active" : ""} onClick={() => void switchMode("dollhouse")}>DOLLHOUSE</button></div>
        <span>{status === "ready" ? `● PHOTO-REAL · ${coordinateCheck}${mode === "inside" && activeLocationId ? ` · SCAN ${activeLocationId}` : ""}` : status === "error" ? "! BUNDLE FAILED" : `◌ ${loadingStage.toUpperCase()} · ${elapsedSeconds}s`}</span>
      </div>
      {status === "loading" ? <div className="photo-real-loading" role="status"><i /><b>{loadingStage}</b><span>{elapsedSeconds}s elapsed · large spaces can take longer on first load</span></div> : null}
      <div className="photo-floor-control">
        <span>FLOOR {floorLevel.toFixed(3)} M · {floorSource}</span>
        <button onClick={() => setCalibrating((value) => !value)}>SET FLOOR LEVEL</button>
        {calibrating ? <div><input aria-label="Photo-real floor level in metres" type="number" step="0.01" value={floorDraft} onChange={(event) => setFloorDraft(event.target.value)} /><button onClick={applyFloor}>APPLY</button><button onClick={resetFloor}>AUTO</button>{currentPuckLevel != null ? <button onClick={() => setFloorDraft(currentPuckLevel.toFixed(3))}>CURRENT PUCK</button> : null}</div> : null}
      </div>
      <div className="photo-depth-readout"><span>WATER ABOVE SLAB</span><b>{depthFt.toFixed(2)} FT</b></div>
      {error ? <div className="photo-real-error"><b>Photo-real view issue</b><span>{error}</span><small>Returning to the offline 3D model.</small></div> : null}
    </div>
  );
}
