import type { UIStateSummary } from "../types/run";

const ST_SUFFIX = /^st_[0-9a-f]{12}_(.+)$/i;

const MAX_LABEL = 56;

function truncate(s: string, max: number): string {
  const t = s.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

/** Compact id for subline: avoid unreadable slice(-6) tails */
export function shortenStateId(id: string): string {
  if (id.length <= 28) return id;
  return `${id.slice(0, 12)}…${id.slice(-10)}`;
}

export type StateLabelParts = {
  /** Human-readable primary label */
  shortLabel: string;
  /** Full state_id for tooltips / copy */
  title: string;
  /** Monospace-friendly shortened id */
  shortId: string;
};

/**
 * Readable label for a UI state in flows / intents (purpose, filename, or id).
 */
export function formatStateLabel(
  stateId: string,
  summary?: UIStateSummary | null,
): StateLabelParts {
  const title = stateId;
  const shortId = shortenStateId(stateId);

  const fromSummary =
    (summary?.state_summary?.trim()) ||
    (summary?.screen_purpose?.trim()) ||
    (summary?.screen_type?.trim()) ||
    (summary?.page_type?.trim()) ||
    (summary?.original_filename?.trim());

  if (fromSummary) {
    return {
      shortLabel: truncate(fromSummary, MAX_LABEL),
      title,
      shortId,
    };
  }

  const m = stateId.match(ST_SUFFIX);
  if (m?.[1]) {
    return {
      shortLabel: truncate(m[1], MAX_LABEL),
      title,
      shortId,
    };
  }

  return {
    shortLabel: shortId,
    title,
    shortId,
  };
}
