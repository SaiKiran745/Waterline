"use client";

import { useEffect, useState } from "react";
import { getDossier } from "@/lib/data";
import { PanelState } from "./PanelState";
import type { Dossier } from "@/lib/contracts";

function fileName(path: string) {
  return path.split("/").pop() ?? path;
}

function inlineMarkdown(value: string) {
  return value.split(/(\*\*[^*]+\*\*)/g).map((part, index) => part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part);
}

function MarkdownContent({ content }: { content: string }) {
  if (!content.trim()) return <p>This file is empty.</p>;
  return <div className="rendered-markdown">{content.split("\n").map((line, index) => {
    if (line.startsWith("### ")) return <h4 key={index}>{inlineMarkdown(line.slice(4))}</h4>;
    if (line.startsWith("## ")) return <h3 key={index}>{inlineMarkdown(line.slice(3))}</h3>;
    if (line.startsWith("# ")) return <h2 key={index}>{inlineMarkdown(line.slice(2))}</h2>;
    if (/^[-*] /.test(line)) return <p className="markdown-list-item" key={index}>{inlineMarkdown(line.slice(2))}</p>;
    if (/^\d+\. /.test(line)) return <p className="markdown-list-item numbered" key={index}>{inlineMarkdown(line.replace(/^\d+\. /, ""))}</p>;
    return line.trim() ? <p key={index}>{inlineMarkdown(line)}</p> : <br key={index} />;
  })}</div>;
}

export function FilesPanel({ buildingId, live, refreshVersion, dataSource }: { buildingId: string; live: boolean; refreshVersion: number; dataSource: string }) {
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (dataSource !== "api") return;
    let cancelled = false;
    const load = async () => {
      try {
        const next = await getDossier(buildingId);
        if (cancelled) return;
        setDossier(next);
        setSelected((current) => current || next.files[0]?.path || "");
        setError("");
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      }
    };
    void load();
    const timer = live ? window.setInterval(load, 1250) : undefined;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [buildingId, dataSource, live, refreshVersion]);

  if (dataSource !== "api") return <PanelState kind="empty" title="No live dossier" detail="Files appear when the backend agent writes them." />;
  if (error && !dossier) return <PanelState kind="error" title="Dossier unavailable" detail={error} />;
  if (!dossier) return <PanelState kind="loading" title="Loading dossier files" detail="Reading the agent workspace." />;
  if (dossier.files.length === 0) return <PanelState kind="empty" title="No files written yet" detail="Run the agent to create survey notes, scenarios, mitigations, and documents." />;
  const file = dossier.files.find((item) => item.path === selected) ?? dossier.files[0];
  return (
    <div className="files-tab">
      <div className="tab-heading"><h2>Files</h2><p>{dossier.files.length} files {live ? "· updating live" : "· last written state"}</p></div>
      {error ? <p className="panel-inline-error">{error}</p> : null}
      <div className="dossier-files">
        <nav aria-label="Dossier files">
          {dossier.files.map((item) => <button key={item.path} className={item.path === file.path ? "active" : ""} onClick={() => setSelected(item.path)}><b>{fileName(item.path)}</b><span>{item.bytes.toLocaleString()} B</span><small>{new Date(item.modified).toLocaleTimeString()}</small></button>)}
        </nav>
        <article><header><b>{fileName(file.path)}</b><span>{file.path}</span></header><MarkdownContent content={file.content} /></article>
      </div>
    </div>
  );
}
