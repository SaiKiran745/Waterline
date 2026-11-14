"use client";

import { useState } from "react";
import { getArtifactUrl } from "@/lib/data";
import type { AgentSessionController } from "@/hooks/useAgentSession";
import type { Building, Mitigation } from "@/lib/contracts";
import { buildingTitle, showAddresses } from "@/lib/presentation";

export function ApprovePanel({ building, mitigations, currentDepth, dataSource, session }: { building: Building; mitigations: Mitigation[]; currentDepth: number; dataSource: string; session: AgentSessionController }) {
  const [reviewed, setReviewed] = useState(false);
  const [recipient, setRecipient] = useState("");
  const [state, setState] = useState<"idle" | "drafting" | "deciding" | "error">("idle");
  const [message, setMessage] = useState("");
  const [artifact, setArtifact] = useState<"report" | "playbook">("playbook");
  const [artifactState, setArtifactState] = useState<"loading" | "ready" | "error">("loading");
  const draft = async () => {
    setState("drafting");
    try {
      await session.draftAndSend(recipient);
      setMessage("The agent is drafting the report and playbook. Approval remains locked until it pauses.");
      setState("idle");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Send failed."); setState("error");
    }
  };
  const decide = async (approved: boolean) => {
    setState("deciding");
    try {
      await session.decide(approved, recipient);
      setMessage(approved ? `Approved. The backend agent is completing delivery to ${recipient}.` : "draft only, not sent");
      setState("idle");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Approval decision failed."); setState("error");
    }
  };
  const playbookActions = mitigations
    .filter((item) => item.depth_ft === currentDepth)
    .sort((a, b) => a.rank - b.rank);
  const artifactsReady = dataSource === "api";
  const artifactUrl = getArtifactUrl(building.id, artifact, currentDepth);
  return (
    <div className="approve-tab">
      <div className="tab-heading"><span className="eyebrow">HUMAN CHECKPOINT</span><h2>Draft, review & approve</h2><p>The agent drafts first, then pauses here. Nothing is sent before an explicit decision.</p></div>
      <div className="artifact-card">
        <div className="artifact-icon">▤</div><div><span>BACKEND ARTIFACTS</span><b>{buildingTitle(building)}</b>{showAddresses ? <small>{building.address}</small> : null}<small>{artifactsReady ? `Rendered for the current ${currentDepth.toFixed(2)} ft scenario` : "Backend connection required"}</small></div>{artifactsReady ? <span className="artifact-links"><a href={getArtifactUrl(building.id, "report", currentDepth)} target="_blank" rel="noreferrer">REPORT ↗</a><a href={getArtifactUrl(building.id, "playbook", currentDepth)} target="_blank" rel="noreferrer">PLAYBOOK ↗</a></span> : <span className="pending-chip">PENDING</span>}
      </div>
      {artifactsReady ? <div className="artifact-preview"><div><button className={artifact === "report" ? "active" : ""} onClick={() => { setArtifact("report"); setArtifactState("loading"); }}>REPORT</button><button className={artifact === "playbook" ? "active" : ""} onClick={() => { setArtifact("playbook"); setArtifactState("loading"); }}>PLAYBOOK</button><span>{artifactState.toUpperCase()}</span></div><iframe key={artifactUrl} src={artifactUrl} title={`${artifact} preview`} onLoad={() => setArtifactState("ready")} onError={() => setArtifactState("error")} /></div> : null}
      <div className="playbook-preview">
        <span>PRE-STORM PLAYBOOK</span><h3>First 24 hours</h3>
        {playbookActions.length === 0 ? <p>No mitigation actions are available yet.</p> : <ol>{playbookActions.map((item) => <li key={item.id}><i>{item.rank}</i><span>{item.action}<small>{item.payback_note}</small></span></li>)}</ol>}
      </div>
      {dataSource === "api" ? <label className="recipient-field"><span>ALLOWED RECIPIENT</span><input type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="ops@example.com" /></label> : null}
      <button className="draft-send-button" disabled={dataSource !== "api" || !recipient || !session.active || session.busy} onClick={() => void draft()}>{state === "drafting" ? "DRAFTING…" : "DRAFT AND SEND"}</button>
      {session.status?.waiting_for_approval ? <div className="approval-wait-banner"><b>AGENT PAUSED FOR APPROVAL</b><span>Review the generated artifacts and choose approve or reject.</span></div> : null}
      <label className="approval-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span><i />I reviewed the current playbook and explicitly approve this send.</span></label>
      <div className="approval-decision-row"><button className="reject-button" disabled={!session.status?.waiting_for_approval || session.busy} onClick={() => void decide(false)}>REJECT · DRAFT ONLY</button><button className="approve-button" disabled={!reviewed || !recipient || !session.status?.waiting_for_approval || session.busy} onClick={() => void decide(true)}>{state === "deciding" ? "RECORDING…" : "APPROVE & SEND"}</button></div>
      <p className={`send-message ${state}`}>{session.sendResult || message || session.error || (dataSource === "api" ? "The backend enforces ALLOWED_RECIPIENTS and owns all email logic and keys." : "Fixture mode requires the backend before approval can be recorded.")}</p>
    </div>
  );
}
