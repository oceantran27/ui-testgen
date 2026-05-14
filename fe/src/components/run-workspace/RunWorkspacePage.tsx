import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { Link, useParams } from "react-router-dom";
import {
  FiChevronRight,
  FiLoader,
  FiRefreshCw,
  FiActivity,
  FiCheckCircle,
  FiAlertCircle,
  FiLayout,
  FiMap,
  FiTarget,
  FiFileText,
  FiShield,
  FiImage,
} from "react-icons/fi";
import { toast } from "react-hot-toast";
import { AppShell } from "../layout/AppShell";
import { apiAbsoluteUrl } from "../../api/client";
import {
  cancelRun,
  getArtifacts,
  getCanonicalStates,
  getFlowDetail,
  getModelConfig,
  getResearchOutput,
  getRunPipelineLog,
  getScenarioDetail,
  getScenarioValidation,
  getUIState,
  listBehaviourIntents,
  listFlows,
  listModelCalls,
  listRunImages,
  listScenarios,
  listUIStates,
} from "../../api/runs";
import { extractApiError } from "../../utils/errors";
import type {
  BehaviourIntentSummary,
  FlowDetailResponse,
  FlowSummary,
  ImageRecord,
  ModelConfigResponse,
  PipelineLogResponse,
  ScenarioDetailResponse,
  ScenarioSummary,
  UIStateDetailResponse,
  UIStateSummary,
  SemanticCanonicalizationResult,
  ScenarioValidationResult,
  IntentReadiness,
} from "../../types/run";
import { useRunPolling } from "../../hooks/useRunPolling";
import { PipelineStrip } from "./PipelineStrip";
import { RunProgressModal } from "../runs/RunProgressModal";
import type { PipelineHints } from "../../utils/pipelineUi";

function formatElementText(text: string[] | string | null | undefined): string {
  if (text == null) return "—";
  if (Array.isArray(text)) return text.filter(Boolean).join(" ") || "—";
  return String(text) || "—";
}

function normalizeTransitionTrigger(raw: unknown): {
  action_type: string;
  text: string[];
} {
  if (!raw || typeof raw !== "object") {
    return { action_type: "", text: [] };
  }
  const t = raw as Record<string, unknown>;
  if (typeof t.action_type === "string" && Array.isArray(t.text)) {
    return { action_type: t.action_type, text: t.text as string[] };
  }
  const actionType = String(t.action_type ?? "");
  const label = String(t.action_label ?? "");
  const te = t.trigger_text != null ? String(t.trigger_text) : "";
  const combined = [label, te].filter(Boolean);
  return {
    action_type: actionType,
    text:
      combined.length > 0
        ? combined
        : label
          ? [label]
          : actionType
            ? [actionType]
            : [],
  };
}

function normalizeTransitionBasis(raw: unknown): string[] {
  if (Array.isArray(raw)) {
    return raw.map(String);
  }
  if (typeof raw === "string" && raw.trim()) {
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

function defaultIntentReadiness(): IntentReadiness {
  return {
    readiness_level: "unknown",
    reason: "",
    usable_for_primary_scenario: false,
  };
}

function normalizeFlowRow(raw: Record<string, unknown>): FlowSummary {
  const idsRaw = raw.state_ids ?? raw.ordered_state_ids;
  const ids = Array.isArray(idsRaw) ? (idsRaw as string[]) : [];
  const termRaw = raw.terminal_state_ids;
  let terminals: string[] = [];
  if (Array.isArray(termRaw)) {
    terminals = termRaw as string[];
  } else if (
    termRaw &&
    typeof termRaw === "object" &&
    Array.isArray((termRaw as { ids?: string[] }).ids)
  ) {
    terminals = (termRaw as { ids: string[] }).ids;
  }
  const ir =
    raw.intent_readiness && typeof raw.intent_readiness === "object"
      ? (raw.intent_readiness as IntentReadiness)
      : defaultIntentReadiness();
  return {
    flow_id: String(raw.flow_id),
    flow_label: String(raw.flow_label ?? raw.name ?? raw.flow_id),
    flow_type: String(raw.flow_type),
    entry_state_id: (raw.entry_state_id ?? raw.start_state_id ?? null) as string | null,
    state_ids: ids,
    terminal_state_ids: terminals,
    state_sequence: Array.isArray(raw.state_sequence)
      ? (raw.state_sequence as FlowSummary["state_sequence"])
      : undefined,
    flow_completeness:
      raw.flow_completeness && typeof raw.flow_completeness === "object"
        ? (raw.flow_completeness as Record<string, boolean>)
        : undefined,
    intent_readiness: ir,
    flow_evidence_package:
      raw.flow_evidence_package && typeof raw.flow_evidence_package === "object"
        ? (raw.flow_evidence_package as FlowSummary["flow_evidence_package"])
        : undefined,
  };
}

function normalizeScenarioRow(raw: Record<string, unknown>): ScenarioSummary {
  const confRaw = raw.confidence;
  let confidence: number | null = null;
  if (typeof confRaw === "number" && !Number.isNaN(confRaw)) {
    confidence = confRaw;
  } else if (confRaw != null && confRaw !== "") {
    const n = Number(confRaw);
    confidence = Number.isNaN(n) ? null : n;
  }
  return {
    scenario_id: String(raw.scenario_id),
    title: String(raw.title ?? ""),
    scenario_type: String(raw.scenario_type ?? raw.type ?? ""),
    status: String(raw.status),
    validation_status: (raw.validation_status ?? null) as string | null,
    confidence,
    confidence_label: (raw.confidence_label ?? null) as string | null,
    grounding_mode: (raw.grounding_mode ?? null) as string | null,
  };
}

function normalizeFlowDetailPayload(raw: Record<string, unknown>): FlowDetailResponse {
  const base = normalizeFlowRow(raw);
  const trans = Array.isArray(raw.transitions) ? raw.transitions : [];
  return {
    ...base,
    transitions: trans.map((t: Record<string, unknown>) => ({
      transition_id: String(t.transition_id),
      from_state_id: String(t.from_state_id),
      to_state_id: String(t.to_state_id),
      transition_type: String(t.transition_type ?? ""),
      trigger: normalizeTransitionTrigger(t.trigger),
      target_state_evidence:
        t.target_state_evidence && typeof t.target_state_evidence === "object"
          ? (t.target_state_evidence as FlowDetailResponse["transitions"][number]["target_state_evidence"])
          : null,
      transition_basis: normalizeTransitionBasis(t.transition_basis),
      ordering_strength: String(t.ordering_strength ?? "medium"),
      transition_certainty:
        t.transition_certainty != null ? String(t.transition_certainty) : null,
      uncertainty_reason: (t.uncertainty_reason ?? null) as string | null,
      reason: (t.reason ?? null) as string | null,
      confidence_label: (t.confidence_label ?? null) as string | null,
      score: typeof t.score === "number" ? t.score : null,
    })),
  };
}

type TabId =
  | "overview"
  | "images"
  | "states"
  | "canonical"
  | "flows"
  | "intents"
  | "scenarios"
  | "validation"
  | "models"
  | "artifacts"
  | "log";

const TABS: { id: TabId; label: string; icon?: ComponentType<{ className?: string }> }[] = [
  { id: "overview", label: "Overview" },
  { id: "images", label: "Images", icon: FiImage },
  { id: "states", label: "States", icon: FiLayout },
  { id: "canonical", label: "Canonical", icon: FiTarget },
  { id: "flows", label: "Flows", icon: FiMap },
  { id: "intents", label: "Intents", icon: FiTarget },
  { id: "scenarios", label: "Scenarios", icon: FiFileText },
  { id: "validation", label: "Validation", icon: FiShield },
  { id: "models", label: "Model calls" },
  { id: "artifacts", label: "Artifacts" },
  { id: "log", label: "Log" },
];

export function RunWorkspacePage() {
  const { runId = "" } = useParams<{ runId: string }>();
  const decodedId = decodeURIComponent(runId);

  const { run, graphStatus, refresh, isTerminal } = useRunPolling(decodedId, {
    enabled: !!decodedId,
    intervalMs: 1500,
  });

  const [tab, setTab] = useState<TabId>("overview");
  const [progressOpen, setProgressOpen] = useState(false);

  const handleCancelRun = async () => {
    if (!run) return;
    if (!window.confirm("Cancel this run?")) return;
    try {
      await cancelRun(run.run_id);
      toast.success("Run cancellation requested.");
      void refresh();
    } catch (e) {
      toast.error(extractApiError(e));
    }
  };

  const isCancellable =
    run && ["created", "uploading", "uploaded", "queued"].includes(run.status);
  const [hints, setHints] = useState<PipelineHints>({
    uiStateCount: 0,
    flowCount: 0,
    scenarioCount: 0,
  });

  const [images, setImages] = useState<ImageRecord[] | null>(null);
  const [states, setStates] = useState<UIStateSummary[] | null>(null);
  const [stateDetail, setStateDetail] = useState<UIStateDetailResponse | null>(
    null,
  );
  const [canonicalResult, setCanonicalResult] = useState<SemanticCanonicalizationResult | null>(null);
  const [flows, setFlows] = useState<FlowSummary[] | null>(null);
  const [flowDetail, setFlowDetail] = useState<FlowDetailResponse | null>(
    null,
  );
  const [intents, setIntents] = useState<BehaviourIntentSummary[] | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSummary[] | null>(null);
  const [scenarioDetail, setScenarioDetail] =
    useState<ScenarioDetailResponse | null>(null);
  const [validationResult, setValidationResult] = useState<ScenarioValidationResult | null>(null);
  
  const [modelCalls, setModelCalls] = useState<
    Awaited<ReturnType<typeof listModelCalls>> | null
  >(null);
  const [modelConfig, setModelConfig] = useState<ModelConfigResponse | null>(
    null,
  );
  const [validationAuditOpenId, setValidationAuditOpenId] = useState<
    string | null
  >(null);
  const [artifacts, setArtifacts] = useState<
    Awaited<ReturnType<typeof getArtifacts>> | null
  >(null);
  const [finalPackage, setFinalPackage] = useState<ScenarioValidationResult | null>(null);
  
  const [pipelineLog, setPipelineLog] = useState<PipelineLogResponse | null>(
    null,
  );
  const [logAutoScroll, setLogAutoScroll] = useState(true);
  const [tabLoading, setTabLoading] = useState(false);
  const logByteOffsetRef = useRef(0);
  const logSessionPathRef = useRef<string | null>(null);
  const logPreRef = useRef<HTMLPreElement | null>(null);

  const thumb = useCallback(
    (imageId: string) =>
      apiAbsoluteUrl(
        `runs/${encodeURIComponent(decodedId)}/images/${encodeURIComponent(imageId)}/thumbnail`,
      ),
    [decodedId],
  );

  useEffect(() => {
    if (!decodedId) {
      return;
    }
    let cancelled = false;
    const loadHints = async () => {
      try {
        const [st, fl, sc] = await Promise.all([
          listUIStates(decodedId),
          listFlows(decodedId),
          listScenarios(decodedId),
        ]);
        if (cancelled) {
          return;
        }
        setHints({
          uiStateCount: st.total,
          flowCount: fl.total,
          scenarioCount: sc.total,
        });
      } catch {
        /* ignore */
      }
    };
    void loadHints();
    const id = window.setInterval(loadHints, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [decodedId, run?.status]);

  useEffect(() => {
    if (tab !== "log" || !decodedId) {
      return;
    }
    let cancelled = false;
    logByteOffsetRef.current = 0;
    logSessionPathRef.current = null;
    setPipelineLog(null);

    const tick = async () => {
      if (cancelled) {
        return;
      }
      try {
        const from = logByteOffsetRef.current;
        const data = await getRunPipelineLog(decodedId, { from_byte: from });
        if (cancelled) {
          return;
        }

        if (
          data.path &&
          logSessionPathRef.current &&
          data.path !== logSessionPathRef.current
        ) {
          logByteOffsetRef.current = 0;
          const full = await getRunPipelineLog(decodedId, { from_byte: 0 });
          if (cancelled) {
            return;
          }
          setPipelineLog(full);
          logByteOffsetRef.current = full.next_byte ?? 0;
          logSessionPathRef.current = full.path ?? null;
          return;
        }

        logSessionPathRef.current = data.path ?? logSessionPathRef.current;

        if (from === 0) {
          setPipelineLog(data);
          logByteOffsetRef.current = data.next_byte ?? 0;
        } else {
          logByteOffsetRef.current = data.next_byte ?? logByteOffsetRef.current;
          setPipelineLog((prev) => {
            if (!prev) {
              return data;
            }
            return {
              ...data,
              content: (prev.content ?? "") + (data.content ?? ""),
              message: data.message ?? prev.message,
              path: data.path ?? prev.path,
              next_byte: data.next_byte,
            };
          });
        }
      } catch (e) {
        toast.error(extractApiError(e));
      }
    };

    void tick();
    const timer = window.setInterval(() => void tick(), 1800);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [tab, decodedId]);

  useEffect(() => {
    if (!logAutoScroll || tab !== "log") {
      return;
    }
    const el = logPreRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [pipelineLog?.content, tab, logAutoScroll]);

  const loadTab = useCallback(async () => {
    if (!decodedId) {
      return;
    }
    if (tab === "log") {
      return;
    }
    setTabLoading(true);
    try {
      if (tab === "images") {
        const res = await listRunImages(decodedId);
        setImages(res.images);
      } else if (tab === "states") {
        const res = await listUIStates(decodedId);
        setStates(res.states);
      } else if (tab === "canonical") {
        try {
          const raw = await getCanonicalStates(decodedId);
          if (
            raw &&
            typeof raw === "object" &&
            "unique_states" in raw &&
            Array.isArray((raw as SemanticCanonicalizationResult).unique_states)
          ) {
            setCanonicalResult(raw as SemanticCanonicalizationResult);
          } else {
            setCanonicalResult(null);
          }
        } catch {
          setCanonicalResult(null);
        }
      } else if (tab === "flows") {
        const res = await listFlows(decodedId);
        setFlows(
          res.flows.map((f) =>
            normalizeFlowRow(f as unknown as Record<string, unknown>),
          ),
        );
        setFlowDetail(null);
      } else if (tab === "intents") {
        const res = await listBehaviourIntents(decodedId);
        setIntents(res.intents);
      } else if (tab === "scenarios") {
        const res = await listScenarios(decodedId);
        setScenarios(
          res.scenarios.map((s) =>
            normalizeScenarioRow(s as unknown as Record<string, unknown>),
          ),
        );
        setScenarioDetail(null);
      } else if (tab === "validation") {
        try {
          const raw = await getScenarioValidation(decodedId);
          if (
            raw &&
            typeof raw === "object" &&
            Array.isArray((raw as ScenarioValidationResult).validated_scenarios)
          ) {
            setValidationResult(raw as ScenarioValidationResult);
          } else {
            setValidationResult(null);
          }
        } catch {
          setValidationResult(null);
        }
      } else if (tab === "models") {
        const [calls, cfg] = await Promise.all([
          listModelCalls(decodedId),
          getModelConfig(decodedId),
        ]);
        setModelCalls(calls);
        setModelConfig(cfg);
      } else if (tab === "artifacts") {
        setArtifacts(await getArtifacts(decodedId));
      } else if (tab === "overview") {
        try {
          const ro = await getResearchOutput(decodedId);
          setFinalPackage(ro);
        } catch {
          setFinalPackage(null);
        }
      }
    } catch (e) {
      toast.error(extractApiError(e));
    } finally {
      setTabLoading(false);
    }
  }, [decodedId, tab]);

  useEffect(() => {
    void loadTab();
  }, [loadTab]);

  const openState = async (stateId: string) => {
    try {
      setStateDetail(await getUIState(decodedId, stateId));
    } catch (e) {
      toast.error(extractApiError(e));
    }
  };

  const openFlow = async (flowId: string) => {
    try {
      const raw = await getFlowDetail(decodedId, flowId);
      setFlowDetail(
        normalizeFlowDetailPayload(raw as unknown as Record<string, unknown>),
      );
    } catch (e) {
      toast.error(extractApiError(e));
    }
  };

  const openScenario = async (scenarioId: string) => {
    try {
      setScenarioDetail(await getScenarioDetail(decodedId, scenarioId));
    } catch (e) {
      toast.error(extractApiError(e));
    }
  };

  const subtitle = useMemo(
    () =>
      run?.project_name
        ? `${run.project_name} · 7-Agent Pipeline Workspace`
        : "Run workspace",
    [run?.project_name],
  );

  if (!decodedId) {
    return (
      <AppShell subtitle="Missing run id.">
        <p className="text-zinc-400">Invalid URL.</p>
      </AppShell>
    );
  }

  return (
    <AppShell subtitle={subtitle}>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Link
          to="/"
          className="text-sm font-semibold text-[var(--accent)] hover:underline"
        >
          ← All runs
        </Link>
        <button
          type="button"
          onClick={() => void refresh()}
          className="inline-flex items-center gap-1 rounded-lg border border-zinc-600 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800/80"
        >
          <FiRefreshCw /> Refresh run
        </button>
        <button
          type="button"
          onClick={() => setProgressOpen(true)}
          className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/40 bg-cyan-950/20 px-3 py-1.5 text-sm font-semibold text-cyan-300 hover:bg-cyan-950/35"
        >
          <FiActivity /> Pipeline detail
        </button>
        {isCancellable ? (
          <button
            type="button"
            onClick={() => void handleCancelRun()}
            className="inline-flex items-center gap-1 rounded-lg border border-amber-600/50 px-3 py-1.5 text-sm text-amber-200 hover:bg-amber-950/30"
          >
            Cancel run
          </button>
        ) : null}
        {run ? (
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-zinc-800 px-2.5 py-1 text-xs font-bold uppercase tracking-wider text-zinc-300 border border-zinc-700">
              {run.status}
            </span>
          </div>
        ) : (
          <FiLoader className="animate-spin text-cyan-400" />
        )}
      </div>

      <div className="card-dark mb-6">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-zinc-500">
          Sequential 7-Agent Pipeline
        </h2>
        <PipelineStrip run={run} graphStatus={graphStatus} hints={hints} />
      </div>

      <div className="flex flex-wrap gap-2 border-b border-zinc-800 pb-3">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={
              tab === t.id
                ? "rounded-lg bg-zinc-800 px-3 py-1.5 text-sm font-semibold text-cyan-300 flex items-center gap-2"
                : "rounded-lg px-3 py-1.5 text-sm text-zinc-400 hover:bg-zinc-900/80 hover:text-zinc-200 flex items-center gap-2"
            }
          >
            {t.icon && <t.icon className="w-3.5 h-3.5" />}
            {t.label}
          </button>
        ))}
      </div>

      <div className="card-dark mt-4 min-h-[240px]">
        {tabLoading ? (
          <p className="flex items-center gap-2 text-sm text-zinc-400">
            <FiLoader className="animate-spin" /> Loading Agent Data…
          </p>
        ) : null}

        {tab === "overview" && (
          <div className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Canonical States", value: run?.canonical_images ?? 0 },
                { label: "Discovered Flows", value: hints.flowCount },
                {
                  label: "Validated Scenarios",
                  value:
                    finalPackage?.validated_scenarios?.filter(
                      (s) => s.acceptance_decision.include_in_final_output,
                    ).length ?? 0,
                },
                {
                  label: "Avg Reliability",
                  value:
                    finalPackage?.validated_scenarios?.length
                      ? (
                          finalPackage.validated_scenarios.reduce(
                            (a, b) => a + b.final_reliability,
                            0,
                          ) / finalPackage.validated_scenarios.length
                        ).toFixed(2)
                      : "0.00",
                },
              ].map((m) => (
                <div key={m.label} className="rounded-xl border border-zinc-700/60 bg-zinc-950/50 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{m.label}</p>
                  <p className="text-2xl font-bold text-zinc-100">{m.value}</p>
                </div>
              ))}
            </div>
            {finalPackage && (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-950/10 p-4">
                <p className="text-sm font-semibold text-emerald-300 mb-2">Final Output Summary</p>
                <div className="text-xs text-emerald-400/80 grid grid-cols-2 gap-4">
                   <div>Validated: {finalPackage.final_output_summary?.validated_count ?? 0}</div>
                   <div>Rejected: {finalPackage.final_output_summary?.rejected_count ?? 0}</div>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "images" && images && (
          <ul className="space-y-2">
            {images.map((img) => (
              <li key={img.image_id} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-950/40 p-2">
                <img src={thumb(img.image_id)} alt="" className="h-14 w-14 rounded border border-zinc-700 object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-zinc-200">{img.original_filename}</p>
                  <p className="font-mono text-xs text-zinc-500">{img.image_id}</p>
                </div>
              </li>
            ))}
          </ul>
        )}

        {tab === "states" && states && (
          <div className="grid gap-4 lg:grid-cols-2">
            <ul className="space-y-2">
              {states.map((s) => (
                <li key={s.state_id}>
                  <button type="button" onClick={() => void openState(s.state_id)} className="flex w-full items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-left text-sm hover:border-zinc-600">
                    <span className="truncate text-zinc-200">{s.page_type} · {s.state_summary}</span>
                    <FiChevronRight className="shrink-0 text-zinc-500" />
                  </button>
                </li>
              ))}
            </ul>
            <div className="rounded-lg border border-zinc-700/60 bg-zinc-950/50 p-3">
              {stateDetail ? (
                <div className="space-y-3 text-sm">
                  <img src={thumb(stateDetail.image_id)} alt="" className="max-h-40 rounded border border-zinc-700" />
                  <p className="text-zinc-300">{stateDetail.state_summary}</p>
                  {(() => {
                    const showRoleCol = stateDetail.ui_elements.some(
                      (el) => el.semantic_role,
                    );
                    return (
                  <div className="overflow-hidden rounded border border-zinc-800">
                    <table className="w-full text-left text-[10px]">
                      <thead className="bg-zinc-900 text-zinc-500 uppercase">
                        <tr>
                          <th className="px-2 py-1">Type</th>
                          {showRoleCol ? (
                            <th className="px-2 py-1">Role</th>
                          ) : null}
                          <th className="px-2 py-1">Text</th>
                          <th className="px-2 py-1">Visibility</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800 text-zinc-400">
                        {stateDetail.ui_elements.map((el) => (
                          <tr key={el.element_id} className="hover:bg-zinc-900/40">
                            <td className="px-2 py-1 font-mono">{el.type}</td>
                            {showRoleCol ? (
                              <td className="px-2 py-1">{el.semantic_role || "—"}</td>
                            ) : null}
                            <td className="px-2 py-1 max-w-[140px] truncate" title={formatElementText(el.text)}>
                              {formatElementText(el.text)}
                            </td>
                            <td className="px-2 py-1">{el.visibility ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                    );
                  })()}
                </div>
              ) : <p className="text-zinc-500 text-sm">Select a state to see elements.</p>}
            </div>
          </div>
        )}

        {tab === "canonical" && !tabLoading && (
          canonicalResult == null ? (
            <p className="text-sm text-zinc-500">
              Canonical report is not available yet (pipeline still running, not reached Agent 2, or report missing).
            </p>
          ) : !Array.isArray(canonicalResult.unique_states) || canonicalResult.unique_states.length === 0 ? (
            <p className="text-sm text-zinc-500">No semantic groups in this report.</p>
          ) : (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-zinc-300">Semantic groups (unique_states)</h3>
            <ul className="grid gap-4 sm:grid-cols-2">
              {canonicalResult.unique_states.map((cs) => (
                <li key={cs.canonical_id} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
                  <p className="text-sm font-bold text-zinc-200 mb-1">{cs.data.screen_purpose}</p>
                  <p className="text-xs text-zinc-500 mb-1">
                    <span className="font-mono text-zinc-400">{cs.canonical_id}</span>
                    {" · "}
                    <span className="uppercase">{cs.confidence}</span>
                  </p>
                  <p className="text-xs text-zinc-500 mb-2">
                    Type: {cs.data.screen_type} · Domain: {cs.data.domain}
                  </p>
                  <p className="text-xs text-zinc-500 mb-2">
                    Merged from: {cs.merged_from.length ? cs.merged_from.join(", ") : "(representative only)"}
                  </p>
                </li>
              ))}
            </ul>
          </div>
          )
        )}

        {tab === "flows" && flows && (
          <div className="grid gap-4 lg:grid-cols-2">
            <ul className="space-y-2">
              {flows.map((f) => (
                <li key={f.flow_id}>
                  <button type="button" onClick={() => void openFlow(f.flow_id)} className="flex w-full flex-col gap-1 rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-left text-sm hover:border-zinc-600">
                    <span className="font-medium text-zinc-200">{f.flow_label}</span>
                    <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                      <span>{f.state_ids.length} states</span>
                      <span className="rounded bg-zinc-800 px-1 py-0.5 uppercase">{f.flow_type}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            <div className="rounded-lg border border-zinc-700/60 bg-zinc-950/50 p-4">
              {flowDetail ? (
                <div className="space-y-4 text-sm text-zinc-300">
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-zinc-100 text-lg">{flowDetail.flow_label}</p>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${
                      (flowDetail.intent_readiness ?? defaultIntentReadiness()).readiness_level === 'ready_for_intent' ? 'bg-emerald-950/30 text-emerald-400' : 'bg-amber-950/30 text-amber-400'
                    }`}>
                      {(flowDetail.intent_readiness ?? defaultIntentReadiness()).readiness_level}
                    </span>
                  </div>
                  <p className="text-zinc-400 text-xs italic">{(flowDetail.intent_readiness ?? defaultIntentReadiness()).reason || "—"}</p>

                  <div className="space-y-2">
                    <p className="text-[10px] font-bold uppercase text-zinc-500 tracking-wider">Inferred transitions</p>
                    <ul className="space-y-3">
                      {flowDetail.transitions.map((t) => {
                        const triggerLabel =
                          t.trigger.text?.length > 0
                            ? t.trigger.text.join(" ")
                            : t.trigger.action_type || "—";
                        return (
                        <li key={t.transition_id} className="bg-zinc-900/40 border border-zinc-800/50 rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2 flex-wrap">
                            <span className="bg-zinc-800 px-1.5 py-0.5 rounded font-mono text-[10px]">{t.from_state_id.slice(-6)}</span>
                            <FiChevronRight className="text-zinc-600 shrink-0" />
                            <span className="bg-zinc-800 px-1.5 py-0.5 rounded font-mono text-[10px]">{t.to_state_id.slice(-6)}</span>
                            <div className="ml-auto flex items-center gap-2 shrink-0">
                              <span className="text-cyan-400 font-bold text-[10px] uppercase" title={triggerLabel}>{t.trigger.action_type}</span>
                              <span className={`text-[10px] font-bold px-1.5 rounded uppercase ${
                                t.ordering_strength === 'strong' ? 'text-emerald-400' : t.ordering_strength === 'medium' ? 'text-amber-400' : 'text-zinc-500'
                              }`}>
                                {t.ordering_strength}
                              </span>
                              {t.confidence_label ? (
                                <span className="text-[10px] text-zinc-500">{t.confidence_label}</span>
                              ) : null}
                            </div>
                          </div>
                          <p className="text-[11px] text-zinc-400 mb-1 truncate" title={triggerLabel}>
                            <span className="text-zinc-500">Trigger:</span> {triggerLabel}
                          </p>
                          <p className="text-[11px] text-zinc-300 mb-1">
                            <span className="text-zinc-500">Basis:</span>{" "}
                            {t.transition_basis.length ? t.transition_basis.join(", ") : "—"}
                          </p>
                          {t.reason ? (
                            <p className="text-[10px] text-zinc-500 italic">{t.reason}</p>
                          ) : null}
                          {t.uncertainty_reason ? (
                            <p className="text-[10px] text-amber-500/80 italic">Note: {t.uncertainty_reason}</p>
                          ) : null}
                        </li>
                      ); })}
                    </ul>
                  </div>
                </div>
              ) : <p className="text-zinc-500 text-sm">Select a flow to see transitions and evidence.</p>}
            </div>
          </div>
        )}

        {tab === "intents" && intents && (
          <div className="grid gap-4 lg:grid-cols-2">
            {intents.map((i) => (
              <div key={i.intent_id} className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-4 text-sm">
                <div className="flex justify-between items-start mb-2 gap-2">
                  <p className="font-bold text-zinc-200">{i.behaviour_name}</p>
                  <span className={`shrink-0 text-[10px] font-bold px-2 py-0.5 rounded uppercase ${
                    i.confidence === 'high' ? 'bg-emerald-950/30 text-emerald-400' : i.confidence === 'medium' ? 'bg-amber-950/30 text-amber-400' : 'bg-zinc-800 text-zinc-400'
                  }`}>
                    {i.confidence}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 mb-2">{i.user_intent}</p>
                <p className="text-xs text-zinc-500 mb-3 italic">{i.business_goal}</p>
                <div className="flex flex-wrap gap-2 mb-3">
                   <span className="bg-zinc-900 px-2 py-0.5 rounded text-[10px] text-zinc-400 uppercase font-bold">{i.intent_type}</span>
                   <span className="bg-zinc-900 px-2 py-0.5 rounded text-[10px] text-zinc-400 uppercase font-bold">{i.test_path}</span>
                </div>
                <p className="text-[10px] font-mono text-zinc-500">
                  {i.start_state.slice(-8)} → {i.end_state.slice(-8)}
                </p>
              </div>
            ))}
          </div>
        )}

        {tab === "scenarios" && scenarios && (
          <div className="grid gap-4 lg:grid-cols-2">
            <ul className="space-y-2">
              {scenarios.map((s) => (
                <li key={s.scenario_id}>
                  <button type="button" onClick={() => void openScenario(s.scenario_id)} className="flex w-full items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-left text-sm hover:border-zinc-600">
                    <span className="truncate text-zinc-200">{s.title}</span>
                    <span className="text-[10px] text-zinc-500 uppercase font-bold">{s.scenario_type}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="rounded-lg border border-zinc-700/60 bg-zinc-950/50 p-3 overflow-hidden">
               {scenarioDetail ? (
                 <div className="space-y-4">
                    <h4 className="font-bold text-zinc-200">{scenarioDetail.scenario_title}</h4>
                    <pre className="text-[10px] text-cyan-200/70 whitespace-pre-wrap font-mono bg-black/40 p-3 rounded leading-relaxed">
                      {scenarioDetail.gherkin_text}
                    </pre>
                    {scenarioDetail.bdd_steps?.length ? (
                      <div>
                        <p className="text-[10px] font-bold uppercase text-zinc-500 mb-2">BDD steps</p>
                        <div className="overflow-x-auto rounded border border-zinc-800">
                          <table className="w-full text-left text-[10px]">
                            <thead className="bg-zinc-900 text-zinc-500 uppercase">
                              <tr>
                                <th className="px-2 py-1">#</th>
                                <th className="px-2 py-1">Kw</th>
                                <th className="px-2 py-1">Text</th>
                                <th className="px-2 py-1">Source</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-800 text-zinc-400">
                              {scenarioDetail.bdd_steps.map((step, idx) => (
                                <tr key={`${step.step_number}-${idx}`}>
                                  <td className="px-2 py-1 font-mono">{step.step_number}</td>
                                  <td className="px-2 py-1">{step.keyword}</td>
                                  <td className="px-2 py-1">{step.text}</td>
                                  <td className="px-2 py-1 text-zinc-500">{step.source}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}
                    {scenarioDetail.validation?.scores ? (
                      <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2 text-[10px] text-zinc-400">
                        <p className="font-bold text-zinc-500 uppercase mb-1">Validation scores</p>
                        <div className="grid grid-cols-2 gap-1 sm:grid-cols-3">
                          <span>G: {Number(scenarioDetail.validation.scores.grounding_score).toFixed(2)}</span>
                          <span>E: {Number(scenarioDetail.validation.scores.evidence_coverage_score).toFixed(2)}</span>
                          <span>BDD: {Number(scenarioDetail.validation.scores.bdd_structure_score).toFixed(2)}</span>
                        </div>
                      </div>
                    ) : null}
                 </div>
               ) : <p className="text-zinc-500 text-sm">Select a scenario.</p>}
            </div>
          </div>
        )}

        {tab === "validation" && !tabLoading && (
          validationResult == null || !Array.isArray(validationResult.validated_scenarios) ? (
            <p className="text-sm text-zinc-500">
              Scenario validation report is not available yet.
            </p>
          ) : validationResult.validated_scenarios.length === 0 ? (
            <p className="text-sm text-zinc-500">No validated scenarios in this report.</p>
          ) : (
           <div className="space-y-4">
              {validationResult.validated_scenarios.map((vs) => {
                const decision = vs.acceptance_decision ?? { reason: "", include_in_final_output: false };
                const sc = vs.scores;
                const hf = vs.hallucination_flags ?? {};
                const hfEntries = Object.entries(hf).filter(([, v]) => v === true);
                const auditsOpen = validationAuditOpenId === vs.scenario_id;
                const audits = vs.step_audits ?? [];
                return (
                <div key={vs.scenario_id} className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 space-y-3">
                  <div className="flex flex-wrap items-start gap-4">
                   <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-zinc-200 truncate">
                        {vs.scenario_name ?? vs.scenario_id}
                      </p>
                      <p className="text-[10px] font-mono text-zinc-500 mt-0.5">{vs.scenario_id}</p>
                      <p className="text-xs text-zinc-500 mt-2">{decision.reason}</p>
                      {vs.validation_warnings?.length ? (
                        <ul className="mt-2 text-[10px] text-amber-500/90 list-disc pl-4">
                          {vs.validation_warnings.map((w, wi) => (
                            <li key={wi}>{w}</li>
                          ))}
                        </ul>
                      ) : null}
                   </div>
                   <div className="text-right shrink-0">
                      <p className="text-lg font-bold text-cyan-400">{((vs.final_reliability ?? 0) * 100).toFixed(0)}%</p>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${vs.validation_status === 'validated' ? 'bg-emerald-950/30 text-emerald-400' : 'bg-amber-950/30 text-amber-400'}`}>
                        {(vs.validation_status ?? 'unknown').toUpperCase()}
                      </span>
                   </div>
                   {decision.include_in_final_output ? <FiCheckCircle className="text-emerald-500 w-5 h-5 shrink-0" /> : <FiAlertCircle className="text-amber-500 w-5 h-5 shrink-0" />}
                  </div>
                  {sc ? (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-zinc-400 border-t border-zinc-800/80 pt-3">
                      <span>Grounding: {Number(sc.grounding_score).toFixed(2)}</span>
                      <span>Evidence: {Number(sc.evidence_coverage_score).toFixed(2)}</span>
                      <span>BDD: {Number(sc.bdd_structure_score).toFixed(2)}</span>
                      <span>Penalty: {Number(sc.hallucination_penalty).toFixed(2)}</span>
                    </div>
                  ) : null}
                  {hfEntries.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {hfEntries.map(([k]) => (
                        <span key={k} className="rounded bg-red-950/40 px-1.5 py-0.5 text-[9px] font-bold uppercase text-red-300 border border-red-900/50">
                          {k.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {audits.length > 0 ? (
                    <div>
                      <button
                        type="button"
                        className="text-[10px] font-semibold text-cyan-400 hover:underline"
                        onClick={() =>
                          setValidationAuditOpenId(auditsOpen ? null : vs.scenario_id)
                        }
                      >
                        {auditsOpen ? "Hide step audits" : "View step audits"}
                      </button>
                      {auditsOpen ? (
                        <ul className="mt-2 space-y-2 max-h-48 overflow-y-auto text-[10px]">
                          {audits.map((a) => (
                            <li key={a.step_number} className="rounded border border-zinc-800 bg-black/30 p-2">
                              <span className="font-mono text-zinc-500">#{a.step_number}</span>
                              {" "}
                              <span className="text-zinc-300">{a.keyword}</span>
                              <span className="ml-2 text-amber-400/90">{a.step_support_status}</span>
                              <p className="text-zinc-500 mt-1">{a.audit_reason}</p>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
              })}
           </div>
          )
        )}

        {tab === "artifacts" && artifacts && (
          <ul className="space-y-2">
            {artifacts.artifacts.map((a) => (
              <li
                key={a.artifact_id}
                className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-xs text-zinc-300"
              >
                <span className="font-mono text-zinc-500">{a.type}</span>
                {a.node_name ? (
                  <span className="ml-2 text-zinc-500">· {a.node_name}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {tab === "models" && (
          <div className="space-y-6">
            {modelConfig?.pipeline_phase_models &&
            Object.keys(modelConfig.pipeline_phase_models).length > 0 ? (
              <div>
                <h3 className="text-xs font-bold uppercase text-zinc-500 mb-2">
                  Pipeline phase models
                </h3>
                <ul className="grid gap-2 sm:grid-cols-2">
                  {Object.entries(modelConfig.pipeline_phase_models).map(
                    ([phase, cfg]) =>
                      cfg ? (
                        <li
                          key={phase}
                          className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-xs"
                        >
                          <p className="font-mono text-zinc-400 mb-1">{phase}</p>
                          <p className="text-zinc-200">
                            <span className="text-cyan-500/80">{cfg.provider}</span>
                            {" · "}
                            <span className="font-mono text-zinc-300">{cfg.model}</span>
                          </p>
                        </li>
                      ) : null,
                  )}
                </ul>
              </div>
            ) : null}
            {modelCalls ? (
              <div>
                <h3 className="text-xs font-bold uppercase text-zinc-500 mb-2">
                  Model calls
                </h3>
                <ul className="space-y-2">
                  {modelCalls.model_calls.map((c) => (
                    <li
                      key={c.model_call_id}
                      className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-zinc-300">
                          {c.node_name} · {c.task_name}
                        </span>
                        <span className="text-zinc-500">
                          {c.latency_ms}ms · {c.status}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-sm text-zinc-500">No model calls loaded.</p>
            )}
          </div>
        )}

        {tab === "log" && (
          <div className="flex flex-col h-[500px]">
            <div className="mb-2 flex items-center justify-between px-1">
               <span className="text-xs text-zinc-500 font-mono">Stream: {pipelineLog?.path || 'waiting...'}</span>
               <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
                  <input type="checkbox" checked={logAutoScroll} onChange={e => setLogAutoScroll(e.target.checked)} className="rounded border-zinc-700 bg-zinc-900 text-cyan-500" />
                  Auto-scroll
               </label>
            </div>
            <pre ref={logPreRef} className="flex-1 overflow-auto bg-black/60 p-4 rounded-lg font-mono text-[10px] text-zinc-400 border border-zinc-800 custom-scrollbar leading-relaxed">
               {pipelineLog?.content || 'Pipeline session logs will appear here...'}
               {pipelineLog?.message && <div className="mt-4 p-2 bg-zinc-900 border border-zinc-800 text-zinc-500 italic">{pipelineLog.message}</div>}
            </pre>
          </div>
        )}
      </div>

      <RunProgressModal
        isOpen={progressOpen}
        run={run}
        graphStatus={graphStatus}
        hints={hints}
        onClose={() => setProgressOpen(false)}
        lockWhileBusy={!isTerminal}
      />
    </AppShell>
  );
}
