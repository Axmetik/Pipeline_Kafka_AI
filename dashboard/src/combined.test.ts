import { expect, it } from "vitest";
import { combinedText } from "./combined";
import type { CombinedDecision } from "./types";
it("describes independent agreement levels and does not invent probabilities", () => {
  for (let n = 0; n < 4; n++) {
    const text = combinedText({
      status: "ready",
      coverage_count: 3,
      trigger_count: n,
      flag: n === 3,
      triggered_methods: n ? ["isolation_forest"] : [],
    } as CombinedDecision);
    expect(text).toContain(`${n} із 3`);
    expect(text).toContain("не ймовірність");
    expect(text).toContain(
      n === 3
        ? "Правило комбінування спрацювало"
        : "Правило комбінування не спрацювало",
    );
  }
});
it("never interprets null, partial, gap or incompatible as 0/3", () => {
  for (const status of ["warmup", "partial", "gap", "incompatible"] as const) {
    const text = combinedText({
      status,
      coverage_count: 2,
      trigger_count: null,
      flag: null,
      available_trigger_count: 1,
    } as CombinedDecision);
    expect(text).toContain("Неповне покриття");
    expect(text).toContain("це не 0 із 3");
  }
  expect(combinedText(undefined)).toContain("недоступне");
});
import { buildInsights } from "./insights";
import type { Snapshot } from "./types";
it("aligns combined Insights to the current measurement and clears stale decisions", () => {
  const data = {
    measurements: [
      {
        measurement_id: "latest",
        measurement_timestamp: "2016-01-01T00:00:00",
        energy_wh: 20,
        interval_seconds: 600,
      },
    ],
    forecasts: [],
    scores: [],
    basis: "dataset_naive",
    combined: [
      {
        measurement_id: "latest",
        status: "ready",
        coverage_count: 3,
        trigger_count: 3,
        flag: true,
        triggered_methods: ["isolation_forest", "autoencoder", "residual"],
      },
    ],
  } as unknown as Snapshot;
  expect(buildInsights(data).summary).toHaveLength(4);
  expect(buildInsights(data).summary[3]).toContain("3 із 3");
  data.combined![0].measurement_id = "stale";
  expect(buildInsights(data).summary[3]).toContain("недоступне");
});
