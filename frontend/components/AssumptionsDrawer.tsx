import type { Assumption } from "@/lib/contracts";

export function AssumptionsDrawer({ open, onClose, assumptions }: { open: boolean; onClose: () => void; assumptions: Assumption[] }) {
  return (
    <div className={`drawer-wrap ${open ? "open" : ""}`} aria-hidden={!open}>
      <button className="drawer-backdrop" aria-label="Close assumptions" onClick={onClose} />
      <aside className="assumptions-drawer" role="dialog" aria-modal="true" aria-label="Scenario assumptions">
        <div className="drawer-header"><div><span className="eyebrow">SCENARIO DISCLOSURE</span><h2>Assumptions</h2></div><button onClick={onClose} aria-label="Close">×</button></div>
        <p className="drawer-intro">Every value used in the current result is listed here. Water depth is user-selected and is not a prediction.</p>
        {assumptions.length === 0 ? <div className="panel-state empty"><strong>No assumptions supplied</strong><span>The data source did not include assumption records.</span></div> : (
          <div className="assumption-list">{assumptions.map((assumption) => <article key={assumption.id}><div><code>{assumption.id}</code>{assumption.placeholder ? <span>PLACEHOLDER</span> : null}</div><p>{assumption.text}</p><small>SOURCE · {assumption.source}</small></article>)}</div>
        )}
      </aside>
    </div>
  );
}
