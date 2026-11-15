import type { CSSProperties } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { label, valueLabel } from "../data";
import { scoreTick, finite } from "../insights";
import type { Score } from "../types";
import { chartTooltipStyle, detectors, statusName } from "./presentation";
export default function ScoreChart({
  detector,
  rows,
}: {
  detector: (typeof detectors)[number];
  rows: Score[];
}) {
  const ordered = [...rows].reverse();
  const latest = rows[0];
  return (
    <section
      className="card detector"
      style={{ "--detector-color": detector.color } as CSSProperties}
      data-testid={`detector-${detector.id}`}
    >
      <div className="card-heading">
        <h3>{detector.name}</h3>
        <span className="badge experimental" title="Експериментальний метод">
          experimental
        </span>
      </div>
      <p className="muted small">{detector.description}</p>
      <div className="score-values">
        <strong style={{ color: detector.color }}>
          {valueLabel(latest?.score, 4)}
          {detector.id === "residual" && (
            <small className="score-unit">Wh</small>
          )}
        </strong>
        <span>
          Поріг <b>{valueLabel(latest?.threshold, 4)}</b>
          {detector.id === "residual" ? " Wh" : ""}
        </span>
      </div>
      <div className="mini-chart" aria-label={`Score ${detector.name}`}>
        {ordered.length ? (
          <ResponsiveContainer width="100%" height={120}>
            <ComposedChart
              data={ordered}
              margin={{ top: 8, right: 8, left: 4, bottom: 0 }}
            >
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="measurement_timestamp" hide />
              <YAxis
                fontSize={10}
                tick={{ fill: "var(--text-muted)" }}
                tickLine={false}
                axisLine={false}
                width={74}
                tickFormatter={scoreTick}
                domain={["auto", "auto"]}
              />
              <Tooltip
                labelFormatter={(v) => label(String(v))}
                formatter={(v, n) => [
                  valueLabel(v as number | null, 4) +
                    (detector.id === "residual" ? " Wh" : ""),
                  n === "score" ? "Score" : "Поріг",
                ]}
                contentStyle={chartTooltipStyle}
                cursor={{
                  stroke: "var(--border-strong)",
                  strokeDasharray: "3 3",
                }}
              />
              <Line
                dataKey="threshold"
                name="threshold"
                stroke="var(--threshold)"
                strokeDasharray="4 4"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="score"
                name="score"
                stroke={detector.color}
                strokeWidth={2}
                activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="chart-empty">Очікуємо оцінки</div>
        )}
      </div>
      <div className="detector-footer">
        <span
          className={latest?.status === "ready" ? "status ready" : "status"}
        >
          {latest ? statusName(latest.status) : "Немає даних"}
        </span>
        <span>
          Без готової оцінки:{" "}
          {
            rows.filter(
              (r) => r.status !== "ready" || !finite(r.score) || r.flag == null,
            ).length
          }
          <br />
          Перевищень у вибраному вікні:{" "}
          {
            rows.filter(
              (r) =>
                r.status === "ready" &&
                finite(r.score) &&
                finite(r.threshold) &&
                r.flag === true,
            ).length
          }
        </span>
      </div>
    </section>
  );
}
