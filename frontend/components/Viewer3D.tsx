"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import type { Asset, AssetDamage } from "@/lib/contracts";
import { damageColour } from "@/lib/scenario";

const WATER = 0x28b8db;

export function Viewer3D({ assets, damageByAsset, depthFt, meshUrl, selectedAssetId }: { assets: Asset[]; damageByAsset: Map<string, AssetDamage>; depthFt: number; meshUrl: string | null; selectedAssetId: string | null }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const waterRef = useRef<THREE.Mesh<THREE.BoxGeometry, THREE.MeshPhysicalMaterial> | null>(null);
  const waterEdgeRef = useRef<THREE.LineLoop | null>(null);
  const markerMaterialsRef = useRef(new Map<string, THREE.MeshBasicMaterial>());
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("Preparing model");

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    setStatus("loading");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x17262d);
    scene.fog = new THREE.FogExp2(0x17262d, 0.006);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 600);
    camera.up.set(0, 0, 1);
    camera.position.set(28, -36, 30);
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      const failureTimer = window.setTimeout(() => {
        setStatus("error");
        setMessage("WebGL unavailable · switch to Room Safety View");
      }, 0);
      return () => window.clearTimeout(failureTimer);
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    renderer.localClippingEnabled = true;
    renderer.shadowMap.enabled = true;
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(-8, -4, 1.5);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minDistance = 8;
    controls.maxDistance = 120;

    scene.add(new THREE.HemisphereLight(0xe6f7fa, 0x35505b, 2.15));
    scene.add(new THREE.AmbientLight(0xd7eef2, 0.75));
    const sun = new THREE.DirectionalLight(0xffffff, 3.2);
    sun.position.set(8, -12, 30);
    sun.castShadow = true;
    scene.add(sun);

    const markerGroup = new THREE.Group();
    const markerMaterials = markerMaterialsRef.current;
    markerMaterials.clear();
    assets.filter((asset) => asset.position).forEach((asset) => {
      const position = asset.position!;
      const damage = damageByAsset.get(asset.id);
      const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(damageColour(damage?.fractionHigh ?? 0)), side: THREE.DoubleSide, transparent: true, opacity: 0.96 });
      const geometry = new THREE.RingGeometry(damage?.movable ? 0.3 : 0.34, damage?.movable ? 0.54 : 0.52, damage?.movable ? 4 : 32);
      const marker = new THREE.Mesh(geometry, material);
      marker.position.set(position.x, position.y, Math.max(position.z, 0.4));
      marker.scale.setScalar(asset.id === selectedAssetId ? 1.45 : 1);
      markerGroup.add(marker);
      markerMaterials.set(asset.id, material);
    });
    scene.add(markerGroup);

    const waterMaterial = new THREE.MeshPhysicalMaterial({ color: WATER, transparent: true, opacity: 0.28, roughness: 0.08, metalness: 0.02, transmission: 0.18, side: THREE.DoubleSide, depthWrite: false });
    const initialWaterHeight = Math.max(depthFt * 0.3048, 0.001);
    const water = new THREE.Mesh(new THREE.BoxGeometry(80, 50, 1), waterMaterial);
    water.scale.z = initialWaterHeight;
    water.position.set(-10, -4, initialWaterHeight / 2);
    water.renderOrder = 4;
    scene.add(water);
    waterRef.current = water;
    const makeWaterEdge = (width: number, height: number) => new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-width / 2, -height / 2, 0), new THREE.Vector3(width / 2, -height / 2, 0),
      new THREE.Vector3(width / 2, height / 2, 0), new THREE.Vector3(-width / 2, height / 2, 0),
    ]);
    const waterEdge = new THREE.LineLoop(makeWaterEdge(80, 50), new THREE.LineBasicMaterial({ color: 0x75eaff, transparent: true, opacity: 0.96 }));
    waterEdge.position.copy(water.position);
    waterEdge.renderOrder = 5;
    scene.add(waterEdge);
    waterEdgeRef.current = waterEdge;

    const grid = new THREE.GridHelper(90, 30, 0x285461, 0x1a3038);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = 0.005;
    scene.add(grid);

    const addPlaceholder = () => {
      const roomMaterial = new THREE.MeshStandardMaterial({ color: 0xb5c5ca, transparent: true, opacity: 0.76, roughness: 0.9, side: THREE.DoubleSide });
      const floor = new THREE.Mesh(new THREE.BoxGeometry(55, 30, 0.12), new THREE.MeshStandardMaterial({ color: 0x366373, roughness: 0.88 }));
      floor.position.set(-10, -4, -0.08);
      floor.receiveShadow = true;
      scene.add(floor);
      const walls = [
        { size: [55, 0.25, 6], pos: [-10, 11, 3] },
        { size: [0.25, 30, 6], pos: [-37.5, -4, 3] },
        { size: [0.25, 30, 6], pos: [17.5, -4, 3] },
        { size: [16, 0.22, 4], pos: [-19, -6, 2] },
        { size: [0.22, 17, 4], pos: [-11, 2.5, 2] },
      ];
      walls.forEach(({ size, pos }) => {
        const wall = new THREE.Mesh(new THREE.BoxGeometry(size[0], size[1], size[2]), roomMaterial);
        wall.position.set(pos[0], pos[1], pos[2]);
        scene.add(wall);
      });
      setMessage("Placeholder room · OBJ URL not present in contract");
      setStatus("ready");
    };

    if (meshUrl) {
      new OBJLoader().load(meshUrl, (object) => {
        const ceilingCut = new THREE.Plane(new THREE.Vector3(0, 0, -1), 1e6);
        const architecturalMaterial = new THREE.MeshStandardMaterial({ color: 0xbac9ce, roughness: 0.86, metalness: 0.02, side: THREE.DoubleSide, clippingPlanes: [ceilingCut] });
        const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x415d67, transparent: true, opacity: 0.8, clippingPlanes: [ceilingCut] });
        const meshChildren: THREE.Mesh[] = [];
        object.traverse((child) => { if (child instanceof THREE.Mesh) meshChildren.push(child); });
        meshChildren.forEach((child) => {
          const oldMaterials = Array.isArray(child.material) ? child.material : [child.material];
          oldMaterials.forEach((material) => material.dispose());
          child.material = architecturalMaterial;
          child.castShadow = true;
          child.receiveShadow = true;
          const edges = new THREE.LineSegments(new THREE.EdgesGeometry(child.geometry, 28), edgeMaterial);
          edges.renderOrder = 2;
          child.add(edges);
        });
        scene.add(object);
        const bounds = new THREE.Box3().setFromObject(object);
        const center = bounds.getCenter(new THREE.Vector3());
        const size = bounds.getSize(new THREE.Vector3());
        const span = Math.max(size.x, size.y, size.z, 8);
        ceilingCut.constant = bounds.min.z + size.z * 0.72;
        controls.target.set(center.x, center.y, bounds.min.z + size.z * 0.34);
        camera.position.set(center.x + span * 0.78, center.y - span * 1.02, Math.max(span * 0.76, size.z * 1.7));
        camera.near = Math.max(0.05, span / 1000);
        camera.far = Math.max(600, span * 12);
        camera.updateProjectionMatrix();
        controls.minDistance = Math.max(2, span * 0.08);
        controls.maxDistance = span * 4;
        water.geometry.dispose();
        const waterWidth = Math.max(size.x * 1.08, 10);
        const waterHeight = Math.max(size.y * 1.08, 10);
        water.geometry = new THREE.BoxGeometry(waterWidth, waterHeight, 1);
        water.position.x = center.x;
        water.position.y = center.y;
        waterEdge.geometry.dispose();
        waterEdge.geometry = makeWaterEdge(waterWidth, waterHeight);
        waterEdge.position.x = center.x;
        waterEdge.position.y = center.y;
        const floor = new THREE.Mesh(
          new THREE.PlaneGeometry(Math.max(size.x * 1.12, 10), Math.max(size.y * 1.12, 10)),
          new THREE.MeshStandardMaterial({ color: 0x315d6b, roughness: 0.92, metalness: 0.01, side: THREE.DoubleSide }),
        );
        floor.position.set(center.x, center.y, -0.035);
        floor.receiveShadow = true;
        scene.add(floor);
        setMessage("Architectural model ready");
        setStatus("ready");
      }, (progress) => {
        if (progress.total > 0) setMessage(`Loading mesh · ${Math.round(progress.loaded / progress.total * 100)}%`);
      }, () => { addPlaceholder(); setStatus("error"); setMessage("OBJ failed to load · showing placeholder"); });
    } else addPlaceholder();

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    let frame = 0;
    const animate = () => { controls.update(); renderer.render(scene, camera); frame = requestAnimationFrame(animate); };
    animate();
    return () => {
      observer.disconnect(); cancelAnimationFrame(frame); controls.dispose(); renderer.dispose();
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) { object.geometry.dispose(); const materials = Array.isArray(object.material) ? object.material : [object.material]; materials.forEach((material) => material.dispose()); }
      });
      waterRef.current = null;
      waterEdgeRef.current = null;
      markerMaterials.clear();
      renderer.domElement.remove();
    };
    // Scene construction is intentionally independent of slider depth.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assets, meshUrl, selectedAssetId]);

  useEffect(() => {
    if (waterRef.current) {
      const height = Math.max(depthFt * 0.3048, 0.001);
      waterRef.current.scale.z = height;
      waterRef.current.position.z = height / 2;
      waterRef.current.visible = depthFt > 0.001;
    }
    if (waterEdgeRef.current) waterEdgeRef.current.position.z = depthFt * 0.3048;
    markerMaterialsRef.current.forEach((material, assetId) => {
      const damage = damageByAsset.get(assetId);
      material.color.set(damageColour(damage?.fractionHigh ?? 0));
      material.needsUpdate = true;
    });
  }, [damageByAsset, depthFt]);

  return (
    <div className="viewer3d" ref={hostRef}>
      {status === "loading" ? <div className="viewer-status">{message}</div> : null}
      {status === "error" ? <div className="viewer-webgl-fallback"><span>3D VIEW UNAVAILABLE</span><strong>Use Room Safety View</strong><p>The rest of the scenario remains interactive.</p></div> : null}
      {status !== "ready" ? <div className={`model-status ${status}`}>{message}</div> : null}
    </div>
  );
}
