import type { DashboardView } from "./view";
import { label, valueLabel } from "../data";
import { chartTime } from "../insights";
import { chartTooltipStyle, statusName } from "./presentation";
import { Database } from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
export default function ForecastChart({ view }: { view: DashboardView }) {
  const {
    data,
    connection,
    chart,
    latest,
    intervalSeconds,
    windowSize,
    setWindowSize,
  } = view;
  return (
    <section className="card main-chart" data-testid="forecast-chart">
      <div className="chart-header">
        <div>
          <h2>Споживання та прогноз</h2>
          <p className="muted small">
            Інтервальна енергія · Wh за {intervalSeconds} секунд
          </p>
        </div>
        <label className="window-select">
          Вікно
          <select
            aria-label="Видиме вікно"
            value={windowSize}
            onChange={(e) => setWindowSize(Number(e.target.value))}
          >
            <option value={72}>Останні 72 точки</option>
            <option value={144}>Останні 144 точки</option>
            <option value={288}>Останні 288 точок</option>
          </select>
        </label>
      </div>
      <div className="chart-legend">
        <span>
          <i className="legend-line actual" />
          Фактичне споживання
        </span>
        <span>
          <i className="legend-line predicted" />
          HGB20 · прогноз на 10 хв
        </span>
        <span className="point-count" data-testid="visible-count">
          {data?.measurements.length ?? 0} точок у вікні
        </span>
      </div>
      <div className="energy-plot">
        {chart.length ? (
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart
              data={chart}
              margin={{ top: 15, right: 20, left: 0, bottom: 5 }}
            >
              <defs>
                <linearGradient id="energy-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor="var(--accent)"
                    stopOpacity={0.14}
                  />
                  <stop
                    offset="100%"
                    stopColor="var(--accent)"
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="timestamp"
                interval="preserveStartEnd"
                tickFormatter={(v) => chartTime(String(v))}
                minTickGap={48}
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                axisLine={false}
                tickLine={false}
                width={45}
              />
              <Tooltip
                labelFormatter={(v) => label(String(v))}
                formatter={(v, n) => [
                  valueLabel(v as number | null) + " Wh",
                  n === "actual" ? "Фактичне" : "Прогноз HGB20",
                ]}
                contentStyle={chartTooltipStyle}
                cursor={{
                  stroke: "var(--border-strong)",
                  strokeDasharray: "3 3",
                }}
              />
              <Area
                dataKey="actual"
                name="actual"
                type="monotone"
                stroke="var(--accent)"
                strokeWidth={2}
                activeDot={{
                  r: 4,
                  stroke: "var(--surface)",
                  strokeWidth: 2,
                }}
                fill="url(#energy-fill)"
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="forecast"
                name="forecast"
                type="monotone"
                stroke="var(--forecast)"
                strokeWidth={2}
                strokeDasharray="5 4"
                activeDot={{
                  r: 4,
                  stroke: "var(--surface)",
                  strokeWidth: 2,
                }}
                dot={false}
                connectNulls={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-panel" data-testid="empty-state">
            <Database size={28} />
            <h3>
              {connection === "loading"
                ? "Завантажуємо вимірювання"
                : "Очікуємо дані replay"}
            </h3>
            <p>
              Запустіть producer для вибраного запуску. Нові точки з’являться
              автоматично.
            </p>
          </div>
        )}
      </div>
      <div className="chart-caption">
        <span>
          {data?.basis === "offset_aware"
            ? "Час джерела з явним offset"
            : "Час датасету, часовий пояс не визначено"}
        </span>
        <span>
          Прогноз суміщено за цільовим часом · відсутнє значення не означає нуль
        </span>
      </div>
      {latest && latest.feature_status !== "ready" && (
        <div className="notice" data-testid="warmup-state">
          {statusName(latest.feature_status)}:{" "}
          {latest.feature_status === "incompatible"
            ? "модель не застосовується до цього джерела."
            : "накопичуємо часову історію; відсутній прогноз показано як —."}
        </div>
      )}
    </section>
  );
}
