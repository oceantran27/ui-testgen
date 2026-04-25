import type { BehaviorFlowViewGroup } from "../types/behaviorFlow";

const anchorId = (i: number) => `behavior-flow-section-${i}`;

export { anchorId as behaviorFlowSectionId };

export function scrollToFlowSection(i: number) {
  const el = document.getElementById(anchorId(i));
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

interface BehaviorFlowNavProps {
  groups: BehaviorFlowViewGroup[];
}

/**
 * Sticky short links when more than one flow; scrolls to each section.
 */
export function BehaviorFlowNav({ groups }: BehaviorFlowNavProps) {
  if (groups.length <= 1) {
    return null;
  }

  return (
    <nav
      className="sticky top-0 z-10 mb-6 rounded-xl border border-gray-200/80 bg-white/90 px-3 py-2 shadow-sm backdrop-blur-sm"
      aria-label="Behavior flow sections"
    >
      <p className="mb-1 text-xs font-semibold text-gray-500">Jump to flow</p>
      <ul className="flex flex-wrap gap-2">
        {groups.map((g, i) => (
          <li key={anchorId(i)}>
            <button
              type="button"
              onClick={() => {
                scrollToFlowSection(i);
              }}
              className="max-w-[12rem] truncate rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-left text-sm font-medium text-gray-800 hover:border-blue-300 hover:bg-blue-50"
              title={g.behavior_flow}
            >
              {g.behavior_flow}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
