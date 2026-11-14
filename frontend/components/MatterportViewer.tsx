"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type MatterportSdk = {
  App: {
    Phase: { PLAYING: unknown };
    state: { waitUntil: (predicate: (state: { phase: unknown }) => boolean) => Promise<unknown> };
  };
  Camera: { TransitionType: { FADEOUT: unknown } };
  Sweep: { moveTo: (locationId: string, options: { transition: unknown }) => Promise<string> };
  disconnect?: () => void;
};

declare global {
  interface Window {
    MP_SDK?: { connect: (iframe: HTMLIFrameElement, applicationKey: string) => Promise<MatterportSdk> };
  }
}

const BOOTSTRAP_URL = "https://static.matterport.com/showcase-sdk/bootstrap/3.1.0-0-g1cd7e0997a/sdk.js";

export function MatterportViewer({ modelId, locationId, enabled }: { modelId: string | null; locationId: string | null; enabled: boolean }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const sdkRef = useRef<MatterportSdk | null>(null);
  const [scriptReady, setScriptReady] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const [status, setStatus] = useState<"idle" | "connecting" | "ready" | "error">("idle");
  const [error, setError] = useState("");
  const sdkKey = process.env.NEXT_PUBLIC_MATTERPORT_SDK_KEY ?? "";

  useEffect(() => {
    if (!enabled || !modelId || !sdkKey || !scriptReady || !iframeReady || !iframeRef.current || !window.MP_SDK) return;
    let cancelled = false;
    const connect = async () => {
      setStatus("connecting");
      setError("");
      try {
        const sdk = await window.MP_SDK!.connect(iframeRef.current!, sdkKey);
        await sdk.App.state.waitUntil((state) => state.phase === sdk.App.Phase.PLAYING);
        if (cancelled) {
          sdk.disconnect?.();
          return;
        }
        sdkRef.current = sdk;
        setStatus("ready");
      } catch (caught) {
        if (!cancelled) {
          setStatus("error");
          setError(caught instanceof Error ? caught.message : String(caught));
        }
      }
    };
    void connect();
    return () => {
      cancelled = true;
      sdkRef.current?.disconnect?.();
      sdkRef.current = null;
    };
  }, [enabled, iframeReady, modelId, scriptReady, sdkKey]);

  useEffect(() => {
    if (status !== "ready" || !locationId || !sdkRef.current) return;
    let cancelled = false;
    sdkRef.current.Sweep.moveTo(locationId, {
      transition: sdkRef.current.Camera.TransitionType.FADEOUT,
    }).catch((caught) => {
      if (!cancelled) {
        setStatus("error");
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    });
    return () => { cancelled = true; };
  }, [locationId, status]);

  if (!enabled) return <ViewerNotice title="Matterport available in API mode" detail="The fixture model id is not a live Matterport Space." />;
  if (!modelId) return <ViewerNotice title="No Matterport scan" detail="This building has no selected Matterport model." />;
  if (!sdkKey) return <ViewerNotice title="Matterport key missing" detail="Set NEXT_PUBLIC_MATTERPORT_SDK_KEY and restart the frontend." tone="error" />;

  const iframeUrl = `https://my.matterport.com/show?m=${encodeURIComponent(modelId)}&play=1&qs=1&applicationKey=${encodeURIComponent(sdkKey)}`;
  const scriptUrl = `${BOOTSTRAP_URL}?applicationKey=${encodeURIComponent(sdkKey)}`;

  return (
    <div className="matterport-viewer">
      <Script src={scriptUrl} strategy="afterInteractive" onReady={() => setScriptReady(true)} onError={() => { setStatus("error"); setError("Matterport SDK bootstrap failed to load."); }} />
      <iframe
        ref={iframeRef}
        src={iframeUrl}
        title="Matterport walkthrough"
        allow="fullscreen; xr-spatial-tracking"
        onLoad={() => setIframeReady(true)}
      />
      <div className={`matterport-state ${status}`}>
        <span>{status === "ready" ? "● SDK CONNECTED" : status === "error" ? "! SDK ERROR" : status === "connecting" ? "◌ CONNECTING" : "◌ LOADING SPACE"}</span>
        {locationId ? <small>SCAN POSITION · {locationId}</small> : <small>SELECT AN ASSET TO NAVIGATE</small>}
      </div>
      {error ? <div className="matterport-error"><b>Matterport could not connect</b><p>{error}</p></div> : null}
    </div>
  );
}

function ViewerNotice({ title, detail, tone = "idle" }: { title: string; detail: string; tone?: "idle" | "error" }) {
  return <div className={`matterport-notice ${tone}`}><span>MATTERPORT WALKTHROUGH</span><strong>{title}</strong><p>{detail}</p></div>;
}
