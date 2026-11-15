"use client";

import { useState } from "react";
import { getArtifactUrl } from "@/lib/data";
import type { AgentSessionController } from "@/hooks/useAgentSession";
import type { Building, Mitigation } from "@/lib/contracts";
import { buildingTitle } from "@/lib/presentation";

export function ApprovePanel({ building, currentDepth, dataSource, session }: { building: Building; mitigations: Mitigation[]; currentDepth: number; dataSource: string; session: AgentSessionController }) {
  const [reviewed, setReviewed] = useState(false);
  const [recipient, setRecipient] = useState("");
  const [state, setState] = useState<"idle" | "drafting" | "deciding" | "error">("idle");
  const [message, setMessage] = useState("");
  const [artifactState, setArtifactState] = useState<"loading" | "ready" | "error">("loading");

  const draft = async () => {
    setState("drafting");
    try {
      await session.draftAndSend(recipient);
      setMessage("The agent is drafting the playbook and will pause for approval.");
      setState("idle");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Send failed."); setState("error"); }
  };
  const decide = async (approved: boolean) => {
    setState("deciding");
    try {
      await session.decide(approved, recipient);
      setMessage(approved ? `Approved. The backend agent is completing delivery to ${recipient}.` : "draft only, not sent");
      setState("idle");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Approval decision failed."); setState("error"); }
  };

  const playbookUrl = getArtifactUrl(building.id, "playbook", currentDepth);
  return (
    <div className="approve-tab">
      <div className="tab-heading"><h2>Review and send</h2><p>The backend owns delivery. Nothing leaves Waterline until you approve it here.</p></div>
      <section className="playbook-sheet">
        <header><div><span>Pre-storm playbook</span><b>{buildingTitle(building)}</b></div><small>{currentDepth.toFixed(2)} ft scenario · {artifactState}</small></header>
        {dataSource === "api" ? <iframe key={playbookUrl} src={playbookUrl} title="Pre-storm playbook" onLoad={() => setArtifactState("ready")} onError={() => setArtifactState("error")} /> : <p>Connect the backend to render the playbook.</p>}
      </section>
      {dataSource === "api" ? <label className="recipient-field"><span>Allowed recipient</span><input type="email" value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="ops@example.com" /></label> : null}
      <button className="draft-send-button" disabled={dataSource !== "api" || !recipient || !session.active || session.busy} onClick={() => void draft()}>{state === "drafting" ? "Drafting…" : "Draft and send"}</button>
      {session.status?.waiting_for_approval ? <div className="approval-wait-banner"><b>Agent paused for approval</b><span>Review the generated playbook, then approve or reject.</span></div> : null}
      <label className="approval-check"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span><i />I reviewed this playbook and approve delivery.</span></label>
      <div className="approval-decision-row"><button className="reject-button" disabled={!session.status?.waiting_for_approval || session.busy} onClick={() => void decide(false)}>Reject · draft only</button><button className="approve-button" disabled={!reviewed || !recipient || !session.status?.waiting_for_approval || session.busy} onClick={() => void decide(true)}>{state === "deciding" ? "Recording…" : "Approve and send"}</button></div>
      <p className={`send-message ${state}`}>{session.sendResult || message || session.error || (dataSource === "api" ? "Waiting for a draft request." : "Backend connection required.")}</p>
    </div>
  );
}
