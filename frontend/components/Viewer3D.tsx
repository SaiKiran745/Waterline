"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import type { Asset, ScenarioResult } from "@/lib/contracts";
import { hitMap } from "@/lib/scenario";

const WATER = 0x28b8db;

export function Viewer3D({ assets, scenario, depthFt, meshUrl }: { assets: Asset[]; scenario: ScenarioResult; depthFt: number; meshUrl: string | null }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const waterRef = useRef<THREE.Mesh<THREE.PlaneGeometry, THREE.MeshPhysicalMaterial> | null>(null);
  const markerMaterialsRef = useRef(new Map<string, THREE.MeshStandardMaterial>());
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("Preparing model");

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    setStatus("loading");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b1116);
    scene.fog = new THREE.FogExp2(0x0b1116, 0.018);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 600);
    camera.up.set(0, 0, 1);
    camera.position.set(24, -35, 25);
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
    renderer.shadowMap.enabled = true;
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(-8, -4, 1.5);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minDistance = 8;
    controls.maxDistance = 120;

    scene.add(new THREE.HemisphereLight(0xaaddec, 0x172027, 1.8));
    const sun = new THREE.DirectionalLight(0xffffff, 2.3);
    sun.position.set(8, -12, 30);
    sun.castShadow = true;
    scene.add(sun);

    const hit = hitMap(scenario);
    const markerGroup = new THREE.Group();
    const markerMaterials = markerMaterialsRef.current;
    markerMaterials.clear();
    assets.filter((asset) => asset.position).forEach((asset) => {
      const position = asset.position!;
      const state = hit.get(asset.id);
      const material = new THREE.MeshStandardMaterial({ color: state === "likely" ? 0xff5d57 : state === "possible" ? 0xf6ad55 : 0x70d4c8, emissive: state === "likely" ? 0x641715 : 0x0b2827, emissiveIntensity: 0.4 });
      const marker = new THREE.Mesh(new THREE.SphereGeometry(0.48, 20, 20), material);
      marker.position.set(position.x, position.y, Math.max(position.z, 0.4));
      markerGroup.add(marker);
      markerMaterials.set(asset.id, material);
      const stem = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(position.x, position.y, 0), new THREE.Vector3(position.x, position.y, Math.max(position.z, 0.4))]),
        new THREE.LineBasicMaterial({ color: material.color, transparent: true, opacity: 0.45 }),
      );
      markerGroup.add(stem);
    });
    scene.add(markerGroup);

    const waterMaterial = new THREE.MeshPhysicalMaterial({ color: WATER, transparent: true, opacity: 0.32, roughness: 0.18, metalness: 0.05, side: THREE.DoubleSide, depthWrite: false });
    const water = new THREE.Mesh(new THREE.PlaneGeometry(80, 50), waterMaterial);
    water.position.set(-10, -4, depthFt * 0.3048);
    scene.add(water);
    waterRef.current = water;

    const grid = new THREE.GridHelper(90, 30, 0x285461, 0x1a3038);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = 0.005;
    scene.add(grid);

    const addPlaceholder = () => {
      const roomMaterial = new THREE.MeshStandardMaterial({ color: 0x53616a, transparent: true, opacity: 0.45, side: THREE.DoubleSide });
      const floor = new THREE.Mesh(new THREE.BoxGeometry(55, 30, 0.12), new THREE.MeshStandardMaterial({ color: 0x28343b, roughness: 0.9 }));
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
        object.traverse((child) => { if (child instanceof THREE.Mesh) { child.castShadow = true; child.receiveShadow = true; } });
        scene.add(object);
        const bounds = new THREE.Box3().setFromObject(object);
        const center = bounds.getCenter(new THREE.Vector3());
        controls.target.copy(center);
        setMessage("OBJ mesh · metres · z-up");
        setStatus("ready");
      }, undefined, () => { addPlaceholder(); setStatus("error"); setMessage("OBJ failed to load · showing placeholder"); });
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
      markerMaterials.clear();
      renderer.domElement.remove();
    };
    // Scene construction is intentionally independent of slider depth.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assets, meshUrl]);

  useEffect(() => {
    if (waterRef.current) waterRef.current.position.z = depthFt * 0.3048;
    const hits = hitMap(scenario);
    markerMaterialsRef.current.forEach((material, assetId) => {
      const assetStatus = hits.get(assetId);
      material.color.setHex(assetStatus === "likely" ? 0xff5d57 : assetStatus === "possible" ? 0xf6ad55 : 0x70d4c8);
      material.emissive.setHex(assetStatus === "likely" ? 0x641715 : 0x0b2827);
      material.needsUpdate = true;
    });
  }, [depthFt, scenario]);

  return (
    <div className="viewer3d" ref={hostRef}>
      {status === "loading" ? <div className="viewer-status">◌ {message}</div> : null}
      {status === "error" ? <div className="viewer-webgl-fallback"><span>3D VIEW UNAVAILABLE</span><strong>Use Room Safety View</strong><p>The rest of the scenario remains interactive.</p></div> : null}
      <div className={`model-status ${status}`}>{status === "error" ? "!" : "●"} {message}</div>
      <div className="orbit-hint">DRAG TO ORBIT · SCROLL TO ZOOM</div>
    </div>
  );
}
