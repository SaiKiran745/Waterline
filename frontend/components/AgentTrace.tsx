"use client";

import { useEffect, useMemo, useState } from "react";
import { PanelState } from "./PanelState";
import { subscribeToEvents } from "@/lib/data";
import type { AgentEvent } from "@/lib/contracts";

const agentLabels: Record<AgentEvent["agent"], string> = {
  "orchestrator": "Orchestrator",
  "site-scout": "Site scout",
  "interior-surveyor": "Interior surveyor",
  "market-analyst": "Market analyst",
  "scenario-builder": "Scenario builder",
  "mitigation-planner": "Mitigation planner",
  "communications": "Communications",
};

export function AgentTrace({ buildingId, fixtureEvents, dataSource }: { buildingId: string; fixtureEvents: AgentEvent[]; dataSource: string }) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [state, setState] = useState<"connecting" | "open" | "replay" | "error">("connecting");
  useEffect(() => {
    return subscribeToEvents(buildingId, dataSource, fixtureEvents, (event) => {
      setEvents((current) => current.some((item) => item.id === event.id) ? current : [...current, event].sort((a, b) => a.id - b.id));
    }, setState);
  }, [buildingId, dataSource, fixtureEvents]);
  const groups = useMemo(() => {
    const grouped = new Map<AgentEvent["agent"], AgentEvent[]>();
    events.forEach((event) => grouped.set(event.agent, [...(grouped.get(event.agent) ?? []), event]));
    return [...grouped.entries()];
  }, [events]);
  return (
    <div className="trace-tab">
      <div className="tab-heading trace-heading"><div><span className="eyebrow">LIVE REASONING TRACE</span><h2>Agent activity</h2></div><span className={`stream-state ${state}`}>{state === "replay" ? "FIXTURE REPLAY" : state.toUpperCase()}</span></div>
      {state === "error" && events.length === 0 ? <PanelState kind="error" title="Event stream disconnected" detail="Check the backend SSE endpoint and CORS settings." /> : null}
      {events.length === 0 && state !== "error" ? <PanelState kind="loading" title="Waiting for agent events" detail="Plans and decisions will appear here." /> : (
        <div className="trace-groups">
          {groups.map(([agent, agentEvents]) => (
            <section className="trace-group" key={agent}>
              <h3><i />{agentLabels[agent]}<span>{agentEvents.length}</span></h3>
              {agentEvents.map((event) => (
                <article className={`trace-event ${event.type}`} key={event.id}>
                  <div><span>{event.type.replace("_", " ")}</span><time>{new Date(event.ts).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time></div>
                  <p>{event.text}</p>
                  {event.refs.length ? <small>{event.refs.join(" · ")}</small> : null}
                </article>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
