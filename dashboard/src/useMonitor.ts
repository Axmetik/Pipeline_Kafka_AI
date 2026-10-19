import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Selection, Snapshot } from "./types";
import { load } from "./data";
// Evaluation harness installs this callback before navigation. No callback,
// storage, timer or telemetry traffic exists in the ordinary dashboard.
declare global {
  interface Window {
    __energyPerformance?: (snapshot: {
      ids: string[]; fetchedEpochMs: number; domEpochMs: number;
    }) => void;
  }
}
export function useMonitor(selection: Selection, windowSize: number) {
  const fetched = useRef(0);
  const [data, setData] = useState<Snapshot | null>(null);
  const [connection, setConnection] = useState<
    "loading" | "online" | "offline"
  >("loading");
  const [updated, setUpdated] = useState<string | null>(null);
  useLayoutEffect(() => {
    if (data && window.__energyPerformance) {
      window.__energyPerformance({
        ids: data.measurements.map((m) => m.measurement_id),
        fetchedEpochMs: fetched.current,
        domEpochMs: performance.timeOrigin + performance.now(),
      });
    }
  }, [data]);
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
        if (window.__energyPerformance)
          fetched.current = performance.timeOrigin + performance.now();
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
