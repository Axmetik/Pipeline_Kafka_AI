import { useMemo, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Box,
  Database,
  Gauge,
  Layers,
  Leaf,
  Radio,
  ShieldCheck,
  WifiOff,
  Zap,
} from "lucide-react";
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
import { align, label, valueLabel } from "./data";
import { useMonitor } from "./useMonitor";
import type { Detector, Selection, Score } from "./types";

const detectors: {
  id: Detector;
  name: string;
  description: string;
  color: string;
}[] = [
  {
    id: "isolation_forest",
    name: "Isolation Forest",
    description: "Ізоляція незвичних спостережень",
    color: "#5272c2",
  },
  {
    id: "autoencoder",
    name: "Autoencoder",
    description: "Помилка відновлення енергетичних ознак",
    color: "#9980bd",
  },
  {
    id: "residual",
    name: "Residual Detector",
    description: "Відхилення від окремого RF21-прогнозу",
    color: "#ca8d43",
  },
];
const statusName = (s: string) =>
  ({
    ready: "Готово",
    warmup: "Прогрів",
    incompatible: "Несумісне джерело",
    gap: "Пропуск історії",
  })[s] ?? s;

function ScoreChart({
  detector,
  rows,
}: {
  detector: (typeof detectors)[number];
  rows: Score[];
}) {
  const ordered = [...rows].reverse();
  const latest = rows[0];
  return (
    <section className="card detector" data-testid={`detector-${detector.id}`}>
      <div className="card-heading">
        <h3>{detector.name}</h3>
        <span className="badge experimental">experimental</span>
      </div>
      <p className="muted small">{detector.description}</p>
      <div className="score-values">
        <strong style={{ color: detector.color }}>
          {valueLabel(latest?.score, 4)}
        </strong>
        <span>
          Поріг <b>{valueLabel(latest?.threshold, 4)}</b>
        </span>
      </div>
      <div className="mini-chart" aria-label={`Score ${detector.name}`}>
        {ordered.length ? (
          <ResponsiveContainer width="100%" height={120}>
            <ComposedChart
              data={ordered}
              margin={{ top: 8, right: 4, left: -24, bottom: 0 }}
            >
              <CartesianGrid vertical={false} stroke="#eef1f0" />
              <XAxis dataKey="measurement_timestamp" hide />
              <YAxis
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={54}
                domain={["auto", "auto"]}
              />
              <Tooltip
                labelFormatter={(v) => label(String(v))}
                formatter={(v, n) => [
                  valueLabel(v as number | null, 4),
                  n === "score" ? "Score" : "Поріг",
                ]}
                contentStyle={{ borderRadius: 10, fontSize: 12 }}
              />
              <Line
                dataKey="threshold"
                name="threshold"
                stroke="#cc7a68"
                strokeDasharray="4 4"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                dataKey="score"
                name="score"
                stroke={detector.color}
                strokeWidth={2}
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
          {rows.filter((r) => r.score === null).length} без оцінки ·{" "}
          {rows.filter((r) => r.flag === true).length} перевищень
        </span>
      </div>
    </section>
  );
}

export default function App() {
  const initial = new URLSearchParams(window.location.search);
  const [selection, setSelection] = useState<Selection>({
    run: initial.get("run") || "",
    building: initial.get("building") || "",
    source: initial.get("source") || "",
  });
  const [windowSize, setWindowSize] = useState(144);
  const [detail, setDetail] = useState<string | null>(null);
  const { data, connection, updated } = useMonitor(selection, windowSize);
  const chart = useMemo(
    () => (data ? align(data.measurements, data.forecasts, data.basis) : []),
    [data],
  );
  const latest = data?.measurements[0];
  const intervalSeconds =
    latest?.interval_seconds ??
    data?.sources.find(
      (s) =>
        s.source_id === data.selection.source &&
        s.building_id === data.selection.building,
    )?.interval_seconds ??
    600;
  const actualUnit =
    intervalSeconds === 600 ? "Wh / 10 хв" : `Wh / ${intervalSeconds} с`;
  const next = data?.forecasts.find(
    (f) => f.forecast_origin === latest?.measurement_timestamp,
  );
  const chosen = data?.selection ?? selection;
  const choose = (value: Selection) => {
    setSelection(value);
    setDetail(null);
    const query = new URLSearchParams();
    for (const [key, v] of Object.entries(value)) if (v) query.set(key, v);
    history.replaceState(null, "", "?" + query);
  };
  const buildings = [...new Set(data?.sources.map((s) => s.building_id) ?? [])];
  const detailRow = chart.find((p) => p.measurement?.measurement_id === detail);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview">
          <span className="brand-symbol">
            <Zap size={23} />
          </span>
          <span>
            енергія<span className="brand-sub">BUILDING INTELLIGENCE</span>
          </span>
        </a>
        <div className="workspace-label">РОБОЧИЙ ПРОСТІР</div>
        <nav>
          <a className="active" href="#overview">
            <Gauge size={18} />
            Моніторинг
            <span className="nav-dot" />
          </a>
          <a href="#detectors">
            <Activity size={18} />
            Детектори
          </a>
          <a href="#events">
            <Layers size={18} />
            Історія подій
          </a>
          <a href="#models">
            <Box size={18} />
            Моделі
          </a>
        </nav>
        <div className="sidebar-note">
          <Leaf size={22} />
          <strong>Від даних до розуміння</strong>
          <p>
            Прогнозування та експериментальне виявлення незвичної поведінки.
          </p>
          <span>МАГІСТЕРСЬКИЙ ПРОЄКТ · MVP</span>
        </div>
        <div className="local-label">
          <ShieldCheck size={15} />
          Локальне середовище
        </div>
      </aside>
      <main id="overview">
        <header className="topbar">
          <span>
            Робочий простір <span className="slash">/</span>
            <b>Енергомоніторинг</b>
          </span>
          <span className="dataset-tag">
            <Database size={13} />
            UCI Appliances
          </span>
        </header>
        <div className="page-heading">
          <div>
            <div className="eyebrow">ENERGY MONITORING</div>
            <h1>
              Енергія вашої будівлі<span>.</span>
            </h1>
            <p>
              Фактичне споживання, короткостроковий прогноз та експериментальні
              оцінки.
            </p>
          </div>
          <div
            className={`connection ${connection}`}
            role="status"
            data-testid="connection-status"
          >
            {connection === "offline" ? (
              <WifiOff size={15} />
            ) : (
              <Radio size={15} />
            )}
            <span>
              {connection === "online"
                ? "API на зв’язку"
                : connection === "offline"
                  ? "API недоступний"
                  : "Завантаження…"}
            </span>
          </div>
        </div>
        {connection === "offline" && (
          <div className="notice error" role="alert">
            Зв’язок із API втрачено.{" "}
            {data ? "Показуємо останні отримані дані. " : ""}Повторюємо
            підключення автоматично (до 30 с).
          </div>
        )}
        <section className="filters card" aria-label="Вибір джерела">
          <label>
            Запуск replay
            <select
              aria-label="Запуск replay"
              value={chosen.run}
              onChange={(e) =>
                choose({ run: e.target.value, building: "", source: "" })
              }
            >
              <option value="">
                {data?.runs.length ? "Оберіть запуск" : "Очікуємо запуск"}
              </option>
              {data?.runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id}
                </option>
              ))}
            </select>
          </label>
          <label>
            Будівля
            <select
              aria-label="Будівля"
              value={chosen.building}
              onChange={(e) =>
                choose({
                  run: chosen.run,
                  building: e.target.value,
                  source: "",
                })
              }
            >
              <option value="">Оберіть будівлю</option>
              {buildings.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </label>
          <label>
            Джерело
            <select
              aria-label="Джерело"
              value={chosen.source}
              onChange={(e) => choose({ ...chosen, source: e.target.value })}
            >
              <option value="">Оберіть джерело</option>
              {data?.sources
                .filter((s) => s.building_id === chosen.building)
                .map((s) => (
                  <option key={s.source_id}>{s.source_id}</option>
                ))}
            </select>
          </label>
          <div className="filter-info">
            <span className="live-dot" />
            Оновлення ≈ 2 с
            <small>
              {updated
                ? "API оновлено " + label(updated).slice(11, 19) + " UTC"
                : "З’єднуємося з PostgreSQL"}
            </small>
          </div>
        </section>
        <section className="kpis">
          <article className="card kpi">
            <div className="kpi-top">
              Останнє споживання
              <Zap size={17} />
            </div>
            <strong>
              {valueLabel(latest?.energy_wh)}
              <small>{actualUnit}</small>
            </strong>
            <p>
              {latest
                ? label(latest.measurement_timestamp)
                : "Очікуємо вимірювання"}
            </p>
          </article>
          <article className="card kpi">
            <div className="kpi-top">
              Наступний інтервал
              <ArrowUpRight size={17} />
            </div>
            <strong>
              {valueLabel(next?.predicted_energy_wh)}
              <small>Wh / 10 хв</small>
            </strong>
            <p>
              {next
                ? `HGB20 · ${statusName(next.status)}`
                : "HGB20 · Очікуємо прогноз"}
            </p>
          </article>
          <article className="card kpi">
            <div className="kpi-top">
              Вимірювань у запуску
              <Database size={17} />
            </div>
            <strong data-testid="measurement-count">
              {data?.status.unique_measurements ?? "—"}
            </strong>
            <p>Унікальні записи PostgreSQL</p>
          </article>
          <article className="card kpi">
            <div className="kpi-top">
              Стан worker
              <Activity size={17} />
            </div>
            <strong className="unknown">Невідомий</strong>
            <p>Checkpoint не є heartbeat</p>
          </article>
        </section>
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
                    <linearGradient
                      id="energy-fill"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="0%"
                        stopColor="#289680"
                        stopOpacity={0.17}
                      />
                      <stop offset="100%" stopColor="#289680" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke="#edf1ef" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(v) => String(v).slice(11, 16)}
                    minTickGap={48}
                    tick={{ fontSize: 11, fill: "#82908d" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#82908d" }}
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
                    contentStyle={{
                      borderRadius: 12,
                      border: "1px solid #e6ece9",
                      fontSize: 12,
                    }}
                  />
                  <Area
                    dataKey="actual"
                    name="actual"
                    type="monotone"
                    stroke="#218570"
                    strokeWidth={2}
                    fill="url(#energy-fill)"
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="forecast"
                    name="forecast"
                    type="monotone"
                    stroke="#6b8bc9"
                    strokeWidth={2}
                    strokeDasharray="5 4"
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
                  Запустіть producer для вибраного запуску. Нові точки
                  з’являться автоматично.
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
            <span>Прогноз суміщено за цільовим часом · null ≠ 0</span>
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
        <section id="detectors" className="section-heading">
          <div>
            <h2>Експериментальні детектори</h2>
            <p>
              Score не є ймовірністю. Перевищення порогу не підтверджує
              несправність.
            </p>
          </div>
          <span className="subtle-tag">3 незалежні шкали</span>
        </section>
        <div className="detector-grid">
          {detectors.map((d) => (
            <ScoreChart
              key={d.id}
              detector={d}
              rows={data?.scores.filter((s) => s.detector === d.id) ?? []}
            />
          ))}
        </div>
        <section className="card pipeline">
          <div>
            <h3>Конвеєр обробки</h3>
            <p className="muted small">
              Лічильники всього запуску · стан зафіксованих транзакцій
            </p>
          </div>
          <div className="pipeline-metrics">
            <span>
              Прогнози
              <b data-testid="forecast-count">
                {data?.status.forecasts ?? "—"}
              </b>
            </span>
            <span>
              Оцінки
              <b data-testid="score-count">
                {data?.status.anomaly_scores ?? "—"}
              </b>
            </span>
            <span>
              Дублі
              <b data-testid="duplicate-count">
                {data?.status.duplicate_deliveries ?? "—"}
              </b>
            </span>
            <span>
              Відхилено
              <b data-testid="rejected-count">
                {data?.status.rejected_messages ?? "—"}
              </b>
            </span>
            <span>
              Next offset
              <b data-testid="checkpoint-next">
                {data?.status.checkpoints[0]?.next_offset ?? "—"}
              </b>
            </span>
          </div>
          <div className="last-processed">
            Остання транзакція: {label(data?.status.last_processed_at)}
          </div>
          {!!data?.status.recent_errors.length && (
            <div className="notice">
              Останні помилки:{" "}
              {data.status.recent_errors.map((e) => e.kind).join(", ")}
            </div>
          )}
        </section>
        <section id="events" className="card table-card">
          <div className="card-heading">
            <div>
              <h2>Історія експериментальних подій</h2>
              <p className="muted small">
                Епізоди перевищення порогу · це не підтверджені несправності
              </p>
            </div>
            <span className="badge experimental">experimental</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Початок / кінець зафіксованого перевищення</th>
                  <th>Детектор</th>
                  <th>Точок</th>
                  <th>Стан епізоду</th>
                </tr>
              </thead>
              <tbody>
                {data?.events.map((e) => (
                  <tr key={e.episode_id}>
                    <td>
                      {label(e.start_timestamp)}
                      <small>{label(e.end_timestamp)}</small>
                    </td>
                    <td>
                      {detectors.find((d) => d.id === e.detector)?.name}
                      <small>{e.threshold_version}</small>
                    </td>
                    <td>{e.flagged_points}</td>
                    <td>
                      <span
                        className={`status ${e.status === "open" ? "open" : ""}`}
                      >
                        {e.status === "open" ? "Відкритий" : "Завершений"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data?.events.length && (
              <p className="table-empty">
                Перевищень порогу поки не зафіксовано.
              </p>
            )}
          </div>
          {data?.moreEvents && (
            <p className="muted small">
              Показано останні 50 подій. Повна історія доступна через cursor
              API.
            </p>
          )}
        </section>
        <section className="card table-card">
          <div className="card-heading">
            <div>
              <h2>Останні вимірювання</h2>
              <p className="muted small">
                Прогноз для того самого цільового інтервалу
              </p>
            </div>
            <span className="subtle-tag">{actualUnit}</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Час вимірювання</th>
                  <th>Факт, Wh</th>
                  <th>HGB20, Wh</th>
                  <th>Деталі</th>
                </tr>
              </thead>
              <tbody>
                {chart
                  .filter((p) => p.measurement)
                  .slice(-5)
                  .reverse()
                  .map((p) => (
                    <tr key={p.timestamp}>
                      <td>{label(p.timestamp)}</td>
                      <td>{valueLabel(p.actual)}</td>
                      <td>{valueLabel(p.forecast)}</td>
                      <td>
                        <button
                          className="text-button"
                          onClick={() =>
                            setDetail(p.measurement!.measurement_id)
                          }
                        >
                          Переглянути ↗
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {detailRow && (
            <div className="details" data-testid="measurement-detail">
              <b>Часові мітки запису</b>
              <dl>
                <dt>Час вимірювання (джерело)</dt>
                <dd>{label(detailRow.timestamp)}</dd>
                <dt>Надходження повідомлення (UTC)</dt>
                <dd>{label(detailRow.measurement?.received_at)}</dd>
                <dt>Origin прогнозу (джерело)</dt>
                <dd>{label(detailRow.prediction?.forecast_origin)}</dd>
                <dt>Target прогнозу (джерело)</dt>
                <dd>
                  {label(detailRow.prediction?.forecast_target_timestamp)}
                </dd>
                <dt>Формування прогнозу (UTC)</dt>
                <dd>{label(detailRow.prediction?.generated_at)}</dd>
                <dt>Версія прогнозної моделі</dt>
                <dd>{detailRow.prediction?.model_version ?? "—"}</dd>
              </dl>
            </div>
          )}
        </section>
        <section id="models" className="card table-card">
          <div className="card-heading">
            <div>
              <h2>Реєстр моделей</h2>
              <p className="muted small">
                HGB20 — основний прогноз · RF21 — окремий reference для residual
                detector
              </p>
            </div>
            <Box size={19} />
          </div>
          <div className="model-grid">
            {data?.models.map((m) => (
              <article className="model" key={m.model_id}>
                <span className="model-role">
                  {m.role === "primary_forecast"
                    ? "HGB20 · основний прогноз"
                    : m.role === "residual_reference"
                      ? "RF21 · residual reference"
                      : (detectors.find((d) => d.id === m.role)?.name ??
                        m.role)}
                </span>
                <span
                  className={`badge ${m.maturity === "experimental" ? "experimental" : "existing"}`}
                >
                  {m.maturity}
                </span>
                <code>{m.model_version}</code>
                <small>
                  {m.feature_version} · {m.feature_names.length} ознак
                </small>
                {m.threshold_version && (
                  <small>Поріг: {m.threshold_version}</small>
                )}
              </article>
            ))}
          </div>
          {!data?.models.length && (
            <p className="table-empty">
              Моделі з’являться після перших записаних прогнозів та оцінок.
            </p>
          )}
        </section>
        <footer>
          ENERGY MONITORING MVP
          <span>Kafka → Worker → PostgreSQL → FastAPI → Dashboard</span>
        </footer>
      </main>
    </div>
  );
}
