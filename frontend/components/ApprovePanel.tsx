"use client";

import { useState } from "react";
import { approveAndSend, getArtifactUrl } from "@/lib/data";
import type { Building, Mitigation } from "@/lib/contracts";

export function ApprovePanel({ building, mitigations, currentDepth, dataSource }: { building: Building; mitigations: Mitigation[]; currentDepth: number; dataSource: string }) {
  const [reviewed, setReviewed] = useState(false);
  const [recipient, setRecipient] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");
  const [artifact, setArtifact] = useState<"report" | "playbook">("playbook");
  const [artifactState, setArtifactState] = useState<"loading" | "ready" | "error">("loading");
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
    .filter((item) => item.depth_ft === currentDepth)
    .sort((a, b) => a.rank - b.rank);
  const artifactsReady = dataSource === "api";
  const artifactUrl = getArtifactUrl(building.id, artifact, currentDepth);
  return (
    <div className="approve-tab">
      <div className="tab-heading"><span className="eyebrow">04 / HUMAN CHECKPOINT</span><h2>Review & approve</h2><p>Nothing leaves Waterline without this step.</p></div>
      <div className="artifact-card">
        <div className="artifact-icon">▤</div><div><span>LIVE BACKEND ARTIFACTS</span><b>{building.name ?? building.address}</b><small>{artifactsReady ? `Rendered for the current ${currentDepth.toFixed(2)} ft scenario` : "Backend connection required"}</small></div>{artifactsReady ? <span className="artifact-links"><a href={getArtifactUrl(building.id, "report", currentDepth)} target="_blank" rel="noreferrer">REPORT ↗</a><a href={getArtifactUrl(building.id, "playbook", currentDepth)} target="_blank" rel="noreferrer">PLAYBOOK ↗</a></span> : <span className="pending-chip">PENDING</span>}
      </div>
      {artifactsReady ? <div className="artifact-preview"><div><button className={artifact === "report" ? "active" : ""} onClick={() => { setArtifact("report"); setArtifactState("loading"); }}>REPORT</button><button className={artifact === "playbook" ? "active" : ""} onClick={() => { setArtifact("playbook"); setArtifactState("loading"); }}>PLAYBOOK</button><span>{artifactState.toUpperCase()}</span></div><iframe key={artifactUrl} src={artifactUrl} title={`${artifact} preview`} onLoad={() => setArtifactState("ready")} onError={() => setArtifactState("error")} /></div> : null}
      <div className="playbook-preview">
        <span>PRE-STORM PLAYBOOK</span><h3>First 24 hours</h3>
        {playbookActions.length === 0 ? <p>No mitigation actions are available yet.</p> : <ol>{playbookActions.map((item) => <li key={item.id}><i>{item.rank}</i><span>{item.action}<small>{item.payback_note}</small></span></li>)}</ol>}
      </div>
      {dataSource === "api" ? <label className="recipient-field"><span>ALLOWED RECIPIENT</span><input type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="ops@example.com" /></label> : null}
      <label className="approval-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span><i />I reviewed the current playbook and explicitly approve this send.</span></label>
      <button className="approve-button" disabled={!reviewed || (dataSource === "api" && !recipient) || state === "sending" || state === "sent"} onClick={send}>
        {state === "sending" ? "SENDING…" : state === "sent" ? "APPROVED ✓" : "APPROVE & SEND"}
      </button>
      <p className={`send-message ${state}`}>{message || (dataSource === "api" ? "The backend enforces ALLOWED_RECIPIENTS and owns all delivery logic." : "Fixture mode requires the backend before approval can be recorded.")}</p>
    </div>
  );
}
