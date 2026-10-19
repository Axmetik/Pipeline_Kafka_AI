import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { load } from "./data";
import { useMonitor } from "./useMonitor";
import type { Snapshot } from "./types";
vi.mock("./data", () => ({ load: vi.fn() }));
const selection = { run: "run-a", building: "house", source: "meter" };
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(load).mockReset();
});
afterEach(() => {
  delete window.__energyPerformance;
  vi.useRealTimers();
});
it("emits opt-in telemetry only after the snapshot is committed", async () => {
  const callback = vi.fn();
  window.__energyPerformance = callback;
  vi.mocked(load).mockResolvedValue({
    measurements: [{ measurement_id: "a" }, { measurement_id: "b" }],
  } as Snapshot);
  const hook = renderHook(() => useMonitor(selection, 144));
  await act(() => Promise.resolve());
  expect(callback).toHaveBeenCalledTimes(1);
  expect(callback.mock.calls[0][0].ids).toEqual(["a", "b"]);
  expect(callback.mock.calls[0][0].domEpochMs).toBeGreaterThanOrEqual(
    callback.mock.calls[0][0].fetchedEpochMs,
  );
  expect(load).toHaveBeenCalledTimes(1);
  hook.unmount();
});
it("does not overlap and cancels requests/timers", async () => {
  let resolve!: (s: Snapshot) => void;
  vi.mocked(load).mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const hook = renderHook(() => useMonitor(selection, 144));
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(load).toHaveBeenCalledTimes(1);
  await act(async () => resolve({} as Snapshot));
  expect(hook.result.current.connection).toBe("online");
  await act(() => vi.advanceTimersByTimeAsync(1999));
  expect(load).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(load).toHaveBeenCalledTimes(2);
  const signal = vi.mocked(load).mock.calls[1][2];
  hook.unmount();
  expect(signal.aborted).toBe(true);
  await act(() => vi.advanceTimersByTimeAsync(60000));
  expect(load).toHaveBeenCalledTimes(2);
});
it("backs off then resumes polling", async () => {
  vi.mocked(load)
    .mockRejectedValueOnce(new Error("503"))
    .mockResolvedValue({} as Snapshot);
  const hook = renderHook(() => useMonitor(selection, 144));
  await act(() => Promise.resolve());
  expect(hook.result.current.connection).toBe("offline");
  await act(() => vi.advanceTimersByTimeAsync(3999));
  expect(load).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(hook.result.current.connection).toBe("online");
  await act(() => vi.advanceTimersByTimeAsync(2000));
  expect(load).toHaveBeenCalledTimes(3);
  hook.unmount();
});
it("ignores late responses from old selection", async () => {
  let oldResolve!: (s: Snapshot) => void;
  vi.mocked(load)
    .mockImplementationOnce(
      () =>
        new Promise((r) => {
          oldResolve = r;
        }),
    )
    .mockResolvedValue({
      selection: { ...selection, run: "run-b" },
    } as Snapshot);
  const hook = renderHook(({ run }) => useMonitor({ ...selection, run }, 144), {
    initialProps: { run: "run-a" },
  });
  const signal = vi.mocked(load).mock.calls[0][2];
  await act(async () => hook.rerender({ run: "run-b" }));
  expect(signal.aborted).toBe(true);
  await act(async () => oldResolve({ selection } as Snapshot));
  expect(hook.result.current.data?.selection.run).toBe("run-b");
  hook.unmount();
});
it("times out a stalled cycle and recovers with a new abort controller", async () => {
  vi.mocked(load)
    .mockImplementationOnce(
      (_s, _w, signal) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(new Error("timeout")));
        }),
    )
    .mockResolvedValue({} as Snapshot);
  const hook = renderHook(() => useMonitor(selection, 144));
  await act(() => vi.advanceTimersByTimeAsync(12000));
  expect(hook.result.current.connection).toBe("offline");
  await act(() => vi.advanceTimersByTimeAsync(4000));
  expect(hook.result.current.connection).toBe("online");
  expect(vi.mocked(load).mock.calls[1][2].aborted).toBe(false);
  hook.unmount();
});
