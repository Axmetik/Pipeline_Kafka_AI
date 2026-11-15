import { useEffect, useState } from "react";
import { fetchJSON } from "./data";
import type { Page, Source } from "./types";
// Registered sources, not a fabricated building registry. One bounded request per entry/run/retry.
export function usePortfolio(run: string) {
  const [state, setState] = useState<{
    status: "loading" | "ready" | "error";
    sources: Source[];
    truncated: boolean;
  }>({ status: "loading", sources: [], truncated: false });
  const [revision, retry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => controller.abort(), 12000);
    setState({ status: "loading", sources: [], truncated: false });
    fetchJSON<Page<Source>>("/api/sources?limit=1000", controller.signal)
      .then((page) => {
        if (active)
          setState({
            status: "ready",
            sources: page.items,
            truncated: page.next_cursor !== null,
          });
      })
      .catch(() => {
        if (active)
          setState({ status: "error", sources: [], truncated: false });
      })
      .finally(() => clearTimeout(timer));
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [run, revision]);
  return { ...state, retry: () => retry((n) => n + 1) };
}
