import { useCallback, useState } from "react";
import type { TestScenarioSuite } from "./types";

const parseTestScenarioSuiteString = (
  result: string,
): TestScenarioSuite | null => {
  try {
    return JSON.parse(result) as TestScenarioSuite;
  } catch {
    return null;
  }
};

/** Legacy ranked-endpoint wrapper: prefers top-level `suite`; falls back to historic nested key when present. */
const parseLegacyWrappedSuite = (result: string): TestScenarioSuite | null => {
  try {
    const o = JSON.parse(result) as Record<string, unknown>;
    const nested = (o.suite ?? o["bdd"]) as TestScenarioSuite | undefined;
    if (
      nested &&
      typeof nested === "object" &&
      nested.feature &&
      typeof nested.feature.name === "string"
    ) {
      return nested;
    }
    return null;
  } catch {
    return null;
  }
};

interface TestScenarioResultDisplayProps {
  result: string;
  showTitle?: boolean;
  className?: string;
}

function ScenarioAccordionList({ data }: { data: TestScenarioSuite }) {
  return (
    <>
      {data.scenarios.length === 0 ? (
        <p className="rounded-xl border border-dashed border-gray-300/90 bg-gray-50/80 px-4 py-6 text-center text-sm text-gray-600">
          No scenarios were generated: the viewport may lack interactive elements to cover, or
          nothing matched the generation rules. The feature block above still summarizes the visible
          page.
        </p>
      ) : null}
      {data.scenarios.map((sc, index) => (
        <details
          key={`${sc.id}-${index}`}
          className="group overflow-hidden rounded-xl border border-gray-200/90 bg-gray-50/90 shadow-inner"
          open={index === 0}
        >
          <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 border-b border-gray-200/70 bg-white/70 px-4 py-3 [&::-webkit-details-marker]:hidden">
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <p className="text-xs font-medium text-gray-500">{sc.id}</p>
              </div>
              <p className="text-sm font-semibold text-gray-800 wrap-anywhere">
                {sc.title}
              </p>
            </div>
            <span className="text-sm text-gray-400 transition-transform group-open:rotate-180">
              ▾
            </span>
          </summary>
          <pre className="custom-scrollbar max-h-80 overflow-auto px-4 py-3 font-mono text-sm leading-6 text-gray-800 wrap-anywhere whitespace-pre-wrap">
            {sc.test_scenario}
          </pre>
        </details>
      ))}
    </>
  );
}

export function TestScenarioResultDisplay({
  result,
  showTitle = true,
  className = "",
}: TestScenarioResultDisplayProps) {
  const wrapped = parseLegacyWrappedSuite(result);
  const dataFlat = parseTestScenarioSuiteString(result);
  const data = wrapped ?? dataFlat;
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
        <p className="text-sm text-amber-700">
          Could not parse test scenario result.
        </p>
        <pre className="mt-2 max-h-48 overflow-auto rounded border bg-gray-50 p-2 text-xs wrap-anywhere whitespace-pre-wrap">
          {result}
        </pre>
      </div>
    );
  }

  const subtitle = `${data.model} — Test scenarios in the order returned by the model.`;

  return (
    <div className={`card relative overflow-hidden ${className}`}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-linear-to-r from-emerald-100/50 via-teal-100/30 to-transparent" />

      {showTitle && (
        <div className="relative mb-4">
          <h2 className="text-gradient from-emerald-700 to-teal-600 text-2xl font-extrabold">
            Test scenarios
          </h2>
          <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
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
          {(data.feature.business_intent ?? "").trim() ? (
            <div className="mt-3 border-t border-gray-100 pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                Business intent
              </p>
              <p className="mt-1 text-sm text-gray-700 wrap-anywhere">
                {(data.feature.business_intent ?? "").trim()}
              </p>
            </div>
          ) : null}
        </div>

        <div className="space-y-3">
          <ScenarioAccordionList data={data} />
        </div>

        {data.combined_test_scenario ? (
          <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/40 p-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setCombinedOpen((o) => !o)}
                className="text-sm font-semibold text-emerald-800 hover:underline"
              >
                {combinedOpen ? "Hide" : "Show"} combined test scenario
              </button>
              <button
                type="button"
                onClick={() => void onCopy(data.combined_test_scenario)}
                className="rounded-lg border border-emerald-300 bg-white px-3 py-1 text-xs font-semibold text-emerald-800 hover:bg-emerald-50"
              >
                Copy all
              </button>
            </div>
            {combinedOpen ? (
              <pre className="custom-scrollbar max-h-96 overflow-auto rounded-lg border border-emerald-100 bg-white/90 p-3 font-mono text-sm leading-6 text-gray-800 wrap-anywhere whitespace-pre-wrap">
                {data.combined_test_scenario}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function isTestScenarioSuiteJsonString(result: string): boolean {
  try {
    const obj = JSON.parse(result) as unknown;
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
      return false;
    }
    const o = obj as Record<string, unknown>;
    const wrappedNested = (o.suite ?? o["bdd"]) as Record<string, unknown> | undefined;
    if (wrappedNested && o.vision) {
      const feature = wrappedNested.feature;
      if (!feature || typeof feature !== "object" || feature === null) {
        return false;
      }
      const name = (feature as Record<string, unknown>).name;
      if (typeof name !== "string" || !name.trim()) {
        return false;
      }
      return true;
    }
    const feature = o.feature;
    if (!feature || typeof feature !== "object" || feature === null) {
      return false;
    }
    const name = (feature as Record<string, unknown>).name;
    if (typeof name !== "string" || !name.trim()) {
      return false;
    }
    const scenarios = o.scenarios;
    if (!Array.isArray(scenarios)) {
      return false;
    }
    if (scenarios.length === 0) {
      return true;
    }
    const first = scenarios[0] as Record<string, unknown> | undefined;
    if (!first || typeof first.test_scenario !== "string") {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}
