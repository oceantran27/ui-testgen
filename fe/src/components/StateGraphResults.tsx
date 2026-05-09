import type { StateGraphOrganizeResponsePayload } from "../types/stateGraph";
import { formatMillis } from "../utils/formatMillis";
import { stateGraphScreenSrc } from "../utils/stateGraphScreenSrc";
import { ScreenThumbnail } from "./ScreenThumbnail";

type StateGraphResultsProps = {
  payload: StateGraphOrganizeResponsePayload;
  className?: string;
};

function shortenId(id: string, n = 10): string {
  if (id.length <= n) {
    return id;
  }
  return `${id.slice(0, n)}…`;
}

export function StateGraphResults({
  payload,
  className = "",
}: StateGraphResultsProps) {
  const { isolated_scenarios, flow_scenarios } = payload.final_test_output;
  const timing = payload.pipeline_timing;

  return (
    <div className={`card-dark space-y-8 ${className}`}>
      <div>
        <h2 className="text-xl font-bold text-zinc-100">Flows</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Inferred user journeys ({payload.flows.length} flow
          {payload.flows.length === 1 ? "" : "s"}).
        </p>
        <ul className="mt-4 space-y-4">
          {payload.flows.map((flow) => (
            <li
              key={flow.id}
              className="rounded-xl border border-zinc-700/60 bg-zinc-900/40 p-4"
            >
              <p className="font-semibold text-cyan-300">{flow.name}</p>
              <p className="mt-2 text-xs text-zinc-500">Screens in flow order</p>
              <div className="mt-2 flex flex-wrap gap-4">
                {flow.nodes.map((nid, idx) => (
                  <div
                    key={`${flow.id}-${nid}-${idx}`}
                    className="flex flex-col items-center gap-1"
                  >
                    <ScreenThumbnail
                      src={stateGraphScreenSrc(
                        payload.input_id,
                        nid,
                        payload.screen_images,
                      )}
                      imageId={nid}
                    />
                    <span className="font-mono text-[10px] tabular-nums text-zinc-500">
                      {idx + 1}
                    </span>
                  </div>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {timing ? (
        <div className="rounded-xl border border-zinc-700/60 bg-zinc-950/60 p-4">
          <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-500">
            Pipeline timing
          </h3>
          <ul className="mt-2 space-y-1 text-sm">
            {timing.phases.map((p) => (
              <li key={p.phase_id} className="flex justify-between text-zinc-300">
                <span className="text-zinc-400">{p.label}</span>
                <span className="font-mono">{formatMillis(p.duration_ms)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 border-t border-zinc-700/50 pt-2 text-sm font-semibold text-zinc-100">
            Total{" "}
            <span className="float-right font-mono">
              {formatMillis(timing.wall_clock_ms)}
            </span>
          </p>
        </div>
      ) : null}

      <div>
        <h2 className="text-xl font-bold text-zinc-100">Per-screen scenarios</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Isolated Gherkin keyed by canonical screen id ({isolated_scenarios.length}{" "}
          screen{isolated_scenarios.length === 1 ? "" : "s"}).
        </p>
        <div className="custom-scrollbar mt-4 max-h-96 space-y-2 overflow-y-auto">
          {isolated_scenarios.map((block) => (
            <details
              key={block.image_id}
              className="group rounded-lg border border-zinc-700/60 bg-zinc-900/35"
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
      </div>

      <div>
        <h2 className="text-xl font-bold text-zinc-100">
          E2E flow scenarios <span className="text-zinc-500">(Actor–Critic)</span>
        </h2>
        <div className="custom-scrollbar mt-4 max-h-96 space-y-3 overflow-y-auto">
          {flow_scenarios.map((fs) => (
            <details
              key={fs.flow_id}
              className="rounded-lg border border-zinc-700/60 bg-zinc-900/35"
              open={false}
            >
              <summary className="cursor-pointer list-none px-3 py-2 text-sm font-medium text-zinc-200 [&::-webkit-details-marker]:hidden">
                Flow <span className="font-mono text-violet-300">{fs.flow_id}</span>
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
          ))}
        </div>
      </div>

      <details className="rounded-lg border border-zinc-700/50 bg-black/25">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-zinc-400">
          Raw JSON response
        </summary>
        <pre className="custom-scrollbar max-h-80 overflow-auto p-3 font-mono text-xs text-zinc-300">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </details>
    </div>
  );
}
