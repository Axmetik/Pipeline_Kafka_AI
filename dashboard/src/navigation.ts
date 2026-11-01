export type ProductPage = "overview" | "buildings" | "analytics" | "events";
export function pageFromHash(hash: string): ProductPage {
  const key = hash.replace(/^#/, "");
  if (key === "models" || key === "detectors") return "analytics";
  return key === "buildings" || key === "analytics" || key === "events"
    ? key
    : "overview";
}
export function selectionQuery(
  selection: { run: string; building: string; source: string },
  hash: string,
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(selection))
    if (value) query.set(key, value);
  return (query.size ? "?" + query : "") + (hash || "#overview");
}
