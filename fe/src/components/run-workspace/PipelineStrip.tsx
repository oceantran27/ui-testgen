import type { GraphStatusResponse } from "../../types/run";
import type { RunResponse } from "../../types/run";
import { buildPipelineStepRows, type PipelineHints } from "../../utils/pipelineUi";

type PipelineStripProps = {
  run: RunResponse | null;
  graphStatus: GraphStatusResponse | null;
  hints?: PipelineHints;
};

export function PipelineStrip({ run, graphStatus, hints }: PipelineStripProps) {
  const steps = buildPipelineStepRows(run, graphStatus, hints);

  return (
    <div className="overflow-x-auto pb-2">
      <div className="flex min-w-max gap-1">
        {steps.map((row, i) => {
          const bar =
            row.status === "done"
              ? "bg-emerald-500/80"
              : row.status === "running"
                ? "bg-cyan-400"
                : row.status === "failed"
                  ? "bg-red-500"
                  : "bg-zinc-700/80";
          return (
            <div
              key={row.id}
              className="flex max-w-[7rem] flex-col items-center gap-1 px-1 text-center"
              title={row.id}
            >
              <div className={`h-1.5 w-full rounded-full ${bar}`} />
              <span className="text-[10px] font-medium leading-tight text-zinc-300">
                {row.label}
              </span>
              <span className="font-mono text-[9px] text-zinc-600">{i + 1}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
