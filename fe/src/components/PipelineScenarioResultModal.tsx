import { useEffect, useMemo } from "react";
import type { StateGraphOrganizeResponsePayload } from "../types/stateGraph";
import { stateGraphScreenSrc } from "../utils/stateGraphScreenSrc";
import { ScreenThumbnail } from "./ScreenThumbnail";

function shortenId(id: string, n = 10): string {
  if (id.length <= n) {
    return id;
  }
  return `${id.slice(0, n)}…`;
}

type PipelineScenarioResultModalProps = {
  isOpen: boolean;
  payload: StateGraphOrganizeResponsePayload | null;
  onClose: () => void;
};

export function PipelineScenarioResultModal({
  isOpen,
  payload,
  onClose,
}: PipelineScenarioResultModalProps) {
  const { isolated_scenarios, flow_scenarios } = payload?.final_test_output ?? {
    isolated_scenarios: [],
    flow_scenarios: [],
  };

  const flowNameById = useMemo(() => {
    const m = new Map<string, string>();
    if (!payload) return m;
    for (const f of payload.flows) {
      m.set(f.id, f.name);
    }
    return m;
  }, [payload]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen || !payload) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="pipeline-scenario-result-title"
        className="card-dark flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden p-6 shadow-2xl"
      >
        <div className="mb-4 flex shrink-0 items-start justify-between gap-3">
          <div>
            <h2
              id="pipeline-scenario-result-title"
              className="text-lg font-bold text-zinc-100"
            >
              Test scenarios
            </h2>
            <p className="mt-1 text-xs text-zinc-500">
              By flow (E2E) · By screen image (isolated)
            </p>
          </div>
          <button
            type="button"
            className="rounded-lg border border-zinc-600 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        <div className="grid max-h-[min(72vh,640px)] min-h-[260px] grid-cols-1 gap-6 overflow-hidden lg:grid-cols-2">
          <section className="flex min-h-0 flex-col border-t border-zinc-700/60 pt-4 lg:border-t-0 lg:border-r lg:border-zinc-700/60 lg:pr-4 lg:pt-0">
            <h3 className="mb-3 shrink-0 text-sm font-semibold uppercase tracking-wide text-cyan-400/90">
              By flow
            </h3>
            <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
              {flow_scenarios.map((fs) => {
                const title = flowNameById.get(fs.flow_id) ?? fs.flow_id;
                return (
                  <details
                    key={fs.flow_id}
                    className="rounded-lg border border-zinc-700/60 bg-zinc-900/35"
                    open={false}
                  >
                    <summary className="cursor-pointer list-none px-3 py-2 text-sm font-medium text-zinc-200 [&::-webkit-details-marker]:hidden">
                      <span className="text-zinc-100">{title}</span>
                      <span className="ml-2 font-mono text-xs text-violet-300/90">
                        {shortenId(fs.flow_id, 24)}
                      </span>
                    </summary>
                    <div className="space-y-3 border-t border-zinc-800 px-3 py-3">
                      {fs.scenarios.map((sc, i) => (
                        <div key={`${fs.flow_id}-${i}`} className="space-y-1">
                          <p className="text-xs font-semibold text-zinc-400">{sc.scenario}</p>
                          <pre className="custom-scrollbar overflow-x-auto rounded-md bg-black/40 p-2 font-mono text-xs text-violet-100/90 whitespace-pre-wrap">
                            {sc.gherkin}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </details>
                );
              })}
            </div>
          </section>

          <section className="flex min-h-0 flex-col border-t border-zinc-700/60 pt-4 lg:border-t-0 lg:pt-0">
            <h3 className="mb-3 shrink-0 text-sm font-semibold uppercase tracking-wide text-emerald-400/90">
              By screen image
            </h3>
            <div className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
              {isolated_scenarios.map((block) => (
                <details
                  key={block.image_id}
                  className="rounded-lg border border-zinc-700/60 bg-zinc-900/35"
                  open={false}
                >
                  <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-2 text-sm font-medium text-zinc-200 [&::-webkit-details-marker]:hidden">
                    <ScreenThumbnail
                      src={stateGraphScreenSrc(
                        payload.input_id,
                        block.image_id,
                        payload.screen_images,
                      )}
                      imageId={block.image_id}
                      size="md"
                    />
                    <span className="min-w-0">
                      <span className="font-mono text-cyan-300/90">
                        {shortenId(block.image_id, 16)}
                      </span>
                      <span className="ml-2 text-zinc-500">
                        ({block.scenarios.length} scenario
                        {block.scenarios.length === 1 ? "" : "s"})
                      </span>
                    </span>
                  </summary>
                  <div className="space-y-3 border-t border-zinc-800 px-3 py-3">
                    {block.scenarios.map((sc, i) => (
                      <div key={`${block.image_id}-${i}`} className="space-y-1">
                        <p className="text-xs font-semibold uppercase text-zinc-500">
                          {sc.scenario}
                        </p>
                        <pre className="custom-scrollbar overflow-x-auto rounded-md bg-black/40 p-2 font-mono text-xs text-emerald-100/90 whitespace-pre-wrap">
                          {sc.gherkin}
                        </pre>
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
