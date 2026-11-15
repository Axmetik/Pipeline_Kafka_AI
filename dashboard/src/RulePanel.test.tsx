import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, it, expect } from "vitest";
import RulePanel, { hybridText } from "./RulePanel";
import type { Snapshot, HybridDecision } from "./types";
afterEach(cleanup);
const decision = (flag: boolean | null, inputs: string[] = []) =>
  ({
    flag,
    triggered_inputs: inputs,
    measurement_id: "m",
    coverage_count: flag === null ? 1 : 2,
    layer_version: "v-fixture",
  }) as HybridDecision;
const snapshot = (flag: boolean | null) =>
  ({
    measurements: [
      { measurement_id: "m", measurement_timestamp: "2016-01-01T08:00:00" },
    ],
    hybridDecisions: {
      channel_status: "available",
      items: [decision(flag, ["residual", "sustained_high"])],
    },
    ruleAssessments: {
      channel_status: "available",
      items: [
        {
          assessment_id: "q",
          measurement_id: "m",
          measurement_timestamp: "2016-01-01T08:00:00",
          rule: "interval_gap",
          category: "telemetry_quality",
          flag: true,
          status: "ready",
          evidence: { missing_intervals: 2 },
        },
      ],
    },
    hybridEvents: {
      channel_status: "available",
      items: [
        {
          episode_id: "e",
          start_timestamp: "2016-01-01T08:00:00",
          end_timestamp: "2016-01-01T08:50:00",
          triggered_inputs: ["sustained_high"],
          flagged_points: 6,
          status: "closed",
        },
      ],
    },
  }) as unknown as Snapshot;
describe("persisted experimental rule layer", () => {
  it("distinguishes unavailable, negative, and contributor-positive", () => {
    expect(hybridText(decision(null))).toContain("Недоступно");
    expect(hybridText(decision(false))).toContain("Відхилення немає");
    expect(hybridText(decision(true, ["residual"]))).toContain("RF21");
    expect(hybridText(decision(true, ["sustained_high"]))).toContain(
      "тривале підвищення",
    );
  });
  it("shows missing schema without reporting normality", () => {
    render(
      <RulePanel
        data={
          {
            ...snapshot(null),
            hybridDecisions: { channel_status: "not_connected", items: [] },
          } as unknown as Snapshot
        }
      />,
    );
    expect(screen.getByText(/Канал вимкнений/)).toBeInTheDocument();
    expect(screen.getByTestId("hybrid-current")).toHaveTextContent(
      "Недоступно",
    );
  });
  it("shows both origins, naive time, and separate telemetry semantics", () => {
    render(<RulePanel data={snapshot(true)} />);
    expect(screen.getByTestId("hybrid-current")).toHaveTextContent(
      "Residual (відхилення від RF21) + Sustained high",
    );
    expect(
      screen.getByText(/Інтервал: 2016-01-01 08:00:00/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Пропущені інтервали: 2/)).toHaveTextContent(
      "виявлено на наступному записі",
    );
    expect(screen.getByText("experimental")).toBeInTheDocument();
  });
  it("renders persisted episode origins separately from Unanimous", () => {
    render(<RulePanel data={snapshot(true)} events />);
    expect(
      screen.getByText("Sustained high (тривале підвищення)"),
    ).toBeInTheDocument();
    expect(screen.getByText("2016-01-01 08:50:00")).toBeInTheDocument();
  });
});
