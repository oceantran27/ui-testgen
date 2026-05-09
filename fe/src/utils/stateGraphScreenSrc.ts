/**
 * URL for a canonical screen screenshot served via FastAPI StaticFiles at `/uploads`.
 */
export function stateGraphScreenSrc(
  inputId: string,
  imageId: string,
  screenImages?: Record<string, string> | null,
): string | undefined {
  const basename = screenImages?.[imageId];
  if (!basename?.trim()) {
    return undefined;
  }
  const safeBase = basename.replace(/\\/g, "/").split("/").pop() ?? basename;
  return `/uploads/state-graph-input/${encodeURIComponent(inputId)}/${encodeURIComponent(safeBase)}`;
}
