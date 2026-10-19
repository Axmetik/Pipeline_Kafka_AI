import { describe, it, expect } from "vitest";
import { align, label, timeKey, valueLabel } from "./data";
import type { Measurement, Forecast } from "./types";
const m = (time: string, value: number) =>
  ({
    measurement_id: time,
    measurement_timestamp: time,
    energy_wh: value,
  }) as Measurement;
const f = (
  origin: string,
  target: string,
  value: number | null,
  purpose = "primary_forecast",
) =>
  ({
    forecast_origin: origin,
    forecast_target_timestamp: target,
    predicted_energy_wh: value,
    purpose,
  }) as Forecast;
describe("time and energy contracts", () => {
  it("preserves naive labels", () => {
    const time = "2016-01-11T17:00:00";
    expect(timeKey(time, "dataset_naive")).toBe(time);
    expect(label(time)).toBe("2016-01-11 17:00:00");
  });
  it("aligns to target and excludes RF reference", () => {
    const points = align(
      [m("2016-01-01T00:00:00", 40), m("2016-01-01T00:10:00", 50)],
      [
        f("2016-01-01T00:00:00", "2016-01-01T00:10:00", 45),
        f(
          "2016-01-01T00:00:00",
          "2016-01-01T00:10:00",
          900,
          "residual_reference",
        ),
      ],
      "dataset_naive",
    );
    expect(points.map((p) => [p.actual, p.forecast])).toEqual([
      [40, null],
      [50, 45],
    ]);
  });
  it("preserves null and future actual missing", () => {
    const points = align(
      [m("2016-01-01T00:00:00", 0)],
      [f("2016-01-01T00:00:00", "2016-01-01T00:10:00", null)],
      "dataset_naive",
    );
    expect(points[1].actual).toBeNull();
    expect(points[1].forecast).toBeNull();
    expect(valueLabel(null)).toBe("—");
    expect(valueLabel(0)).toBe("0");
  });
  it("matches aware instants only with explicit offsets", () => {
    expect(timeKey("2016-01-01T00:00:00+02:00", "offset_aware")).toBe(
      timeKey("2015-12-31T22:00:00Z", "offset_aware"),
    );
    expect(() => timeKey("2016-01-01T00:00:00", "offset_aware")).toThrow();
  });
});
