import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Activity,
  Database,
  Search,
  SlidersHorizontal,
  Zap,
  Gauge,
  Layers,
  Leaf,
  ShieldCheck,
  Clock3,
  Building2,
  Radio,
  AlertCircle,
  RefreshCw,
  ChevronRight,
  BarChart3,
  Info,
  Mail,
  Copy,
  Check,
  Box,
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
import { align, fetchJSON, label, valueLabel } from "./data";
import { chartTime, nextPrimary, finite, detectorNames } from "./insights";
import {
  fetchRuns,
  intervalLabel,
  loadSourceDetail,
  navigate,
  sourceDescription,
  sourceHref,
  sourceType,
  timeContext,
} from "./sourceData";
import { useResource } from "./useResource";
import type { Selection, SourceCatalog, SourceSummary } from "./types";
import ScoreChart, { detectors } from "./ScoreChart";
import CombinedPanel from "./CombinedPanel";
import NotificationsPanel from "./NotificationsPanel";
import "./sources.css";

function Link({
  href,
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      {...props}
      href={href}
      onClick={(e) => {
        if (
          href &&
          !e.ctrlKey &&
          !e.metaKey &&
          !e.shiftKey &&
          !e.altKey &&
          e.button === 0
        ) {
          e.preventDefault();
          navigate(href);
        }
      }}
    >
      {children}
    </a>
  );
}
function Frame({
  children,
  detail = false,
  selection = {},
}: {
  children: React.ReactNode;
  detail?: boolean;
  selection?: Partial<Selection>;
}) {
  return (
    <div className="app-shell sources-workspace">
      <aside className="sidebar">
        <a className="brand" href="?">
          <span className="brand-symbol">
            <Zap size={23} />
          </span>
          <span>
            Energy<span className="brand-sub">INTELLIGENCE</span>
          </span>
        </a>
        <div className="workspace-label">РОБОЧИЙ ПРОСТІР</div>
        <nav>
          <a href="?">
            <Gauge size={18} />
            Моніторинг
          </a>
          <Link
            href={sourceHref("sources", selection)}
            className="active"
            aria-current="page"
          >
            <Database size={18} />
            Пристрої та джерела
            <span className="nav-dot" />
          </Link>
          <a href="?#detectors">
            <Activity size={18} />
            Детектори
          </a>
          <a href="?#events">
            <Layers size={18} />
            Історія подій
          </a>
          <a href="?#models">
            <Box size={18} />
            Моделі
          </a>
        </nav>
        <div className="sidebar-note">
          <Leaf size={22} />
          <strong>Від даних до розуміння</strong>
          <p>
            Кожне джерело — у власному контексті. Від вимірювання до аналітики.
          </p>
          <span>ЛОКАЛЬНА ЕНЕРГЕТИЧНА ПЛАТФОРМА</span>
        </div>
        <div className="local-label">
          <ShieldCheck size={15} />
          Локальне середовище
        </div>
      </aside>
      <main>
        <header className="topbar">
          <span>
            Робочий простір <span className="slash">/</span>{" "}
            <b>{detail ? "Аналітика джерела" : "Пристрої та джерела"}</b>
          </span>
          <span className="subtle-tag">
            <Database size={13} />
            Збережені вимірювання
          </span>
        </header>
        {children}
      </main>
    </div>
  );
}
function ErrorNotice({
  retry,
  stale = false,
}: {
  retry: () => void;
  stale?: boolean;
}) {
  return (
    <div className="source-notice error" role="alert">
      <AlertCircle size={20} />
      <div>
        <strong>Не вдалося отримати дані API</strong>
        <p>
          {stale ? "Показано останні отримані дані. " : ""}Підключення
          відновлюється автоматично.
        </p>
      </div>
      <button className="source-button secondary" onClick={retry}>
        <RefreshCw size={15} />
        Повторити
      </button>
    </div>
  );
}
function Skeleton() {
  return (
    <div className="source-grid" role="status" aria-label="Завантаження джерел">
      {[0, 1, 2].map((x) => (
        <div key={x} className="card source-skeleton">
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}
function Empty({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card source-empty">
      <div className="source-empty-icon">
        <Database size={28} />
      </div>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}
function CopyId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1800);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <button
      className="source-copy"
      aria-label="Скопіювати повний ID джерела"
      title={value}
      onClick={() => {
        void navigator.clipboard
          ?.writeText(value)
          .then(() => setCopied(true))
          .catch(() => setCopied(false));
      }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      <span>{copied ? "Скопійовано" : "Копіювати ID"}</span>
    </button>
  );
}
function SourceCard({ row }: { row: SourceSummary }) {
  return (
    <article className="card source-card" data-testid="source-card">
      <div className="source-card-top">
        <span className="source-icon">
          <Database size={22} />
        </span>
        <span className="source-type">{sourceType(row)}</span>
      </div>
      <h2 title={row.source_id}>{row.source_id}</h2>
      <p className="source-building">
        <Building2 size={14} />
        {row.building_id}
      </p>
      <p className="source-description">{sourceDescription(row)}</p>
      <div className="source-reading">
        <span>Остання інтервальна енергія</span>
        <strong>
          {valueLabel(row.latest_energy_wh)}
          <small>Wh / {intervalLabel(row)}</small>
        </strong>
        <time>{label(row.measurement_timestamp)}</time>
      </div>
      <div className="source-card-meta">
        <span>
          <Clock3 size={14} />
          {intervalLabel(row)}
        </span>
        <span>Активність невідома</span>
      </div>
      <p className="source-time-note">{timeContext(row)}</p>
      <Link
        className="source-button"
        href={sourceHref("source", {
          run: row.run_id,
          building: row.building_id,
          source: row.source_id,
        })}
      >
        Переглянути аналітику
        <ArrowRight size={16} />
      </Link>
    </article>
  );
}
export default function SourcesWorkspace({ route }: { route: string }) {
  const q = new URLSearchParams(route),
    isDetail = q.get("view") === "source";
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const runs = useResource("source-runs", fetchRuns, 10000);
  const run = q.get("run") || runs.data?.items.at(-1)?.run_id || "";
  const building = q.get("building") || "";
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setCursor(null);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    setCursor(null);
  }, [run, building]);
  const key = JSON.stringify([isDetail, run, building, debounced, cursor]);
  const resource = useResource(
    key,
    async (signal) => {
      if (isDetail || !run) return null;
      return fetchJSON<SourceCatalog>(
        "/api/source-summaries?" +
          new URLSearchParams({
            run_id: run,
            limit: "24",
            ...(building ? { building_id: building } : {}),
            ...(debounced ? { search: debounced } : {}),
            ...(cursor ? { cursor } : {}),
          }),
        signal,
      );
    },
    5000,
  );
  const data = resource.data;
  const state =
    runs.status === "offline" || resource.status === "offline"
      ? "offline"
      : runs.status === "loading" || (run && resource.status === "loading")
        ? "loading"
        : "online";
  if (isDetail)
    return (
      <SourceDetails
        selection={{
          run: q.get("run") || "",
          building,
          source: q.get("source") || "",
        }}
      />
    );
  const buildings = [
    ...new Set([
      ...(data?.building_ids ?? []),
      ...(building ? [building] : []),
    ]),
  ];
  return (
    <Frame selection={{ run, building }}>
      <div className="page-heading source-heading">
        <div>
          <div className="eyebrow">ДЖЕРЕЛА ЕНЕРГЕТИЧНИХ ДАНИХ</div>
          <h1>
            Пристрої та джерела<span>.</span>
          </h1>
          <p>
            Відкрийте джерело, щоб побачити його споживання, прогнози та історію
            оцінок.
          </p>
        </div>
        <span className="source-heading-icon">
          <Database size={30} />
        </span>
      </div>
      <section className="card source-intro">
        <span className="source-intro-icon">
          <Info size={20} />
        </span>
        <div>
          <strong>Дані мають свій контекст</strong>
          <p>
            Каталог показує джерела зі збереженими вимірюваннями у вибраному
            запуску. Джерело датасету не обов’язково є фізичним пристроєм.
          </p>
        </div>
      </section>
      <section className="card source-controls" aria-label="Фільтри каталогу">
        <label>
          Запуск
          <select
            aria-label="Запуск каталогу"
            value={run}
            onChange={(e) => {
              setCursor(null);
              navigate(sourceHref("sources", { run: e.target.value }));
            }}
          >
            <option value="">Оберіть запуск</option>
            {runs.data?.items.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Будівля
          <select
            aria-label="Будівля каталогу"
            value={building}
            onChange={(e) => {
              setCursor(null);
              navigate(
                sourceHref("sources", { run, building: e.target.value }),
              );
            }}
          >
            <option value="">Усі будівлі</option>
            {buildings.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </label>
        <label className="source-search">
          Пошук за ID
          <div>
            <Search size={17} />
            <input
              aria-label="Пошук джерел"
              placeholder="Джерело або будівля…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </label>
      </section>
      {state === "offline" && (
        <ErrorNotice
          retry={() => {
            runs.retry();
            resource.retry();
          }}
          stale={!!data}
        />
      )}
      <div className="source-results-heading">
        <h2>Доступні джерела</h2>
        <span>
          {data ? `${data.items.length} на цій сторінці` : "Завантаження…"}
        </span>
      </div>
      {state === "loading" ? (
        <Skeleton />
      ) : data?.items.length ? (
        <div className="source-grid">
          {data.items.map((row) => (
            <SourceCard
              key={JSON.stringify([row.building_id, row.source_id])}
              row={row}
            />
          ))}
        </div>
      ) : state !== "offline" ? (
        <Empty
          title={
            debounced
              ? "Нічого не знайдено"
              : building
                ? "У цій будівлі немає джерел"
                : "Каталог поки порожній"
          }
        >
          {debounced
            ? "Спробуйте інший ID або очистіть пошук."
            : "Оберіть інший запуск чи будівлю. Джерела з’являються після збереження їхніх вимірювань."}
        </Empty>
      ) : null}
      <div className="source-pagination">
        {cursor && (
          <button
            className="source-button secondary"
            onClick={() => setCursor(null)}
          >
            <ArrowLeft size={16} />
            До першої сторінки
          </button>
        )}
        {data?.next_cursor && (
          <button
            className="source-button secondary"
            onClick={() => setCursor(data.next_cursor)}
          >
            Наступні джерела
            <ArrowRight size={16} />
          </button>
        )}
      </div>
      {(runs.data?.next_cursor || data?.buildings_truncated) && (
        <p className="muted small">
          Список запусків або будівель обмежений. Відомі ідентифікатори можна
          відкрити прямим посиланням.
        </p>
      )}
      <p className="source-footnote">
        <ShieldCheck size={14} />
        Лише читання з PostgreSQL. Доступність API не означає, що джерело зараз
        активне.
      </p>
    </Frame>
  );
}
function SourceDetails({ selection }: { selection: Selection }) {
  const [windowSize, setWindowSize] = useState(144);
  const [tab, setTab] = useState("overview");
  const scope = JSON.stringify(selection);
  useEffect(() => setTab("overview"), [scope]);
  const resource = useResource(
    JSON.stringify([selection, windowSize]),
    (signal) => loadSourceDetail(selection, windowSize, signal),
    2000,
  );
  const data = resource.data,
    source = data?.source,
    latest = data?.measurements[0];
  const next = data
    ? nextPrimary(latest, data.forecasts, data.basis)
    : undefined;
  const points = data
    ? align(data.measurements, data.forecasts, data.basis)
    : [];
  const energies = (data?.measurements ?? [])
    .map((m) => m.energy_wh)
    .filter(finite);
  const mean = energies.length
    ? energies.reduce((a, b) => a + b, 0) / energies.length
    : null;
  const unit = source ? `Wh / ${intervalLabel(source)}` : "Wh";
  const back = sourceHref("sources", {
    run: selection.run,
    building: selection.building,
  });
  const tabs = [
    { id: "overview", name: "Огляд", icon: BarChart3 },
    { id: "detectors", name: "Детектори", icon: Activity },
    { id: "events", name: "Епізоди", icon: Layers },
    { id: "notifications", name: "Сповіщення", icon: Mail },
    { id: "info", name: "Про джерело", icon: Info },
  ];
  return (
    <Frame detail selection={selection}>
      <nav className="source-breadcrumbs" aria-label="Навігаційний шлях">
        <Link href={back}>Пристрої та джерела</Link>
        <ChevronRight size={14} />
        <span>{selection.source || "Невідоме джерело"}</span>
      </nav>
      <div className="page-heading source-heading">
        <div>
          <div className="eyebrow">АНАЛІТИКА ДЖЕРЕЛА</div>
          <h1 className="source-detail-title">
            {selection.source || "Джерело не задано"}
          </h1>
          <p className="source-building">
            <Building2 size={15} />
            {selection.building || "Будівлю не задано"} ·{" "}
            {source ? sourceType(source) : "Джерело вимірювань"}
          </p>
        </div>
        <Link href={back} className="source-button secondary">
          <ArrowLeft size={16} />
          До каталогу
        </Link>
      </div>
      {resource.status === "offline" && (
        <ErrorNotice retry={resource.retry} stale={!!data} />
      )}
      {resource.status === "loading" ? (
        <Skeleton />
      ) : data === null ? (
        <Empty title="Джерело не знайдено">
          У цьому запуску немає збережених даних для вказаної пари будівлі та
          джерела. Перевірте посилання або поверніться до каталогу.
        </Empty>
      ) : data && source ? (
        <>
          <div className="source-context">
            <span>
              <Database size={14} />
              {timeContext(source)}
            </span>
            <span>
              <Clock3 size={14} />
              Інтервал {intervalLabel(source)}
            </span>
            <span>Активність джерела невідома</span>
          </div>
          <section className="source-metrics">
            <article className="card">
              <span>
                Останнє споживання
                <Zap size={17} />
              </span>
              <strong data-testid="source-latest-energy">
                {valueLabel(latest?.energy_wh)}
                <small>{unit}</small>
              </strong>
              <p>{label(latest?.measurement_timestamp)}</p>
            </article>
            <article className="card">
              <span>
                Наступний прогноз HGB20
                <ArrowRight size={17} />
              </span>
              <strong data-testid="source-next-forecast">
                {valueLabel(
                  next?.status === "ready" ? next.predicted_energy_wh : null,
                )}
                <small>{unit}</small>
              </strong>
              <p>Ціль: {label(next?.forecast_target_timestamp)}</p>
            </article>
            <article className="card">
              <span>
                Середнє у видимому вікні
                <BarChart3 size={17} />
              </span>
              <strong>
                {valueLabel(mean)}
                <small>{unit}</small>
              </strong>
              <p>{energies.length} доступних вимірювань</p>
            </article>
          </section>
          <div
            className="source-tabs"
            role="tablist"
            aria-label="Розділи аналітики"
          >
            {tabs.map((t) => (
              <button
                key={t.id}
                role="tab"
                id={"source-tab-" + t.id}
                aria-controls="source-content"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
              >
                <t.icon size={16} />
                {t.name}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id="source-content"
            aria-labelledby={"source-tab-" + tab}
          >
            {tab === "overview" && (
              <>
                <section className="card source-chart">
                  <div className="card-heading">
                    <div>
                      <h2>Споживання та прогноз</h2>
                      <p className="muted small">
                        Інтервальна енергія · {unit}
                      </p>
                    </div>
                    <label className="source-window">
                      Видиме вікно
                      <select
                        aria-label="Вікно джерела"
                        value={windowSize}
                        onChange={(e) => setWindowSize(Number(e.target.value))}
                      >
                        {[72, 144, 288].map((n) => (
                          <option key={n} value={n}>
                            Останні {n} вимірювання
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="chart-legend">
                    <span>
                      <i className="legend-line" />
                      Фактичне споживання
                    </span>
                    <span>
                      <i className="legend-line predicted" />
                      Основний прогноз HGB20
                    </span>
                  </div>
                  <div
                    className="source-energy-chart"
                    data-testid="source-energy-chart"
                  >
                    {points.length ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                          data={points}
                          margin={{ top: 15, right: 12, left: 0, bottom: 12 }}
                        >
                          <defs>
                            <linearGradient
                              id="source-energy-fill"
                              x1="0"
                              y1="0"
                              x2="0"
                              y2="1"
                            >
                              <stop
                                offset="0%"
                                stopColor="var(--accent)"
                                stopOpacity={0.22}
                              />
                              <stop
                                offset="100%"
                                stopColor="var(--accent)"
                                stopOpacity={0}
                              />
                            </linearGradient>
                          </defs>
                          <CartesianGrid
                            stroke="var(--chart-grid)"
                            vertical={false}
                          />
                          <XAxis
                            dataKey="timestamp"
                            tickFormatter={chartTime}
                            minTickGap={50}
                            tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <YAxis
                            width={45}
                            tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <Tooltip
                            labelFormatter={(v) => label(String(v))}
                            formatter={(v, n) => [
                              `${valueLabel(v as number | null)} Wh`,
                              n === "actual" ? "Факт" : "Прогноз HGB20",
                            ]}
                            contentStyle={{
                              background: "var(--surface-secondary)",
                              border: "1px solid var(--border-strong)",
                              borderRadius: 10,
                              color: "var(--text)",
                            }}
                          />
                          <Area
                            type="monotone"
                            dataKey="actual"
                            stroke="var(--accent)"
                            fill="url(#source-energy-fill)"
                            strokeWidth={2}
                            dot={false}
                            connectNulls={false}
                            isAnimationActive={false}
                          />
                          <Line
                            type="monotone"
                            dataKey="forecast"
                            stroke="var(--forecast)"
                            strokeWidth={2}
                            strokeDasharray="5 4"
                            dot={false}
                            connectNulls={false}
                            isAnimationActive={false}
                          />
                        </ComposedChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-empty">
                        Вимірювань у вибраному вікні немає
                      </div>
                    )}
                  </div>
                  <div className="chart-caption">
                    <span>{timeContext(source)}</span>
                    <span>
                      Прогноз зіставлено за цільовим часом · відсутнє значення
                      не означає нуль
                    </span>
                  </div>
                </section>
                {(!next ||
                  next.status !== "ready" ||
                  next.predicted_energy_wh === null) && (
                  <div
                    className="source-notice"
                    data-testid="source-forecast-unavailable"
                  >
                    <Info size={20} />
                    <div>
                      <strong>Прогноз недоступний</strong>
                      <p>
                        {next?.status === "incompatible" ||
                        latest?.feature_status === "incompatible"
                          ? "Навчена модель не підтримує прив’язку цього джерела. API не надає детальнішої причини несумісності."
                          : latest?.gap_detected
                            ? "Часова історія перервана; необхідно знову накопичити послідовні вимірювання."
                            : "Накопичується історія або відповідний прогноз ще не збережено. Відсутнє значення не означає нульове споживання."}
                      </p>
                    </div>
                  </div>
                )}
                <section className="card source-window-stats">
                  <div>
                    <h2>Описова статистика вікна</h2>
                    <p>
                      {label(data.measurements.at(-1)?.measurement_timestamp)} —{" "}
                      {label(latest?.measurement_timestamp)}
                    </p>
                  </div>
                  <dl>
                    <div>
                      <dt>Мінімум</dt>
                      <dd>
                        {valueLabel(
                          energies.length ? Math.min(...energies) : null,
                        )}
                        <small>{unit}</small>
                      </dd>
                    </div>
                    <div>
                      <dt>Максимум</dt>
                      <dd>
                        {valueLabel(
                          energies.length ? Math.max(...energies) : null,
                        )}
                        <small>{unit}</small>
                      </dd>
                    </div>
                    <div>
                      <dt>Спостережень</dt>
                      <dd>{energies.length}</dd>
                    </div>
                  </dl>
                  <p className="muted small">
                    Лише отримані вимірювання вибраного вікна цього джерела. Це
                    не статистика всієї будівлі чи запуску; пропуски не
                    заповнюються.
                  </p>
                </section>
              </>
            )}
            {tab === "detectors" && (
              <>
                <div className="source-section-title">
                  <h2>Експериментальні оцінки</h2>
                  <p>
                    Score не є ймовірністю. Перевищення порогу не підтверджує
                    несправність. Кожен метод має власну шкалу.
                  </p>
                </div>
                <div className="detector-grid">
                  {detectors.map((d) => (
                    <ScoreChart
                      key={d.id}
                      detector={d}
                      experimentalLabel="Експериментально"
                      rows={data.scores.filter((s) => s.detector === d.id)}
                    />
                  ))}
                </div>
                <CombinedPanel data={data} localized />
              </>
            )}
            {tab === "events" && (
              <section className="card table-card">
                <div className="card-heading">
                  <h2>Історія епізодів</h2>
                  <span className="badge experimental">Експериментально</span>
                </div>
                <p className="muted small">
                  Останні 50 епізодів цього джерела у вибраному запуску, не лише
                  видиме вікно. Це не підтверджені несправності.
                </p>
                {data.events.length ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Початок / останнє перевищення</th>
                          <th>Метод</th>
                          <th>Точок</th>
                          <th>Стан</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.events.map((e) => (
                          <tr key={e.episode_id}>
                            <td>
                              {label(e.start_timestamp)}
                              <small>{label(e.end_timestamp)}</small>
                            </td>
                            <td>
                              {detectorNames[e.detector]}
                              <small>{e.model_version}</small>
                            </td>
                            <td>{e.flagged_points}</td>
                            <td>
                              {e.status === "open" ? "Відкритий" : "Завершений"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="source-tab-empty">
                    Збережених епізодів немає. Відсутність оцінок не означає
                    відсутності відхилень.
                  </p>
                )}
                {data.moreEvents && (
                  <p className="muted small">
                    Повна історія доступна через cursor API.
                  </p>
                )}
              </section>
            )}
            {tab === "notifications" && (
              <NotificationsPanel rows={data.notifications} localized />
            )}
            {tab === "info" && (
              <section className="card source-info">
                <div className="card-heading">
                  <h2>Джерело та доступність аналітики</h2>
                  <CopyId value={selection.source} />
                </div>
                <p>{sourceDescription(source)}</p>
                <dl>
                  <dt>Повний ID джерела</dt>
                  <dd>
                    <code>{selection.source}</code>
                  </dd>
                  <dt>Будівля</dt>
                  <dd>
                    <code>{selection.building}</code>
                  </dd>
                  <dt>Запуск</dt>
                  <dd>
                    <code>{selection.run}</code>
                  </dd>
                  <dt>Тип</dt>
                  <dd>{sourceType(source)}</dd>
                  <dt>Область вимірювань</dt>
                  <dd>{source.energy_scope ?? "Не зазначена"}</dd>
                  <dt>Час</dt>
                  <dd>{timeContext(source)}</dd>
                  <dt>Надходження останнього запису, UTC</dt>
                  <dd>{label(latest?.received_at)}</dd>
                  <dt>Формування прогнозу HGB20, UTC</dt>
                  <dd>{label(next?.generated_at)}</dd>
                  <dt>Початкова мітка прогнозу</dt>
                  <dd>{label(next?.forecast_origin)}</dd>
                  <dt>Цільова мітка прогнозу</dt>
                  <dd>{label(next?.forecast_target_timestamp)}</dd>
                  <dt>Модель / версія ознак</dt>
                  <dd>
                    {next?.model_version ?? "Недоступна"} /{" "}
                    {next?.feature_version ?? "—"}
                  </dd>
                </dl>
                <div className="source-notice">
                  <Info size={19} />
                  <p>
                    HGB20 — основний прогноз. RF21 — опора залишкового
                    детектора, він не підміняє основну лінію. Без heartbeat
                    активність джерела невідома.
                  </p>
                </div>
              </section>
            )}
          </div>
        </>
      ) : null}
    </Frame>
  );
}
