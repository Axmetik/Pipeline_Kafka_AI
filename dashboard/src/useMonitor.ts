import { useEffect, useState } from "react";
import type { Selection, Snapshot } from "./types";
import { load } from "./data";
export function useMonitor(selection: Selection, windowSize: number) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [connection, setConnection] = useState<
    "loading" | "online" | "offline"
  >("loading");
  const [updated, setUpdated] = useState<string | null>(null);
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout> | undefined,
      failures = 0;
    let controller: AbortController,
      deadline: ReturnType<typeof setTimeout> | undefined;
    setData(null);
    setConnection("loading");
    async function poll() {
      controller = new AbortController();
      deadline = setTimeout(() => controller.abort(), 12000);
      try {
        const result = await load(selection, windowSize, controller.signal);
        if (!active) return;
        setData(result);
        setConnection("online");
        setUpdated(new Date().toISOString());
        failures = 0;
      } catch {
        if (!active) return;
        failures++;
        setConnection("offline");
      } finally {
        clearTimeout(deadline);
      }
      // Schedule after completion: one refresh at a time; cancelled on selection/unmount.
      if (active)
        timer = setTimeout(
          poll,
          Math.min(30000, 2000 * 2 ** Math.min(failures, 4)),
        );
    }
    void poll();
    return () => {
      active = false;
      controller?.abort();
      clearTimeout(timer);
      clearTimeout(deadline);
    };
  }, [selection.run, selection.building, selection.source, windowSize]);
  return { data, connection, updated };
}
