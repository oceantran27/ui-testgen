export function formatMillis(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) {
    return "—";
  }
  if (ms < 1000) {
    return `${Math.round(ms)} ms`;
  }
  const sec = ms / 1000;
  if (sec < 60) {
    return `${sec.toFixed(sec < 10 ? 1 : 0)} s`;
  }
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
}
