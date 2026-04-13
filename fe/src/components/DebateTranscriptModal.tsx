import { useMemo, useState } from "react";
import { FiRefreshCw, FiX } from "react-icons/fi";
import type { DebateEvent, DebateStreamStatus } from "./types";

interface DebateTranscriptModalProps {
  isOpen: boolean;
  requestId: string | null;
  status: DebateStreamStatus;
  events: DebateEvent[];
  errorMessage: string | null;
  onClose: () => void;
  onRetry: () => void;
}

interface DebateTab {
  id: string;
  label: string;
}

const statusLabel: Record<DebateStreamStatus, string> = {
  idle: "Idle",
  running: "Live",
  completed: "Completed",
  failed: "Failed",
  expired: "Expired",
  error: "Polling issue",
};

const formatTimestamp = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString();
};

const normalizeRole = (role: string): string => {
  const normalized = role.trim().toLowerCase();
  if (
    ["ba", "qa", "ux", "judge", "system", "specialist"].includes(normalized)
  ) {
    return normalized;
  }
  return "system";
};

const roleContainerClass = (role: string): string => {
  if (role === "ba") {
    return "justify-end";
  }
  if (role === "judge") {
    return "justify-center";
  }
  return "justify-start";
};

const roleBubbleClass = (role: string): string => {
  if (role === "ba") {
    return "border-amber-200 bg-amber-50 text-amber-900";
  }
  if (role === "qa") {
    return "border-rose-200 bg-rose-50 text-rose-900";
  }
  if (role === "ux") {
    return "border-cyan-200 bg-cyan-50 text-cyan-900";
  }
  if (role === "judge") {
    return "border-indigo-200 bg-indigo-50 text-indigo-900";
  }
  if (role === "specialist") {
    return "border-violet-200 bg-violet-50 text-violet-900";
  }
  return "border-slate-200 bg-slate-50 text-slate-800";
};

const roleLabel = (role: string): string => {
  if (role === "ba") {
    return "BA";
  }
  if (role === "qa") {
    return "QA";
  }
  if (role === "ux") {
    return "UX";
  }
  if (role === "judge") {
    return "JUDGE";
  }
  if (role === "specialist") {
    return "SPECIALIST";
  }
  return "SYSTEM";
};

export function DebateTranscriptModal({
  isOpen,
  requestId,
  status,
  events,
  errorMessage,
  onClose,
  onRetry,
}: DebateTranscriptModalProps) {
  const tabs = useMemo(() => {
    const scenarioIds = Array.from(
      new Set(
        events
          .map((event) => event.scenario_id?.trim() ?? "")
          .filter((scenarioId) => scenarioId.length > 0),
      ),
    );

    const result: DebateTab[] = [{ id: "__all", label: "All" }];

    if (
      events.some((event) => !event.scenario_id || !event.scenario_id.trim())
    ) {
      result.push({ id: "__system", label: "System" });
    }

    for (const scenarioId of scenarioIds) {
      result.push({ id: scenarioId, label: scenarioId });
    }

    return result;
  }, [events]);

  const [activeTab, setActiveTab] = useState<string>("__all");

  const effectiveActiveTab = tabs.some((tab) => tab.id === activeTab)
    ? activeTab
    : "__all";

  const filteredEvents = useMemo(() => {
    if (effectiveActiveTab === "__all") {
      return events;
    }
    if (effectiveActiveTab === "__system") {
      return events.filter(
        (event) => !event.scenario_id || !event.scenario_id.trim(),
      );
    }
    return events.filter(
      (event) => (event.scenario_id ?? "").trim() === effectiveActiveTab,
    );
  }, [effectiveActiveTab, events]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex h-[min(86vh,52rem)] w-[min(96vw,72rem)] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Debate transcript
            </p>
            <h2 className="truncate text-xl font-bold text-slate-900">
              Request {requestId ?? "-"}
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
              {statusLabel[status]}
            </span>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            >
              <FiX className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="border-b border-slate-200 px-4 py-3">
          <div className="custom-scrollbar flex gap-2 overflow-x-auto pb-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                  effectiveActiveTab === tab.id
                    ? "border-slate-800 bg-slate-800 text-white"
                    : "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {errorMessage && (
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <span>{errorMessage}</span>
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-800 transition hover:bg-amber-100"
              >
                <FiRefreshCw className="h-3.5 w-3.5" />
                Retry now
              </button>
            </div>
          )}
        </div>

        <div className="custom-scrollbar flex-1 space-y-3 overflow-y-auto bg-slate-100/70 p-4">
          {filteredEvents.length === 0 ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 text-center text-sm text-slate-500">
              No transcript events for this tab yet.
            </div>
          ) : (
            filteredEvents.map((event) => {
              const role = normalizeRole(event.role);
              return (
                <div
                  key={event.event_id}
                  className={`flex ${roleContainerClass(role)}`}
                >
                  <article
                    className={`max-w-[92%] rounded-2xl border px-3 py-2 shadow-sm sm:max-w-[75%] ${roleBubbleClass(role)}`}
                  >
                    <div className="mb-1 flex items-center justify-between gap-3 text-[11px] font-semibold">
                      <span>{roleLabel(role)}</span>
                      <span className="text-[10px] opacity-75">
                        #{event.sequence} · {formatTimestamp(event.timestamp)}
                      </span>
                    </div>
                    <p className="text-sm leading-6 whitespace-pre-wrap wrap-anywhere">
                      {event.message}
                    </p>
                  </article>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
