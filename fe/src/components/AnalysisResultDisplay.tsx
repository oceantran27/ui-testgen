import {
  TestScenarioResultDisplay,
  isTestScenarioSuiteJsonString,
} from "./TestScenarioResultDisplay";

interface AnalysisResultDisplayProps {
  result: string;
  showTitle?: boolean;
  className?: string;
}

interface ScenarioDisplayItem {
  scenarioId: string;
  userGoal: string;
  conflictResolutionSummary: string;
  baScore: number | null;
  qaScore: number | null;
  uxScore: number | null;
  finalScore: number | null;
  rankPosition: number | null;
}

const asRecord = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
};

const toNumberOrNull = (value: unknown): number | null => {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

const normalizeScenarioItem = (
  raw: unknown,
  index: number,
): ScenarioDisplayItem | null => {
  const record = asRecord(raw);
  if (!record) {
    return null;
  }

  const scenarioIdRaw = record.scenario_id ?? record.id;
  const userGoalRaw = record.user_goal;
  const summaryRaw = record.conflict_resolution_summary;

  const scenarioId =
    typeof scenarioIdRaw === "string" && scenarioIdRaw.trim()
      ? scenarioIdRaw
      : `SCENARIO_${index + 1}`;
  const userGoal =
    typeof userGoalRaw === "string" && userGoalRaw.trim() ? userGoalRaw : "N/A";
  const conflictResolutionSummary =
    typeof summaryRaw === "string" && summaryRaw.trim()
      ? summaryRaw
      : "No conflict resolution summary provided.";

  return {
    scenarioId,
    userGoal,
    conflictResolutionSummary,
    baScore: toNumberOrNull(record.BA_score ?? record.ba_score),
    qaScore: toNumberOrNull(record.QA_score ?? record.qa_score),
    uxScore: toNumberOrNull(record.UX_score ?? record.ux_score),
    finalScore: toNumberOrNull(record.final_score),
    rankPosition: toNumberOrNull(record.rank_position),
  };
};

const extractScenarioItems = (payload: unknown): ScenarioDisplayItem[] => {
  if (Array.isArray(payload)) {
    return payload
      .map((item, index) => normalizeScenarioItem(item, index))
      .filter((item): item is ScenarioDisplayItem => Boolean(item));
  }

  const root = asRecord(payload);
  if (!root) {
    return [];
  }

  const rankedScenarios = root.ranked_scenarios;
  if (Array.isArray(rankedScenarios)) {
    return rankedScenarios
      .map((item, index) => normalizeScenarioItem(item, index))
      .filter((item): item is ScenarioDisplayItem => Boolean(item));
  }

  if (Array.isArray(root.scenarios)) {
    return root.scenarios
      .map((item, index) => normalizeScenarioItem(item, index))
      .filter((item): item is ScenarioDisplayItem => Boolean(item));
  }

  const extraction = asRecord(root.extraction_result);
  if (extraction && Array.isArray(extraction.scenarios)) {
    return extraction.scenarios
      .map((item, index) => normalizeScenarioItem(item, index))
      .filter((item): item is ScenarioDisplayItem => Boolean(item));
  }

  return [];
};

export function AnalysisResultDisplay({
  result,
  showTitle = true,
  className = "",
}: AnalysisResultDisplayProps) {
  if (!result) {
    return null;
  }

  if (isTestScenarioSuiteJsonString(result)) {
    return (
      <TestScenarioResultDisplay
        result={result}
        showTitle={showTitle}
        className={className}
      />
    );
  }

  let displayContent = result;
  let isJson = false;
  let scenarios: ScenarioDisplayItem[] = [];
  try {
    const jsonObj = JSON.parse(result);
    displayContent = JSON.stringify(jsonObj, null, 2);
    isJson = true;
    scenarios = extractScenarioItems(jsonObj);
  } catch {
    // Keep plain text output when the response is not valid JSON.
  }

  return (
    <div className={`card relative overflow-hidden ${className}`}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-linear-to-r from-blue-100/40 via-indigo-100/30 to-transparent" />

      {showTitle && (
        <div className="relative mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-gradient from-blue-700 to-indigo-600 text-2xl font-extrabold">
            Analysis Result
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold tracking-wide ${
                isJson
                  ? "border-blue-200 bg-blue-50 text-blue-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}
            >
              {isJson ? "JSON formatted" : "Plain text"}
            </span>
            {scenarios.length > 0 && (
              <span className="inline-flex items-center rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold tracking-wide text-indigo-700">
                {scenarios.length} scenario{scenarios.length > 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
      )}

      {scenarios.length > 0 ? (
        <div className="custom-scrollbar relative max-h-112 space-y-3 overflow-y-auto pr-1">
          {scenarios.map((scenario, index) => (
            <details
              key={`${scenario.scenarioId}-${index}`}
              className="group overflow-hidden rounded-xl border border-gray-200/90 bg-gray-50/90 shadow-inner"
              open={index === 0}
            >
              <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 border-b border-gray-200/70 bg-white/70 px-4 py-3 [&::-webkit-details-marker]:hidden">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-800 wrap-anywhere">
                    {scenario.scenarioId}
                  </p>
                  <p className="mt-1 text-xs text-gray-500 wrap-anywhere">
                    {scenario.userGoal}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {scenario.finalScore !== null && (
                    <span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700">
                      Score: {scenario.finalScore}
                    </span>
                  )}
                  {scenario.rankPosition !== null && (
                    <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-semibold text-indigo-700">
                      Rank #{scenario.rankPosition}
                    </span>
                  )}
                  <span className="text-sm text-gray-400 transition-transform group-open:rotate-180">
                    ▾
                  </span>
                </div>
              </summary>

              <div className="space-y-3 px-4 py-3 text-sm">
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    User Goal
                  </p>
                  <p className="text-gray-800 wrap-anywhere">
                    {scenario.userGoal}
                  </p>
                </div>

                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Conflict Resolution Summary
                  </p>
                  <p className="text-gray-700 whitespace-pre-wrap wrap-anywhere">
                    {scenario.conflictResolutionSummary}
                  </p>
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Component Scores
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                      Business (BA): {scenario.baScore ?? "N/A"}
                    </span>
                    <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
                      Security (QA): {scenario.qaScore ?? "N/A"}
                    </span>
                    <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700">
                      UX: {scenario.uxScore ?? "N/A"}
                    </span>
                  </div>
                </div>
              </div>
            </details>
          ))}
        </div>
      ) : (
        <pre className="custom-scrollbar relative max-h-112 overflow-y-auto overflow-x-hidden rounded-xl border border-gray-200/80 bg-gray-50/90 p-4 font-mono text-sm leading-6 text-gray-800 whitespace-pre-wrap wrap-anywhere shadow-inner">
          {displayContent}
        </pre>
      )}
    </div>
  );
}
