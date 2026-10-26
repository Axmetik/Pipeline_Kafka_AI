import { describe, it, expect } from "vitest";
import {
  buildInsights,
  nextPrimary,
  elapsed,
  chartTime,
  scoreTick,
} from "./insights";
import { valueLabel } from "./data";
import type { Measurement, Forecast, Snapshot, Detector } from "./types";
const times = [
  "2016-01-11T23:40:00",
  "2016-01-11T23:50:00",
  "2016-01-12T00:00:00",
  "2016-01-12T00:10:00",
  "2016-01-12T00:20:00",
  "2016-01-12T00:30:00",
];
const m = (value: number, i: number) =>
  ({
    measurement_id: `m${i}`,
    measurement_timestamp: times[i],
    energy_wh: value,
    interval_seconds: 600,
    received_at: "2026-10-26T12:00:00Z",
  }) as Measurement;
export function snapshot(values = [40, 80]) {
  return {
    selection: { run: "replay-a", building: "house", source: "appliances" },
    measurements: values.map(m).reverse(),
    forecasts: [],
    scores: [],
    basis: "dataset_naive",
    status: { unique_measurements: values.length },
    events: [],
  } as unknown as Snapshot;
}
const f = (overrides: Partial<Forecast> = {}) =>
  ({
    forecast_id: "f",
    measurement_id: "m1",
    purpose: "primary_forecast",
    forecast_origin: times[1],
    forecast_target_timestamp: times[2],
    status: "ready",
    predicted_energy_wh: 100,
    model_version: "hgb20-v1",
    generated_at: "2026-10-26T12:00:01Z",
    ...overrides,
  }) as Forecast;
function score(
  data: Snapshot,
  detector: Detector,
  flag: boolean | null,
  value: number | null = 11,
) {
  data.scores.push({
    score_id: detector,
    measurement_id: "m1",
    detector,
    score: value,
    threshold: 10,
    flag,
    status: value === null ? "warmup" : "ready",
  } as Snapshot["scores"][number]);
}
describe("deterministic energy insights", () => {
  it("compares above-average consumption using interval Wh and correct rounding", () => {
    const x = buildInsights(snapshot());
    expect(x.mean).toBe(60);
    expect(x.consumption).toContain("33,3% вище");
    expect(x.consumption).toContain("80 Wh за 10 хвилин");
    expect(x.summary).toHaveLength(3);
  });
  it("compares below average and keeps actual zero distinct from missing", () => {
    expect(buildInsights(snapshot([80, 40])).consumption).toContain(
      "33,3% нижче",
    );
    expect(buildInsights(snapshot([80, 0])).consumption).toContain(
      "100% нижче",
    );
    expect(valueLabel(NaN)).toBe("—");
    expect(valueLabel(Infinity)).toBe("—");
    expect(valueLabel(0)).toBe("0");
  });
  it("handles empty, insufficient, invalid, zero and mixed-interval history", () => {
    expect(buildInsights(snapshot([])).mean).toBeNull();
    expect(buildInsights(snapshot([40])).consumption).toContain(
      "щонайменше два",
    );
    expect(buildInsights(snapshot([0, 0])).consumption).toContain(
      "нульовим середнім",
    );
    const d = snapshot([50, NaN]);
    expect(buildInsights(d).consumption).toContain("некоректне");
    d.measurements[0].energy_wh = Infinity;
    expect(buildInsights(d).mean).toBe(50);
    d.measurements[0].energy_wh = -1;
    expect(buildInsights(d).mean).toBe(50);
    d.measurements[0].energy_wh = 70;
    d.measurements[0].interval_seconds = 60;
    expect(buildInsights(d).consumption).toContain("70 Wh за 60 секунд");
    expect(buildInsights(d).consumption).toContain("щонайменше два");
  });
  it("uses two contiguous groups of three, refuses gaps and zero denominator", () => {
    const d = snapshot([10, 10, 10, 20, 20, 20]);
    expect(buildInsights(d).trend).toContain("100% вище");
    d.measurements[2].measurement_timestamp = "2016-01-12T00:11:00";
    expect(buildInsights(d).trend).toContain("6 послідовних");
    expect(buildInsights(snapshot([0, 0, 0, 20, 20, 20])).trend).toContain(
      "нульове середнє",
    );
  });
  it("selects primary by measurement identity, origin instant and exact target horizon", () => {
    const d = snapshot();
    d.forecasts = [
      f({ purpose: "residual_reference", predicted_energy_wh: 900 }),
      f({ measurement_id: "wrong" }),
      f({ forecast_origin: times[0] }),
      f({ forecast_target_timestamp: times[3] }),
      f(),
    ];
    expect(
      nextPrimary(d.measurements[0], d.forecasts, d.basis)?.predicted_energy_wh,
    ).toBe(100);
    const x = buildInsights(d);
    expect(x.forecast).toContain("2016-01-12 00:00:00");
    expect(x.forecast).toContain("25% вище");
    expect(x.forecast).not.toContain("900");
    expect(x.forecast).toContain("не є гарантією");
  });
  it("accepts equivalent offset-aware instants and exact midnight/leap transitions", () => {
    const d = snapshot();
    d.basis = "offset_aware";
    d.measurements[0].measurement_timestamp = "2016-01-12T01:50:00+02:00";
    const forecast = f({
      forecast_origin: "2016-01-11T23:50:00Z",
      forecast_target_timestamp: "2016-01-12T00:00:00Z",
    });
    expect(nextPrimary(d.measurements[0], [forecast], d.basis)).toBe(forecast);
    expect(
      elapsed("2016-02-28T23:50:00", "2016-02-29T00:00:00", "dataset_naive"),
    ).toBe(600);
    expect(
      elapsed("2016-12-31T23:50:00", "2017-01-01T00:00:00", "dataset_naive"),
    ).toBe(600);
    expect(
      Number.isNaN(elapsed("2016-02-30T00:00:00", times[0], "dataset_naive")),
    ).toBe(true);
    expect(chartTime(times[2])).toBe("12.01 00:00");
    expect(scoreTick(0.000001)).toBe("1.0e-6");
    expect(scoreTick(-100000)).toBe("-1.0e+5");
  });
  it.each(["warmup", "incompatible", "gap"])(
    "explains %s without false zero forecasts",
    (status) => {
      const d = snapshot();
      d.forecasts = [f({ status, predicted_energy_wh: null })];
      const x = buildInsights(d);
      expect(x.summary[1]).toContain("ще не готовий");
      expect(x.forecast).not.toContain("0 Wh");
    },
  );
  it("does not fall back to an older ready forecast, RF21 or null/invalid ready value", () => {
    const d = snapshot();
    d.forecasts = [
      f({
        forecast_origin: times[0],
        forecast_target_timestamp: times[1],
        measurement_id: "m0",
      }),
      f({ purpose: "residual_reference" }),
    ];
    expect(buildInsights(d).next).toBeUndefined();
    for (const v of [null, NaN, Infinity, -10]) {
      d.forecasts = [f({ predicted_energy_wh: v })];
      expect(buildInsights(d).summary[1]).toContain("ще не готовий");
    }
    d.measurements[0].energy_wh = 0;
    d.forecasts = [f()];
    expect(buildInsights(d).forecast).toContain("не визначене");
  });
  it("reports independent detectors, coverage and only flags in the visible window", () => {
    const d = snapshot();
    score(d, "isolation_forest", true);
    score(d, "autoencoder", true);
    score(d, "residual", false, 5);
    score(d, "residual", true);
    d.scores.at(-1)!.measurement_id = "outside";
    const x = buildInsights(d);
    expect(x.detectors.map((x) => x.flags)).toEqual([1, 1, 0]);
    expect(x.detectors[0].text).toContain("перевірено 1 зі 2");
    expect(x.summary[2]).toContain("Isolation Forest, Autoencoder");
    expect(x.summary[2]).not.toContain("Residual Detector");
    expect(x.summary[2]).toContain("незалежні");
  });
  it("distinguishes unavailable scores from verified no exceedances", () => {
    const d = snapshot();
    score(d, "residual", null, null);
    expect(buildInsights(d).summary[2]).toContain("поки недоступне");
    score(d, "autoencoder", false, 5);
    expect(buildInsights(d).summary[2]).toContain("У доступних оцінках");
    expect(buildInsights(d).detectors[0].checked).toBe(0);
    d.scores[1].threshold = NaN;
    expect(buildInsights(d).detectors[1].checked).toBe(0);
  });
  it("handles every supported window without using processing time", () => {
    for (const size of [72, 144, 288]) {
      const d = snapshot([10, 20]);
      d.measurements = Array.from({ length: size }, (_, i) => ({
        ...m(i + 1, 0),
        measurement_id: `w${i}`,
        measurement_timestamp: `2016-01-${String(1 + Math.floor(i / 24)).padStart(2, "0")}T${String(i % 24).padStart(2, "0")}:00:00`,
      })).reverse();
      const before = JSON.stringify(d);
      const x = buildInsights(d);
      expect(x.mean).toBe((size + 1) / 2);
      expect(x.window).not.toContain("2026");
      expect(buildInsights(d)).toEqual(x);
      expect(JSON.stringify(d)).toBe(before);
    }
  });
});
