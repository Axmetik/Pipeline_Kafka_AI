import { useEffect, useState } from "react";
// The key is the complete request scope. A previous source is never rendered as the new one.
export function useResource<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
  interval = 5000,
) {
  const [retryCount, setRetryCount] = useState(0);
  const [state, setState] = useState<{
    key: string;
    data?: T;
    status: "loading" | "online" | "offline";
  }>({ key, status: "loading" });
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout> | undefined,
      failures = 0;
    let controller: AbortController;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      controller = new AbortController();
      deadline = setTimeout(() => controller.abort(), 12000);
      try {
        const data = await load(controller.signal);
        if (active) {
          setState({ key, data, status: "online" });
          failures = 0;
        }
      } catch {
        if (active) {
          failures++;
          setState((old) => ({
            key,
            data: old.key === key ? old.data : undefined,
            status: "offline",
          }));
        }
      } finally {
        clearTimeout(deadline);
      }
      if (active)
        timer = setTimeout(
          refresh,
          Math.min(30000, interval * 2 ** Math.min(failures, 4)),
        );
    }
    void refresh();
    return () => {
      active = false;
      controller?.abort();
      clearTimeout(timer);
      clearTimeout(deadline);
    };
    // Scope key owns the loader's inputs, avoiding restarts on each render.
  }, [key, retryCount, interval]);
  const current =
    state.key === key
      ? state
      : { key, data: undefined, status: "loading" as const };
  return { ...current, retry: () => setRetryCount((n) => n + 1) };
}
