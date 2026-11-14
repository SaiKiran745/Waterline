export function PanelState({ kind, title, detail }: { kind: "loading" | "empty" | "error"; title: string; detail?: string }) {
  return (
    <div className={`panel-state ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <span className="state-symbol">{kind === "loading" ? "◌" : kind === "error" ? "!" : "—"}</span>
      <strong>{title}</strong>
      {detail ? <span>{detail}</span> : null}
    </div>
  );
}

export function AppSkeleton({ label }: { label: string }) {
  return (
    <main className="app-skeleton">
      <div className="skeleton-brand">WATERLINE</div>
      <div className="skeleton-line wide" />
      <div className="skeleton-grid"><i /><i /><i /></div>
      <p>{label}…</p>
    </main>
  );
}
