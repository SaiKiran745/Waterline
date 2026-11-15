"use client";

import { useEffect, useRef, useState } from "react";
import { PanelState } from "./PanelState";
import { FilesPanel } from "./FilesPanel";
import { subscribeToEvents } from "@/lib/data";
import type { AgentSessionController } from "@/hooks/useAgentSession";
import type { AgentEvent, ReplayRun } from "@/lib/contracts";

const agentLabels: Record<AgentEvent["agent"], string> = {
  "orchestrator": "Orchestrator", "site-scout": "Site scout", "interior-surveyor": "Interior surveyor",
  "market-analyst": "Market analyst", "scenario-builder": "Scenario builder",
  "mitigation-planner": "Mitigation planner", "communications": "Communications",
};

type Signal = "plan" | "batch" | "relook" | "discrepancy" | "memory-applied" | "memory-skipped" | "replan" | "skill" | "file" | "approval" | null;

function eventSignal(event: AgentEvent): Signal {
  const text = `${event.text} ${JSON.stringify(event.data ?? {})}`.toLowerCase();
  if (event.type === "awaiting_approval") return "approval";
  if (event.type === "replan") return "replan";
  if (event.type === "plan") return "plan";
  if (text.includes("layer discrepancy")) return "discrepancy";
  if (text.includes("re-look") || text.includes("relook") || text.includes("neighboring scan") || text.includes("neighbouring scan")) return "relook";
  if (text.includes("memory") || text.includes("correction") || text.includes("skipped")) return text.includes("skip") ? "memory-skipped" : "memory-applied";
  if (typeof event.data?.batch === "number" || text.includes("survey batch") || text.includes("why now") || (text.includes("batch") && text.includes("reason"))) return "batch";
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
  plan: "Plan", batch: "Survey batch · reason", relook: "Re-look", discrepancy: "Layer discrepancy",
  "memory-applied": "Memory applied", "memory-skipped": "Memory skipped · reason", replan: "Re-plan · priorities", skill: "Skill loaded", file: "File written", approval: "Approval wait",
};

const eventIcons: Record<AgentEvent["type"], string> = {
  plan: "✦", tool_call: "↗", observation: "◉", decision: "◆", replan: "↻", artifact: "▤", awaiting_approval: "Ⅱ",
};

export function AgentTrace({ buildingId, fixtureEvents, dataSource, session }: { buildingId: string; fixtureEvents: AgentEvent[]; dataSource: string; session: AgentSessionController }) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [state, setState] = useState<"idle" | "connecting" | "open" | "replay" | "error" | "ended">(dataSource === "api" ? "idle" : "connecting");
  const [replayRun, setReplayRun] = useState<ReplayRun | null>(session.replay);
  const [filesOpen, setFilesOpen] = useState(false);
  const runIdRef = useRef("");

  useEffect(() => {
    if (dataSource === "api" && !session.eventsUrl) return;
    const runId = `${session.replay ? "replay" : "live"}:${session.replay?.run_id ?? session.status?.run_id ?? "fixture"}`;
    let firstEventOfRun = runIdRef.current !== runId;
    runIdRef.current = runId;
    return subscribeToEvents(buildingId, dataSource, fixtureEvents, (event) => {
      setEvents((current) => {
        const base = firstEventOfRun ? [] : current;
        firstEventOfRun = false;
        return base.some((item) => item.id === event.id) ? base : [...base, event].sort((a, b) => a.id - b.id);
      });
    }, setState, {
      eventsUrl: session.eventsUrl ?? undefined,
      onReplay: setReplayRun,
      onEnd: (summary) => { setState(summary.replay ? "replay" : "ended"); void session.receiveEnd(summary); },
    });
    // The stream version intentionally reconnects after every agent turn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildingId, dataSource, fixtureEvents, session.eventsUrl, session.replay, session.status?.run_id, session.streamVersion]);

  const replay = async () => { try { await session.playReplay(); } catch { /* Error is rendered verbatim. */ } };
  const recordedAt = replayRun?.recorded_at ?? session.latestRun?.recorded_at;
  const visibleState = replayRun ? "replay" : state;

  return (
    <div className="trace-tab">
      <div className="tab-heading trace-heading"><div><span className="eyebrow">Live agent flow</span><h2>Agent activity</h2></div><span className={`stream-state ${visibleState}`}>{visibleState === "replay" ? "Replay" : visibleState}</span></div>
      <div className="agent-run-controls">
        <span className={`agent-status ${session.statusLabel.toLowerCase().replaceAll(" ", "-")}`}>{session.statusLabel}</span>
        <button className="files-toggle" onClick={() => setFilesOpen((value) => !value)}>{filesOpen ? "Activity" : "Files"}</button>
        <button className="replay-button" disabled={session.busy || dataSource !== "api"} onClick={() => void replay()}>Replay last run{session.latestRun ? ` · ${new Date(session.latestRun.recorded_at).toLocaleString()}` : ""}</button>
      </div>
      {replayRun ? <div className="replay-banner"><b>Replay · not live</b><span>{replayRun.label}</span></div> : null}
      {session.error ? <PanelState kind="error" title="Agent endpoint error" detail={session.error} /> : null}
      {filesOpen ? <FilesPanel buildingId={buildingId} live={Boolean(session.status?.running)} refreshVersion={session.streamVersion} dataSource={dataSource} /> : <>
        {state === "error" && events.length === 0 ? <PanelState kind="error" title="Event stream disconnected" detail={`GET ${session.eventsUrl ?? `/buildings/${buildingId}/events`} → event stream disconnected`} /> : null}
        {events.length === 0 && state !== "error" ? <PanelState kind={state === "idle" ? "empty" : "loading"} title={state === "idle" ? "Agent has not run" : "Waiting for agent events"} detail={state === "idle" ? "Run the agent live, or replay the saved run with its timestamp." : "Plans, survey decisions, and artifacts will appear here."} /> : (
        <div className="trace-timeline">
            {events.map((event) => {
              const signal = eventSignal(event); const cached = isCached(event);
              return <details className={`trace-event ${event.type} ${signal ? `signal-${signal}` : ""}`} key={event.id}>
                <summary>
                  <span className="trace-event-icon" aria-hidden="true">{eventIcons[event.type]}</span>
                  <span className="trace-event-copy"><span>{signal ? signalLabels[signal] : event.type.replace("_", " ")}{cached ? " · cached" : ""}</span><b>{event.text}</b></span>
                  <time>{new Date(event.ts).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time>
                </summary>
                <div className="trace-event-details"><span>{agentLabels[event.agent]} · {event.type.replace("_", " ")}</span>{cached ? <b className="cache-badge">Cached result</b> : null}<p>{event.text}</p>{event.refs.length ? <small>{event.refs.join(" · ")}</small> : null}</div>
              </details>;
            })}
        </div>
        )}
      </>}
      {recordedAt && replayRun ? <footer className="replay-footer">Saved run recorded {new Date(recordedAt).toLocaleString()} · replay, not a live agent session</footer> : null}
    </div>
  );
}
