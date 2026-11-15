import { act, renderHook } from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { useResource } from "./useResource";
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
it("never exposes previous-source data or accepts a late response", async () => {
  let finish!: (x: string) => void;
  const loader = vi.fn(
    () =>
      new Promise<string>((resolve) => {
        finish = resolve;
      }),
  );
  const hook = renderHook(({ key }) => useResource(key, loader, 2000), {
    initialProps: { key: "a" },
  });
  const old = finish;
  await act(async () => hook.rerender({ key: "b" }));
  await act(async () => old("wrong source"));
  expect(hook.result.current.data).toBeUndefined();
  await act(async () => finish("b"));
  expect(hook.result.current.data).toBe("b");
  hook.rerender({ key: "c" });
  expect(hook.result.current.data).toBeUndefined();
  hook.unmount();
});
it("does not overlap, aborts on cleanup and removes timers", async () => {
  let signal: AbortSignal | undefined;
  const loader = vi.fn((s) => {
    signal = s;
    return new Promise<string>(() => {});
  });
  const hook = renderHook(() => useResource("a", loader, 2000));
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(loader).toHaveBeenCalledTimes(1);
  hook.unmount();
  expect(signal?.aborted).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
  await act(() => vi.advanceTimersByTimeAsync(60000));
  expect(loader).toHaveBeenCalledTimes(1);
});
it("recovers from API failure and supports explicit retry", async () => {
  const loader = vi
    .fn()
    .mockRejectedValueOnce(Error("503"))
    .mockResolvedValue("online");
  const hook = renderHook(() => useResource("a", loader, 2000));
  await act(() => Promise.resolve());
  expect(hook.result.current.status).toBe("offline");
  await act(async () => hook.result.current.retry());
  expect(hook.result.current.data).toBe("online");
  hook.unmount();
});
