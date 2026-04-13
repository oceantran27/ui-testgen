import {
  FiAlertCircle,
  FiCheckCircle,
  FiLoader,
  FiMessageCircle,
  FiXCircle,
} from "react-icons/fi";
import type { DebateStreamStatus } from "./types";

interface DebateFloatingBubbleProps {
  visible: boolean;
  status: DebateStreamStatus;
  eventCount: number;
  unreadCount: number;
  onOpen: () => void;
}

const statusLabel: Record<DebateStreamStatus, string> = {
  idle: "Idle",
  running: "Live",
  completed: "Completed",
  failed: "Failed",
  expired: "Expired",
  error: "Polling issue",
};

const StatusIcon = ({ status }: { status: DebateStreamStatus }) => {
  if (status === "running") {
    return <FiLoader className="h-4 w-4 animate-spin" />;
  }
  if (status === "completed") {
    return <FiCheckCircle className="h-4 w-4" />;
  }
  if (status === "failed" || status === "expired") {
    return <FiXCircle className="h-4 w-4" />;
  }
  if (status === "error") {
    return <FiAlertCircle className="h-4 w-4" />;
  }
  return <FiMessageCircle className="h-4 w-4" />;
};

export function DebateFloatingBubble({
  visible,
  status,
  eventCount,
  unreadCount,
  onOpen,
}: DebateFloatingBubbleProps) {
  if (!visible) {
    return null;
  }

  const highlightClass =
    status === "running"
      ? "border-sky-200 bg-sky-50 text-sky-700"
      : status === "completed"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : status === "failed" || status === "expired"
          ? "border-rose-200 bg-rose-50 text-rose-700"
          : "border-amber-200 bg-amber-50 text-amber-700";

  return (
    <button
      type="button"
      onClick={onOpen}
      className="fixed bottom-6 right-4 z-40 w-[min(92vw,22rem)] rounded-2xl border border-slate-200 bg-white/95 p-3 text-left shadow-xl backdrop-blur-sm transition hover:-translate-y-0.5 hover:shadow-2xl sm:right-6"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-white">
            <FiMessageCircle className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-semibold text-slate-900">
              Committee Debate
            </p>
            <p className="text-xs text-slate-500">Read-only transcript</p>
          </div>
        </div>

        {unreadCount > 0 && (
          <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-rose-500 px-2 py-0.5 text-xs font-bold text-white">
            {unreadCount}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${highlightClass}`}
        >
          <StatusIcon status={status} />
          {statusLabel[status]}
        </span>
        <span className="text-xs font-medium text-slate-600">
          {eventCount} events
        </span>
      </div>
    </button>
  );
}
