"use client";

import { useState } from "react";
import { approveAndSend } from "@/lib/data";
import type { Building, Mitigation } from "@/lib/contracts";

export function ApprovePanel({ building, mitigations, dataSource }: { building: Building; mitigations: Mitigation[]; dataSource: string }) {
  const [reviewed, setReviewed] = useState(false);
  const [recipient, setRecipient] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");
  const send = async () => {
    setState("sending");
    try {
      const result = await approveAndSend(building.id, recipient);
      setMessage(result.message); setState("sent");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Send failed."); setState("error");
    }
  };
  const playbookActions = mitigations
    .filter((item) => item.depth_ft === 2)
    .sort((a, b) => a.rank - b.rank);
  return (
    <div className="approve-tab">
      <div className="tab-heading"><span className="eyebrow">04 / HUMAN CHECKPOINT</span><h2>Review & approve</h2><p>Nothing leaves Waterline without this step.</p></div>
      <div className="artifact-card">
        <div className="artifact-icon">▤</div><div><span>RESILIENCE BRIEF</span><b>{building.name ?? building.address}</b><small>Derived from current building, survey, and mitigation records</small></div><button aria-label="Preview report">PREVIEW</button>
      </div>
      <div className="playbook-preview">
        <span>PRE-STORM PLAYBOOK</span><h3>First 24 hours</h3>
        {playbookActions.length === 0 ? <p>No mitigation actions are available yet.</p> : <ol>{playbookActions.map((item) => <li key={item.id}><i>{item.rank}</i><span>{item.action}<small>{item.payback_note}</small></span></li>)}</ol>}
      </div>
      {dataSource === "api" ? <label className="recipient-field"><span>ALLOWED RECIPIENT</span><input type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="ops@example.com" /></label> : null}
      <label className="approval-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span><i />I reviewed the current playbook and explicitly approve this send.</span></label>
      <button className="approve-button" disabled={!reviewed || (dataSource === "api" && !recipient) || state === "sending" || state === "sent"} onClick={send}>
        {state === "sending" ? "SENDING…" : state === "sent" ? "APPROVED ✓" : "APPROVE & SEND"}
      </button>
      <p className={`send-message ${state}`}>{message || "Fixture mode never contacts an external recipient. API mode enforces the backend allowlist."}</p>
    </div>
  );
}
