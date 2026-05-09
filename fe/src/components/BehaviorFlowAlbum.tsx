import { useState } from "react";
import { FlowLightboxModal } from "./FlowLightboxModal";
import { behaviorFlowSectionId } from "./BehaviorFlowNav";
import type { BehaviorFlowViewGroup } from "../types/behaviorFlow";

interface BehaviorFlowAlbumProps {
  groups: BehaviorFlowViewGroup[];
  isLoading: boolean;
}

function AlbumSkeleton() {
  return (
    <div className="space-y-8">
      {[0, 1].map((k) => (
        <div key={k} className="card animate-pulse">
          <div className="mb-4 h-6 w-1/3 rounded bg-zinc-800" />
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 6 }, (_, j) => (
              <div
                key={j}
                className="aspect-square rounded-lg bg-zinc-800"
                aria-hidden
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function BehaviorFlowAlbum({ groups, isLoading }: BehaviorFlowAlbumProps) {
  const [lightbox, setLightbox] = useState<{
    images: string[];
    start: number;
    title: string;
  } | null>(null);

  if (isLoading) {
    return <AlbumSkeleton />;
  }

  if (groups.length === 0) {
    return null;
  }

  return (
    <div className="space-y-10">
      {groups.map((g, i) => (
        <section
          key={`${g.behavior_flow}-${i}`}
          id={behaviorFlowSectionId(i)}
          className="card scroll-mt-20"
        >
          <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
            <h2 className="text-xl font-bold text-zinc-100">{g.behavior_flow}</h2>
            <span className="text-sm text-zinc-400">
              {g.images.length} image{g.images.length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {g.images.map((src, j) => (
              <button
                key={src + j}
                type="button"
                onClick={() => {
                  setLightbox({ images: g.images, start: j, title: g.behavior_flow });
                }}
                className="group relative aspect-square overflow-hidden rounded-lg border border-zinc-700/80 bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-cyan-500/60"
              >
                <img
                  src={src}
                  alt={`${g.behavior_flow} step ${j + 1}`}
                  loading="lazy"
                  className="h-full w-full object-cover transition-transform group-hover:scale-105"
                />
              </button>
            ))}
          </div>
        </section>
      ))}

      <FlowLightboxModal
        isOpen={lightbox !== null}
        images={lightbox?.images ?? []}
        startIndex={lightbox?.start ?? 0}
        flowTitle={lightbox?.title ?? ""}
        onClose={() => {
          setLightbox(null);
        }}
      />
    </div>
  );
}
