import { useCallback, useState } from "react";
import type { BddHappyPathResult } from "./types";

const parseBdd = (result: string): BddHappyPathResult | null => {
  try {
    return JSON.parse(result) as BddHappyPathResult;
  } catch {
    return null;
  }
};

interface BddResultDisplayProps {
  result: string;
  showTitle?: boolean;
  className?: string;
}

export function BddResultDisplay({
  result,
  showTitle = true,
  className = "",
}: BddResultDisplayProps) {
  const data = parseBdd(result);
  const [combinedOpen, setCombinedOpen] = useState(true);

  const onCopy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore
    }
  }, []);

  if (!data) {
    return (
      <div className={`card ${className}`}>
        <p className="text-sm text-amber-700">Could not parse BDD result.</p>
        <pre className="mt-2 max-h-48 overflow-auto rounded border bg-gray-50 p-2 text-xs wrap-anywhere whitespace-pre-wrap">
          {result}
        </pre>
      </div>
    );
  }

  return (
    <div className={`card relative overflow-hidden ${className}`}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-linear-to-r from-emerald-100/50 via-teal-100/30 to-transparent" />

      {showTitle && (
        <div className="relative mb-4">
          <h2 className="text-gradient from-emerald-700 to-teal-600 text-2xl font-extrabold">
            BDD (Happy path)
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            {data.model} — Gherkin-style scenarios
          </p>
        </div>
      )}

      <div className="relative space-y-4">
        <div className="rounded-xl border border-gray-200/90 bg-white/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Feature
          </p>
          <p className="mt-1 text-lg font-semibold text-gray-800 wrap-anywhere">
            {data.feature.name}
          </p>
          {data.feature.description ? (
            <p className="mt-2 text-sm text-gray-600 wrap-anywhere">
              {data.feature.description}
            </p>
          ) : null}
        </div>

        <div className="space-y-3">
          {data.scenarios.map((sc, index) => (
            <details
              key={`${sc.id}-${index}`}
              className="group overflow-hidden rounded-xl border border-gray-200/90 bg-gray-50/90 shadow-inner"
              open={index === 0}
            >
              <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 border-b border-gray-200/70 bg-white/70 px-4 py-3 [&::-webkit-details-marker]:hidden">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-gray-500">{sc.id}</p>
                  <p className="text-sm font-semibold text-gray-800 wrap-anywhere">
                    {sc.title}
                  </p>
                </div>
                <span className="text-sm text-gray-400 transition-transform group-open:rotate-180">
                  ▾
                </span>
              </summary>
              <pre className="custom-scrollbar max-h-80 overflow-auto px-4 py-3 font-mono text-sm leading-6 text-gray-800 wrap-anywhere whitespace-pre-wrap">
                {sc.gherkin}
              </pre>
            </details>
          ))}
        </div>

        {data.combined_gherkin ? (
          <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/40 p-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setCombinedOpen((o) => !o)}
                className="text-sm font-semibold text-emerald-800 hover:underline"
              >
                {combinedOpen ? "Hide" : "Show"} combined Gherkin
              </button>
              <button
                type="button"
                onClick={() => void onCopy(data.combined_gherkin)}
                className="rounded-lg border border-emerald-300 bg-white px-3 py-1 text-xs font-semibold text-emerald-800 hover:bg-emerald-50"
              >
                Copy all
              </button>
            </div>
            {combinedOpen ? (
              <pre className="custom-scrollbar max-h-96 overflow-auto rounded-lg border border-emerald-100 bg-white/90 p-3 font-mono text-sm leading-6 text-gray-800 wrap-anywhere whitespace-pre-wrap">
                {data.combined_gherkin}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function isBddResultJsonString(result: string): boolean {
  try {
    const obj = JSON.parse(result) as unknown;
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
      return false;
    }
    const o = obj as Record<string, unknown>;
    const feature = o.feature;
    if (!feature || typeof feature !== "object" || feature === null) {
      return false;
    }
    const name = (feature as Record<string, unknown>).name;
    if (typeof name !== "string" || !name.trim()) {
      return false;
    }
    const scenarios = o.scenarios;
    if (!Array.isArray(scenarios) || scenarios.length === 0) {
      return false;
    }
    const first = scenarios[0] as Record<string, unknown> | undefined;
    return Boolean(first && typeof first.gherkin === "string");
  } catch {
    return false;
  }
}
