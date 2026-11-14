"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  decideAgentSend,
  getAgentStatus,
  getLatestRun,
  postAgentDepth,
  replayLastRun,
  requestAgentSend,
  runAgent,
} from "@/lib/data";
import type { AgentActionResult, AgentStatus, ReplayRun } from "@/lib/contracts";

type ActionName = "idle" | "run" | "replay" | "depth" | "draft" | "approve" | "reject";

export function useAgentSession(buildingId: string, enabled: boolean) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [latestRun, setLatestRun] = useState<ReplayRun | null>(null);
  const [action, setAction] = useState<ActionName>("idle");
  const [error, setError] = useState("");
  const [eventsUrl, setEventsUrl] = useState<string | null>(null);
  const [streamVersion, setStreamVersion] = useState(0);
  const [replay, setReplay] = useState<ReplayRun | null>(null);
  const [quickScan, setQuickScan] = useState<number | null>(null);
  const [sendResult, setSendResult] = useState("");

  const refresh = useCallback(async () => {
    if (!enabled) return null;
    try {
      const next = await getAgentStatus(buildingId);
      setStatus(next);
      if (next.run_id && next.events_url) setEventsUrl(next.events_url);
      return next;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    }
  }, [buildingId, enabled]);

  useEffect(() => {
    if (!enabled) return;
    const timer = window.setTimeout(() => {
      void refresh();
      getLatestRun(buildingId).then(setLatestRun).catch((caught) => {
        const message = caught instanceof Error ? caught.message : String(caught);
        if (!message.includes("→ 404")) setError(message);
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [buildingId, enabled, refresh]);

  useEffect(() => {
    if (!enabled || !status?.run_id) return;
    const timer = window.setInterval(() => void refresh(), status.running ? 1000 : 2500);
    return () => window.clearInterval(timer);
  }, [enabled, refresh, status?.run_id, status?.running]);

  const beginStream = useCallback((result: AgentActionResult, replayRun: ReplayRun | null = null) => {
    if (result.events_url) setEventsUrl(result.events_url);
    setReplay(replayRun);
    setStreamVersion((value) => value + 1);
  }, []);

  const perform = useCallback(async (name: ActionName, operation: () => Promise<AgentActionResult>) => {
    setAction(name);
    setError("");
    try {
      const result = await operation();
      setStatus(result);
      return result;
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
      throw caught;
    } finally {
      setAction("idle");
    }
  }, []);

  const start = useCallback(async (depthFt: number, positionBudget?: number) => {
    const result = await perform("run", () => runAgent(buildingId, depthFt, positionBudget));
    setQuickScan(positionBudget ?? null);
    setSendResult("");
    beginStream(result);
  }, [beginStream, buildingId, perform]);

  const playReplay = useCallback(async () => {
    const result = await perform("replay", () => replayLastRun(buildingId));
    const replayRun = result as ReplayRun;
    setLatestRun(replayRun);
    beginStream(result, replayRun);
  }, [beginStream, buildingId, perform]);

  const changeDepth = useCallback(async (depthFt: number) => {
    const result = await perform("depth", () => postAgentDepth(buildingId, depthFt));
    beginStream(result);
  }, [beginStream, buildingId, perform]);

  const draftAndSend = useCallback(async (recipient: string) => {
    const result = await perform("draft", () => requestAgentSend(buildingId, recipient));
    beginStream(result);
  }, [beginStream, buildingId, perform]);

  const decide = useCallback(async (approved: boolean, recipient: string) => {
    const result = await perform(approved ? "approve" : "reject", () => decideAgentSend(buildingId, approved, recipient));
    beginStream(result);
    setSendResult(approved ? `Delivery approved for ${recipient}; waiting for the agent result…` : "draft only, not sent");
  }, [beginStream, buildingId, perform]);

  const receiveEnd = useCallback(async (summary: Record<string, unknown>) => {
    if (summary.replay) return;
    const next = await refresh();
    if (next?.waiting_for_approval) return;
    const result = summary.result;
    if (typeof result === "object" && result) {
      const record = result as Record<string, unknown>;
      if (record.status === "sent") setSendResult(`sent to ${String(record.recipient ?? "approved recipient")}`);
      if (record.status === "draft_only") setSendResult("draft only, not sent");
    }
  }, [refresh]);

  const active = Boolean(status?.run_id && !replay);
  const busy = action !== "idle" || Boolean(status?.running);
  const statusLabel = useMemo(() => {
    if (replay) return "REPLAY";
    if (status?.error) return "ERROR";
    if (status?.waiting_for_approval) return "AWAITING APPROVAL";
    if (status?.running) return "AGENT WORKING";
    if (status?.run_id) return "SESSION READY";
    return "NO SESSION";
  }, [replay, status]);

  return {
    status,
    latestRun,
    action,
    error,
    eventsUrl,
    streamVersion,
    replay,
    quickScan,
    sendResult,
    active,
    busy,
    statusLabel,
    start,
    playReplay,
    changeDepth,
    draftAndSend,
    decide,
    refresh,
    receiveEnd,
    setReplay,
  };
}

export type AgentSessionController = ReturnType<typeof useAgentSession>;
