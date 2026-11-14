"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PanelState } from "./PanelState";
import { subscribeToEvents } from "@/lib/data";
import type { AgentSessionController } from "@/hooks/useAgentSession";
import type { AgentEvent, ReplayRun } from "@/lib/contracts";

const agentLabels: Record<AgentEvent["agent"], string> = {
  "orchestrator": "Orchestrator", "site-scout": "Site scout", "interior-surveyor": "Interior surveyor",
  "market-analyst": "Market analyst", "scenario-builder": "Scenario builder",
  "mitigation-planner": "Mitigation planner", "communications": "Communications",
};

type Signal = "plan" | "batch" | "relook" | "discrepancy" | "memory" | "replan" | "skill" | "file" | "approval" | null;

function eventSignal(event: AgentEvent): Signal {
  const text = `${event.text} ${JSON.stringify(event.data ?? {})}`.toLowerCase();
  if (event.type === "awaiting_approval") return "approval";
  if (event.type === "replan") return "replan";
  if (event.type === "plan") return "plan";
  if (text.includes("layer discrepancy")) return "discrepancy";
  if (text.includes("re-look") || text.includes("relook") || text.includes("neighboring scan") || text.includes("neighbouring scan")) return "relook";
  if (text.includes("memory") || text.includes("correction") || text.includes("skipped")) return "memory";
  if (text.includes("survey batch") || (text.includes("batch") && text.includes("reason"))) return "batch";
  if (text.includes("loaded skill") || text.includes("skill.md")) return "skill";
  if (event.type === "artifact" || text.includes("wrote /dossier")) return "file";
  return null;
}

function isCached(event: AgentEvent) {
  const data = event.data ?? {};
  const text = event.text.toLowerCase();
  return data.cached === true || data.cache_hit === true || data.source === "cache" || text.includes("cache hit") || text.includes("from cache") || text.includes("cached result");
}

const signalLabels: Record<Exclude<Signal, null>, string> = {
  plan: "PLAN", batch: "SURVEY BATCH + REASON", relook: "RE-LOOK", discrepancy: "LAYER DISCREPANCY",
  memory: "AGENT MEMORY", replan: "RE-PLAN + PRIORITIES", skill: "SKILL LOADED", file: "FILE WRITTEN", approval: "APPROVAL WAIT",
};

export function AgentTrace({ buildingId, fixtureEvents, dataSource, session, depth }: { buildingId: string; fixtureEvents: AgentEvent[]; dataSource: string; session: AgentSessionController; depth: number }) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [state, setState] = useState<"idle" | "connecting" | "open" | "replay" | "error" | "ended">(dataSource === "api" ? "idle" : "connecting");
  const [replayRun, setReplayRun] = useState<ReplayRun | null>(session.replay);
  const [quickScanEnabled, setQuickScanEnabled] = useState(false);
  const [positionBudget, setPositionBudget] = useState(6);
  const runIdRef = useRef("");

  useEffect(() => {
    const runId = session.replay?.run_id ?? session.status?.run_id ?? "fixture";
    if (runIdRef.current && runIdRef.current !== runId) setEvents([]);
    runIdRef.current = runId;
  }, [session.replay?.run_id, session.status?.run_id]);

  useEffect(() => {
    if (dataSource === "api" && !session.eventsUrl) return;
    return subscribeToEvents(buildingId, dataSource, fixtureEvents, (event) => {
      setEvents((current) => current.some((item) => item.id === event.id) ? current : [...current, event].sort((a, b) => a.id - b.id));
    }, setState, {
      eventsUrl: session.eventsUrl ?? undefined,
      onReplay: setReplayRun,
      onEnd: (summary) => { setState(summary.replay ? "replay" : "ended"); void session.receiveEnd(summary); },
    });
    // The stream version intentionally reconnects after every agent turn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildingId, dataSource, fixtureEvents, session.eventsUrl, session.streamVersion]);

  const groups = useMemo(() => {
    const grouped = new Map<AgentEvent["agent"], AgentEvent[]>();
    events.forEach((event) => grouped.set(event.agent, [...(grouped.get(event.agent) ?? []), event]));
    return [...grouped.entries()];
  }, [events]);
  const start = async () => { try { await session.start(depth, quickScanEnabled ? positionBudget : undefined); } catch { /* Error is rendered verbatim. */ } };
  const replay = async () => { try { await session.playReplay(); } catch { /* Error is rendered verbatim. */ } };
  const recordedAt = replayRun?.recorded_at ?? session.latestRun?.recorded_at;

  return (
    <div className="trace-tab">
      <div className="tab-heading trace-heading"><div><span className="eyebrow">LIVE AGENT FLOW</span><h2>Agent activity</h2></div><span className={`stream-state ${state}`}>{state === "replay" ? "REPLAY" : state.toUpperCase()}</span></div>
      <div className="agent-run-controls">
        <div><button className="run-agent-button" disabled={session.busy || dataSource !== "api"} onClick={() => void start()}>{session.action === "run" ? "STARTING…" : "RUN AGENT"}</button><span className={`agent-status ${session.statusLabel.toLowerCase().replaceAll(" ", "-")}`}>{session.statusLabel}</span></div>
        <label className="quick-scan-control"><input type="checkbox" checked={quickScanEnabled} onChange={(event) => setQuickScanEnabled(event.target.checked)} /><span>QUICK SCAN (PARTIAL SURVEY)</span>{quickScanEnabled ? <input aria-label="Quick scan position budget" type="number" min="1" max="100" value={positionBudget} onChange={(event) => setPositionBudget(Math.max(1, Number(event.target.value)))} /> : null}</label>
        <button className="replay-button" disabled={session.busy || !session.latestRun} onClick={() => void replay()}>REPLAY LAST RUN{session.latestRun ? ` · ${new Date(session.latestRun.recorded_at).toLocaleString()}` : ""}</button>
      </div>
      {replayRun ? <div className="replay-banner"><b>REPLAY · NOT LIVE</b><span>{replayRun.label}</span></div> : null}
      {session.quickScan ? <div className="quick-scan-banner">QUICK SCAN (PARTIAL SURVEY) · POSITION BUDGET {session.quickScan}</div> : null}
      {session.error ? <PanelState kind="error" title="Agent endpoint error" detail={session.error} /> : null}
      {state === "error" && events.length === 0 ? <PanelState kind="error" title="Event stream disconnected" detail={`GET ${session.eventsUrl ?? `/buildings/${buildingId}/events`} → event stream disconnected`} /> : null}
      {events.length === 0 && state !== "error" ? <PanelState kind={state === "idle" ? "empty" : "loading"} title={state === "idle" ? "Agent has not run" : "Waiting for agent events"} detail={state === "idle" ? "Run the agent live, or replay the saved run with its timestamp." : "Plans, survey decisions, and artifacts will appear here."} /> : (
        <div className="trace-groups">
          {groups.map(([agent, agentEvents]) => <section className="trace-group" key={agent}>
            <h3><i />{agentLabels[agent]}<span>{agentEvents.length}</span></h3>
            {agentEvents.map((event) => {
              const signal = eventSignal(event); const cached = isCached(event);
              return <article className={`trace-event ${event.type} ${signal ? `signal-${signal}` : ""}`} key={event.id}>
                <div><span>{event.type.replace("_", " ")}</span><time>{new Date(event.ts).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time></div>
                {signal || cached ? <div className="trace-signal-row">{signal ? <b>{signalLabels[signal]}</b> : null}{cached ? <b className="cache-badge">CACHED RESULT</b> : null}</div> : null}
                <p>{event.text}</p>{event.refs.length ? <small>{event.refs.join(" · ")}</small> : null}
              </article>;
            })}
          </section>)}
        </div>
      )}
      {recordedAt && state === "replay" ? <footer className="replay-footer">Saved run recorded {new Date(recordedAt).toLocaleString()} · replay, not a live agent session</footer> : null}
    </div>
  );
}
