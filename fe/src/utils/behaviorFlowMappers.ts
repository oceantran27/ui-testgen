import type {
  BehaviorFlowOrganizeResponse,
  BehaviorFlowViewGroup,
} from "../types/behaviorFlow";

function screenIdForIndex(index: number): string {
  return `img_${String(index + 1).padStart(3, "0")}`;
}

/** Extension from file name, normalized; backend uses similar logic. */
export function extFromFileName(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? "";
  const idx = base.lastIndexOf(".");
  if (idx <= 0) {
    return "png";
  }
  const ext = base
    .slice(idx + 1)
    .replace(/[^a-z0-9]/gi, "")
    .toLowerCase();
  return ext || "png";
}

function extensionByScreenIdFromFiles(files: File[]): Record<string, string> {
  const out: Record<string, string> = {};
  files.forEach((f, i) => {
    out[screenIdForIndex(i)] = extFromFileName(f.name);
  });
  return out;
}

/**
 * Public URL path for a saved screen (matches `uploads/multi-img-input/<id>/img_001.<ext>`).
 */
export function screenToPublicPath(
  inputId: string,
  screenId: string,
  ext: string,
): string {
  return `/uploads/multi-img-input/${inputId}/${screenId}.${ext}`;
}

/**
 * Map API response + original files (same order as upload) to view groups with image URLs.
 */
export function responseToViewGroups(
  response: BehaviorFlowOrganizeResponse,
  files: File[],
): BehaviorFlowViewGroup[] {
  const extBy = extensionByScreenIdFromFiles(files);
  return response.flows.map((flow) => ({
    behavior_flow: flow.behavior_flow,
    images: flow.screens.map((sid) => {
      const ext = extBy[sid] ?? "png";
      return screenToPublicPath(response.input_id, sid, ext);
    }),
  }));
}
